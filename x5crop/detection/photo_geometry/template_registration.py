"""Register the finite template inputs for one already measured lane."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations
import math

from ...domain import FiniteInterval, PositiveInterval
from ...formats import FramePhysicalSpec
from .boundary_fitting import fit_format_bound_boundary_observation
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import (
    BoundaryAxis,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from .observation_types import BasicAxisProfile, ProfileRun
from .line_observations import PhotoBoundaryObservation
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry, centered_short_axis_authority_px
from .template_cross_model import CrossEvidence, CrossRoleBinding
from .template_model import PhaseLatticeAuthority, TemplateSpec
from .trace_support import trace_support_is_one_connected_run


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )


def template_spec_from_physical_authority(
    *,
    frame_spec: FramePhysicalSpec,
    source_geometry: SourceScanGeometry,
    width_scale_px_per_mm: PositiveInterval,
    count: int,
    phase_lattice_authority: PhaseLatticeAuthority,
    template_id: str | None = None,
) -> TemplateSpec:
    """Scale the user's fixed format once; observations only refine it."""

    width = source_geometry.width_state.extent_projection_px()
    height = source_geometry.height_state.extent_projection_px()
    calibrated_scale = source_geometry.width_state.feasible_scale_interval()
    if frame_spec.format_gap_prior_mm is None:
        gap = FiniteInterval(width.minimum * 0.02, width.maximum * 0.20)
    else:
        gap = FiniteInterval(
            frame_spec.format_gap_prior_mm * calibrated_scale.minimum,
            frame_spec.format_gap_prior_mm * calibrated_scale.maximum,
        )
    return TemplateSpec(
        template_id=(
            template_id
            or f"template:{frame_spec.frame_spec_id}:direct:{count}"
        ),
        frame_width_px=width,
        frame_height_px=height,
        pitch_px=_add(width, gap),
        nominal_gap_px=gap,
        count=count,
        phase_lattice_authority=phase_lattice_authority.with_period(
            _add(width, gap)
        ),
    )


@dataclass(frozen=True)
class RegisteredCrossEvidence:
    top_bindings: tuple[CrossRoleBinding, ...]
    bottom_bindings: tuple[CrossRoleBinding, ...]
    observations: tuple[PhotoBoundaryObservation, ...]
    fit_attempt_count: int

    def __post_init__(self) -> None:
        identities = tuple(item.observation_id for item in self.observations)
        if len(set(identities)) != len(identities):
            raise ValueError("cross observations must be registered once")
        if self.fit_attempt_count < len(self.observations):
            raise ValueError("cross fit-attempt receipt is incomplete")


def _interval_distance(
    left: FiniteInterval,
    right: FiniteInterval,
) -> tuple[float, float]:
    """Return minimum and maximum separation of two physical intervals."""

    minimum = max(
        left.minimum - right.maximum,
        right.minimum - left.maximum,
        0.0,
    )
    maximum = max(
        abs(left.minimum - right.maximum),
        abs(left.maximum - right.minimum),
    )
    return minimum, maximum


def _binding_covers_template_domains(
    binding: CrossRoleBinding,
    domains: tuple[FiniteInterval, ...],
) -> bool:
    return bool(domains) and all(
        any(
            domain.contains(float(trace), epsilon=0.5)
            for trace in binding.trace_coordinates_px
        )
        for domain in domains
    )


def _project_cross_anchor(
    binding: CrossRoleBinding,
    *,
    trace_coordinate_px: int,
    lane_reference_trace_px: float,
    canonical_height_px: float,
) -> FiniteInterval:
    """Project one direct side to the expected opposite-side corridor."""

    direction = binding.full_direction_interval_degrees
    if direction is None:
        raise ValueError("cross refinement anchor needs direct direction")
    delta_trace = float(trace_coordinate_px) - lane_reference_trace_px
    slopes = tuple(
        math.tan(math.radians(value))
        for value in (direction.minimum, direction.maximum)
    )
    projected = tuple(
        coordinate + slope * delta_trace
        for coordinate in (
            binding.full_interval_px.minimum,
            binding.full_interval_px.maximum,
        )
        for slope in slopes
    )
    advance = (
        canonical_height_px
        if binding.role == BoundaryRole.TOP
        else -canonical_height_px
    )
    return FiniteInterval(min(projected) + advance, max(projected) + advance)


