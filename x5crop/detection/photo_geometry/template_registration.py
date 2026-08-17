"""Register the finite template inputs for one already measured lane."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

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
from .template_cross_model import CrossRoleBinding
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
    "short_axis_center_authority",
    "template_spec_from_physical_authority",
]
