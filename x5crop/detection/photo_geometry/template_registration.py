"""Register the finite template inputs for one already measured lane."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from ...domain import EvidenceState, FiniteInterval, PositiveInterval
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
from .source_geometry import SourceScanGeometry
from .template_cross_model import (
    CrossBoundaryFamilyFailureKind,
    CrossBoundaryFamilyResolution,
    CrossEvidence,
    CrossRoleBinding,
)
from .template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
    generic_separator_gap_interval_px,
)


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
        gap = generic_separator_gap_interval_px(width)
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
    registered_run_count: int | None = None
    fitted_observation_count: int | None = None
    family_resolutions: tuple[CrossBoundaryFamilyResolution, ...] = ()

    def __post_init__(self) -> None:
        identities = tuple(item.observation_id for item in self.observations)
        if len(set(identities)) != len(identities):
            raise ValueError("cross observations must be registered once")
        family_ids = tuple(item.family_id for item in self.family_resolutions)
        if len(set(family_ids)) != len(family_ids):
            raise ValueError("cross boundary families must be registered once")
        if self.fit_attempt_count < len(self.observations):
            raise ValueError("cross fit-attempt receipt is incomplete")
        binding_run_count = len(
            {
                item.run_id
                for item in (*self.top_bindings, *self.bottom_bindings)
            }
        )
        registered_run_count = (
            binding_run_count
            if self.registered_run_count is None
            else self.registered_run_count
        )
        fitted_observation_count = (
            len(self.observations)
            if self.fitted_observation_count is None
            else self.fitted_observation_count
        )
        if (
            not isinstance(registered_run_count, int)
            or registered_run_count < binding_run_count
            or not isinstance(fitted_observation_count, int)
            or fitted_observation_count < len(self.observations)
        ):
            raise ValueError("cross registration receipt is invalid")
        object.__setattr__(self, "registered_run_count", registered_run_count)
        object.__setattr__(
            self,
            "fitted_observation_count",
            fitted_observation_count,
        )


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


def _cross_family_projection_interval(
    observation: PhotoBoundaryObservation,
    *,
    reference_trace_px: float,
    boundary_axis: BoundaryAxis,
    connection_allowance_px: float,
) -> FiniteInterval:
    """Project one local line's full measured direction at one shared trace."""

    line = observation.line
    anchor_trace_px = line.support_projection_px.center
    if boundary_axis == BoundaryAxis.Y:
        normal = line.normal_y
        other = line.normal_x
    else:
        normal = line.normal_x
        other = line.normal_y
    if abs(normal) <= 1.0e-12:
        raise ValueError("cross family line cannot project at shared trace")
    anchor_coordinates = tuple(
        (offset - other * anchor_trace_px) / normal
        for offset in (
            observation.offset_interval_px.minimum,
            observation.offset_interval_px.maximum,
        )
    )
    delta_trace_px = reference_trace_px - anchor_trace_px
    slopes = tuple(
        math.tan(math.radians(angle))
        for angle in (
            observation.angle_interval_degrees.minimum,
            observation.angle_interval_degrees.maximum,
        )
    )
    projected = tuple(
        coordinate + slope * delta_trace_px
        for coordinate in anchor_coordinates
        for slope in slopes
    )
    return FiniteInterval(
        min(projected) - connection_allowance_px,
        max(projected) + connection_allowance_px,
    )


def _cross_family_components(
    values: tuple[PhotoBoundaryObservation, ...],
    *,
    measurement: PhotoBoundaryMeasurementSet,
    height_scale_px_per_mm: PositiveInterval,
) -> tuple[tuple[int, ...], ...]:
    """Group only position- and direction-compatible local line fragments."""

    if not values:
        return ()
    reference_trace_px = (
        measurement.query.trace_positions_px[0]
        + measurement.query.trace_positions_px[-1]
    ) / 2.0
    allowance_px = PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
        height_scale_px_per_mm.maximum
    )
    projections = tuple(
        _cross_family_projection_interval(
            observation,
            reference_trace_px=reference_trace_px,
            boundary_axis=measurement.query.boundary_axis,
            connection_allowance_px=allowance_px,
        )
        for observation in values
    )
    ordered = tuple(
        sorted(
            range(len(values)),
            key=lambda index: (
                projections[index].minimum,
                projections[index].maximum,
                str(values[index].observation_id),
            ),
        )
    )
    links: dict[int, set[int]] = {index: set() for index in ordered}
    active: list[int] = []
    for index in ordered:
        interval = projections[index]
        active = [
            candidate
            for candidate in active
            if projections[candidate].maximum >= interval.minimum
        ]
        for candidate in active:
            other_direction = values[candidate].angle_interval_degrees
            direction = values[index].angle_interval_degrees
            if (
                other_direction.maximum < direction.minimum
                or direction.maximum < other_direction.minimum
            ):
                continue
            links[index].add(candidate)
            links[candidate].add(index)
        active.append(index)

    components: list[tuple[int, ...]] = []
    remaining = set(ordered)
    while remaining:
        frontier = [min(remaining)]
        component: set[int] = set()
        while frontier:
            member = frontier.pop()
            if member in component:
                continue
            component.add(member)
            frontier.extend(links[member].intersection(remaining))
        remaining.difference_update(component)
        components.append(tuple(sorted(component)))
    return tuple(components)