def _canonical_cross_run(
    observation: PhotoBoundaryObservation,
    measurement: PhotoBoundaryMeasurementSet,
) -> ProfileRun:
    transition_by_id = {
        transition.transition_id: transition
        for transition in measurement.transitions
    }
    transitions = tuple(
        transition_by_id[identity] for identity in observation.transition_ids
    )
    traces = tuple(sorted({item.trace_coordinate_px for item in transitions}))
    queried = measurement.query.trace_positions_px
    return ProfileRun(
        run_id=physical_fact_id(
            "registered-cross-run",
            observation.role.value,
            observation.observation_id,
        ),
        coordinate_interval_px=observation.offset_interval_px,
        transition_ids=observation.transition_ids,
        trace_coordinates_px=traces,
        role_hint=observation.role,
        qualified_anchor_roles=(observation.role,),
        support_fraction=len(traces) / len(queried),
        continuous_support_fraction=observation.continuous_support_fraction,
        fit_residual_px=observation.fit_residual_px,
        evidence_strength=sum(
            item.gradient_z + max(item.tone_z, item.texture_z)
            for item in transitions
        )
        / len(transitions),
        pair_qualified=True,
    )


def _merge_registered_cross_families(
    values: tuple[PhotoBoundaryObservation, ...],
    *,
    measurement: PhotoBoundaryMeasurementSet,
    role: BoundaryRole,
    width_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
) -> tuple[tuple[PhotoBoundaryObservation, ...], int]:
    """Merge only a complete connected union that refits as one line."""

    if len(values) < 2:
        return values, 0
    fit_cache: dict[tuple[str, ...], PhotoBoundaryObservation | None] = {}
    attempts = 0

    def fit(indices: tuple[int, ...]) -> PhotoBoundaryObservation | None:
        nonlocal attempts
        identities = tuple(
            sorted(
                {
                    identity
                    for index in indices
                    for identity in values[index].transition_ids
                },
                key=str,
            )
        )
        key = tuple(map(str, identities))
        if key not in fit_cache:
            attempts += 1
            fit_cache[key] = fit_format_bound_boundary_observation(
                measurement,
                transition_ids=identities,
                role=role,
                source_axis_long=width_axis,
                boundary_axis_scale_px_per_mm=height_scale_px_per_mm,
            )
        candidate = fit_cache[key]
        if candidate is None:
            return None
        selected = set(candidate.transition_ids)
        if not all(
            len(selected.intersection(values[index].transition_ids)) >= 2
            for index in indices
        ):
            return None
        traces = tuple(
            sorted(
                transition.trace_coordinate_px
                for transition in measurement.transitions
                if transition.transition_id in selected
            )
        )
        if not trace_support_is_one_connected_run(
            measurement.query.trace_positions_px,
            traces,
            spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
        ):
            return None
        return candidate

    mergeable: set[tuple[int, int]] = set()
    queried = measurement.query.trace_positions_px
    for left, right in combinations(range(len(values)), 2):
        traces = tuple(
            sorted(
                {
                    transition.trace_coordinate_px
                    for transition in measurement.transitions
                    if transition.transition_id
                    in {
                        *values[left].transition_ids,
                        *values[right].transition_ids,
                    }
                }
            )
        )
        if not trace_support_is_one_connected_run(
            queried,
            traces,
            spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
        ):
            continue
        if fit((left, right)) is not None:
            mergeable.add((left, right))

    components: list[tuple[int, ...]] = []
    remaining = set(range(len(values)))
    while remaining:
        frontier = [min(remaining)]
        component: set[int] = set()
        while frontier:
            member = frontier.pop()
            if member in component:
                continue
            component.add(member)
            frontier.extend(
                candidate
                for candidate in remaining
                if (min(member, candidate), max(member, candidate)) in mergeable
            )
        remaining.difference_update(component)
        components.append(tuple(sorted(component)))

    merged: list[PhotoBoundaryObservation] = []
    for component in components:
        if len(component) == 1:
            merged.append(values[component[0]])
            continue
        observation = fit(component)
        if observation is None:
            merged.extend(values[index] for index in component)
        else:
            merged.append(observation)
    return tuple(merged), attempts


def register_cross_evidence(
    *,
    profile: BasicAxisProfile,
    top_measurement: PhotoBoundaryMeasurementSet,
    bottom_measurement: PhotoBoundaryMeasurementSet,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
    lane_reference_trace_px: float,
    maximum_runs: int = 256,
) -> RegisteredCrossEvidence:
    """Fit every registered top/bottom run once, without placement queries."""

    if maximum_runs <= 0:
        raise ValueError("cross registration bound must be positive")
    qualified = tuple(
        run
        for run in profile.runs
        if run.role_hint in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        and (run.pair_qualified or run.anchor_qualified_for(run.role_hint))
    )
    if len(qualified) > maximum_runs:
        raise ValueError("cross registration bound exceeded")
    observations_by_role: dict[BoundaryRole, dict[str, PhotoBoundaryObservation]] = {
        BoundaryRole.TOP: {},
        BoundaryRole.BOTTOM: {},
    }
    fit_attempt_count = 0
    for run in qualified:
        measurement = (
            top_measurement
            if run.role_hint == BoundaryRole.TOP
            else bottom_measurement
        )
        observation = fit_format_bound_boundary_observation(
            measurement,
            transition_ids=run.transition_ids,
            role=run.role_hint,
            source_axis_long=width_axis,
            boundary_axis_scale_px_per_mm=height_scale_px_per_mm,
            minimum_independent_support_regions=(
                MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            ),
        )
        fit_attempt_count += 1
        if observation is None:
            continue
        key = str(observation.observation_id)
        observations_by_role[run.role_hint].setdefault(key, observation)
    merged_observations: list[PhotoBoundaryObservation] = []
    for role, measurement in (
        (BoundaryRole.TOP, top_measurement),
        (BoundaryRole.BOTTOM, bottom_measurement),
    ):
        values, attempts = _merge_registered_cross_families(
            tuple(observations_by_role[role].values()),
            measurement=measurement,
            role=role,
            width_axis=width_axis,
            height_scale_px_per_mm=height_scale_px_per_mm,
        )
        fit_attempt_count += attempts
        merged_observations.extend(values)
    registered = {
        str(observation.observation_id): (
            CrossRoleBinding.from_measurement(
                _canonical_cross_run(
                    observation,
                    top_measurement
                    if observation.role == BoundaryRole.TOP
                    else bottom_measurement,
                ),
                observation,
                lane_reference_trace_px=lane_reference_trace_px,
                boundary_axis=height_axis,
            ),
            observation,
        )
        for observation in merged_observations
    }
    ordered = tuple(
        registered[key]
        for key in sorted(
            registered,
            key=lambda identity: (
                registered[identity][0].coordinate_interval_px.center,
                identity,
            ),
        )
    )
    return RegisteredCrossEvidence(
        top_bindings=tuple(
            binding
            for binding, _observation in ordered
            if binding.role == BoundaryRole.TOP
        ),
        bottom_bindings=tuple(
            binding
            for binding, _observation in ordered
            if binding.role == BoundaryRole.BOTTOM
        ),
        observations=tuple(observation for _binding, observation in ordered),
        fit_attempt_count=fit_attempt_count,
    )