def _merge_registered_cross_families(
    values: tuple[PhotoBoundaryObservation, ...],
    *,
    measurement: PhotoBoundaryMeasurementSet,
    role: BoundaryRole,
    width_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
) -> tuple[
    tuple[PhotoBoundaryObservation, ...],
    int,
    tuple[CrossBoundaryFamilyResolution, ...],
]:
    """Merge only a complete transition union that refits as one line.

    Transition tracking deliberately emits local segments.  Their raster
    support need not be connected: the family owner proves physical identity
    by requiring one robust refit to retain the exact transition union.  A
    refit that discards even one member transition is not identity evidence.
    """

    if len(values) < 2:
        return values, 0, ()
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
        if set(candidate.transition_ids) != set(identities):
            return None
        return candidate

    components = _cross_family_components(
        values,
        measurement=measurement,
        height_scale_px_per_mm=height_scale_px_per_mm,
    )

    merged: list[PhotoBoundaryObservation] = []
    resolutions: list[CrossBoundaryFamilyResolution] = []
    for component in components:
        if len(component) == 1:
            merged.append(values[component[0]])
            continue
        members = tuple(values[index] for index in component)
        member_observation_ids = tuple(
            sorted(
                (item.observation_id for item in members),
                key=str,
            )
        )
        member_transition_ids = tuple(
            sorted(
                {
                    identity
                    for item in members
                    for identity in item.transition_ids
                },
                key=str,
            )
        )
        family_id = physical_fact_id(
            "cross-boundary-family",
            role.value,
            *(str(identity) for identity in member_observation_ids),
        )
        observation = fit(component)
        if observation is None:
            merged.extend(members)
            resolutions.append(
                CrossBoundaryFamilyResolution(
                    family_id=family_id,
                    role=role,
                    state=EvidenceState.UNAVAILABLE,
                    member_observation_ids=member_observation_ids,
                    member_transition_ids=member_transition_ids,
                    final_observation_ids=member_observation_ids,
                    failure_kind=(
                        CrossBoundaryFamilyFailureKind
                        .COMPLETE_TRANSITION_UNION_REFIT_REJECTED
                    ),
                )
            )
        else:
            merged.append(observation)
            resolutions.append(
                CrossBoundaryFamilyResolution(
                    family_id=family_id,
                    role=role,
                    state=EvidenceState.SUPPORTED,
                    member_observation_ids=member_observation_ids,
                    member_transition_ids=member_transition_ids,
                    final_observation_ids=(observation.observation_id,),
                    failure_kind=None,
                )
            )
    return tuple(merged), attempts, tuple(resolutions)


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
        return RegisteredCrossEvidence(
            top_bindings=(),
            bottom_bindings=(),
            observations=(),
            fit_attempt_count=0,
            registered_run_count=len(qualified),
            fitted_observation_count=0,
        )
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
    family_resolutions: list[CrossBoundaryFamilyResolution] = []
    for role, measurement in (
        (BoundaryRole.TOP, top_measurement),
        (BoundaryRole.BOTTOM, bottom_measurement),
    ):
        values, attempts, resolutions = _merge_registered_cross_families(
            tuple(observations_by_role[role].values()),
            measurement=measurement,
            role=role,
            width_axis=width_axis,
            height_scale_px_per_mm=height_scale_px_per_mm,
        )
        fit_attempt_count += attempts
        merged_observations.extend(values)
        family_resolutions.extend(resolutions)
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
        registered_run_count=len(qualified),
        fitted_observation_count=len(ordered),
        family_resolutions=tuple(
            sorted(family_resolutions, key=lambda item: item.family_id)
        ),
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

    def has_direct_opposite_closure(anchor: CrossRoleBinding) -> bool:
        opposites = (
            registered.bottom_bindings
            if anchor.role == BoundaryRole.TOP
            else registered.top_bindings
        )
        expected = (
            _add(anchor.full_interval_px, fixed_height_px)
            if anchor.role == BoundaryRole.TOP
            else FiniteInterval(
                anchor.full_interval_px.minimum - fixed_height_px.maximum,
                anchor.full_interval_px.maximum - fixed_height_px.minimum,
            )
        )
        for opposite in opposites:
            if (
                opposite.evidence != CrossEvidence.DIRECT
                or not opposite.role_authorized
                or len(
                    set(anchor.trace_coordinates_px).intersection(
                        opposite.trace_coordinates_px
                    )
                )
                < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
                or expected.maximum < opposite.full_interval_px.minimum
                or opposite.full_interval_px.maximum < expected.minimum
            ):
                continue
            anchor_direction = anchor.full_direction_interval_degrees
            opposite_direction = opposite.full_direction_interval_degrees
            if (
                anchor_direction is not None
                and opposite_direction is not None
                and (
                    anchor_direction.maximum < opposite_direction.minimum
                    or opposite_direction.maximum < anchor_direction.minimum
                )
            ):
                continue
            return True
        return False

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
        # This pass only fills a physically missing opposite side.  Re-fitting
        # transitions after a direct top+bottom closure already exists would
        # duplicate the same structure under a new observation identity and
        # manufacture a discrete runner-up from non-independent evidence.
        if has_direct_opposite_closure(anchor):
            continue
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
        return RegisteredCrossEvidence(
            top_bindings=registered.top_bindings,
            bottom_bindings=registered.bottom_bindings,
            observations=registered.observations,
            fit_attempt_count=fit_attempt_count,
            registered_run_count=max(
                int(registered.registered_run_count),
                len(bindings),
            ),
            fitted_observation_count=len(bindings),
            family_resolutions=registered.family_resolutions,
        )
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
        registered_run_count=max(
            int(registered.registered_run_count),
            len({item.run_id for item in ordered}),
        ),
        fitted_observation_count=len(ordered_observations),
        family_resolutions=registered.family_resolutions,
    )