def register_template_local_cross_refinements(
    registered: RegisteredCrossEvidence,
    *,
    top_measurement: PhotoBoundaryMeasurementSet,
    bottom_measurement: PhotoBoundaryMeasurementSet,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
    lane_reference_trace_px: float,
    fixed_height_px: FiniteInterval,
    canonical_height_px: float,
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
    maximum_bindings: int = 256,
) -> RegisteredCrossEvidence:
    """Refine the missing cross side inside a template-projected local window.

    The measurements were registered and completed before placement fitting.
    A source-wide, role-authorized direct side plus fixed H predicts one finite
    corridor on the opposite measurement.  At each trace only a uniquely
    nearest physical transition may enter the single robust refit.  Therefore
    this pass neither rereads pixels nor turns the template into evidence.
    """

    if not isinstance(registered, RegisteredCrossEvidence):
        raise TypeError("cross refinement requires registered evidence")
    if maximum_bindings <= 0:
        raise ValueError("cross refinement binding bound must be positive")
    if fixed_height_px.minimum <= 0.0:
        raise ValueError("cross refinement height must be positive")
    if not fixed_height_px.contains(canonical_height_px, epsilon=1.0e-9):
        raise ValueError("canonical cross height leaves physical authority")
    domains = tuple(longitudinal_support_domains_px)
    if not domains:
        return registered

    anchors = tuple(
        binding
        for binding in (*registered.top_bindings, *registered.bottom_bindings)
        if binding.role_authorized
        and binding.canonical_direction_degrees is not None
        and binding.full_direction_interval_degrees is not None
        and binding.independent_support_region_count
        >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        and (
            binding.source_spanning_continuous
            or _binding_covers_template_domains(binding, domains)
        )
    )
    if not anchors:
        return registered

    height_radius_px = max(
        canonical_height_px - fixed_height_px.minimum,
        fixed_height_px.maximum - canonical_height_px,
    )
    local_radius_px = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.local_window_mm
        * height_scale_px_per_mm.maximum
    )
    refinement_radius_px = height_radius_px + local_radius_px
    observations = {
        str(item.observation_id): item for item in registered.observations
    }
    bindings = {
        str(item.observation_id): item
        for item in (*registered.top_bindings, *registered.bottom_bindings)
    }
    fit_attempt_count = registered.fit_attempt_count

    for anchor in anchors:
        opposite_role = (
            BoundaryRole.BOTTOM
            if anchor.role == BoundaryRole.TOP
            else BoundaryRole.TOP
        )
        measurement = (
            bottom_measurement
            if opposite_role == BoundaryRole.BOTTOM
            else top_measurement
        )
        by_trace: dict[int, list[object]] = {}
        for transition in measurement.transitions:
            by_trace.setdefault(transition.trace_coordinate_px, []).append(
                transition
            )
        selected = []
        for trace in measurement.query.trace_positions_px:
            expected = _project_cross_anchor(
                anchor,
                trace_coordinate_px=trace,
                lane_reference_trace_px=lane_reference_trace_px,
                canonical_height_px=canonical_height_px,
            )
            local = []
            for transition in by_trace.get(trace, ()):
                distance = _interval_distance(
                    transition.physical_position_interval_px,
                    expected,
                )
                if distance[0] <= refinement_radius_px:
                    local.append((distance, transition))
            distances = tuple(
                sorted(
                    local,
                    key=lambda item: (
                        item[0][0],
                        item[0][1],
                        str(item[1].transition_id),
                    ),
                )
            )
            if not distances:
                continue
            if (
                len(distances) > 1
                and distances[0][0][1] >= distances[1][0][0] - 1.0e-9
            ):
                continue
            selected.append(distances[0][1].transition_id)
        if not selected:
            continue
        fit_attempt_count += 1
        observation = fit_format_bound_boundary_observation(
            measurement,
            transition_ids=tuple(selected),
            role=opposite_role,
            source_axis_long=width_axis,
            boundary_axis_scale_px_per_mm=height_scale_px_per_mm,
            minimum_independent_support_regions=(
                MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            ),
        )
        if observation is None:
            continue
        run = _canonical_cross_run(observation, measurement)
        binding = CrossRoleBinding.from_measurement(
            run,
            observation,
            lane_reference_trace_px=lane_reference_trace_px,
            boundary_axis=height_axis,
        )
        if (
            not binding.role_authorized
            or binding.full_direction_interval_degrees is None
            or max(
                binding.full_direction_interval_degrees.minimum,
                anchor.full_direction_interval_degrees.minimum,
            )
            > min(
                binding.full_direction_interval_degrees.maximum,
                anchor.full_direction_interval_degrees.maximum,
            )
            + 1.0e-9
        ):
            continue
        binding = replace(
            binding,
            evidence=CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
        )
        key = str(observation.observation_id)
        observations.setdefault(key, observation)
        bindings.setdefault(key, binding)

    if len(bindings) > maximum_bindings:
        raise ValueError("cross refinement binding bound exceeded")
    ordered = tuple(
        bindings[key]
        for key in sorted(
            bindings,
            key=lambda identity: (
                bindings[identity].coordinate_interval_px.center,
                identity,
            ),
        )
    )
    ordered_observations = tuple(
        observations[key] for key in sorted(observations)
    )
    return RegisteredCrossEvidence(
        top_bindings=tuple(
            item for item in ordered if item.role == BoundaryRole.TOP
        ),
        bottom_bindings=tuple(
            item for item in ordered if item.role == BoundaryRole.BOTTOM
        ),
        observations=ordered_observations,
        fit_attempt_count=fit_attempt_count,
    )


def short_axis_center_authority(
    visible_authority_px: FiniteInterval,
    scale_authority_px_per_mm: PositiveInterval,
) -> FiniteInterval:
    return centered_short_axis_authority_px(
        visible_authority_px,
        scale_authority_px_per_mm,
    )


__all__ = [
    "RegisteredCrossEvidence",
    "register_cross_evidence",
    "register_template_local_cross_refinements",
    "short_axis_center_authority",
    "template_spec_from_physical_authority",
]
