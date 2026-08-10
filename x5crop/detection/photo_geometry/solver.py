"""Bounded joint solver for fixed-format physical placements."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from hashlib import sha256
import math

import numpy as np

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from ...formats import FRAME_DIMENSION_TOLERANCE_SPEC, FramePhysicalSpec
from ..output_geometry import (
    observed_strip_angle_estimate_degrees,
    resolve_shared_strip_direction,
)
from .boundary_geometry import (
    canonical_boundary_line,
    canonical_source_cross_axis_slope,
    canonical_source_sequence_axis_slope,
    source_cross_axis_slope_interval,
    source_sequence_axis_slope_interval,
)
from .measurement import (
    continuous_trace_support_fraction,
    fit_format_bound_boundary_observation,
    robust_scalar_location,
    track_side_transition_regions,
)
from .model import (
    BoundaryAxis,
    BoundaryRole,
    DirectionAuthority,
    FrameBoundaryGeometry,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    PositionSource,
    SharedStripDirection,
)
from .source_geometry import (
    JointAxisGeometry,
    LaneGapModel,
    SourceScanGeometry,
)
from .chains import (
    BoundRoleEvidence,
    BoundSeparatorBand,
    FixedFormatFrameSet,
    FrameChainProposals,
    CrossPlacement,
    CrossRoleEvidence,
    CompleteFormatChain,
    FixedFormatFrame,
    LaneGeometry,
    LocalAdvanceKind,
    LocalAdvanceRelation,
    CrossAxisProposal,
    RegisteredSequenceRoleQuery,
    SequencePlacement,
    SourcePlacementMaterialization,
    LaneObservationInput,
    LanePhysicalProposals,
    SequenceChainProposal,
)
from .observations import (
    BasicAxisProfile,
    SequenceRoleProposal,
    ProfileRun,
    SequenceHypothesisGroup,
    OrdinalBoundaryRole,
    build_sequence_groups,
    cross_profile_from_regions,
    group_support_exclusion_authorized,
    ordered_ordinal_roles,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _gap_seed_mm(frame_spec: FramePhysicalSpec) -> float:
    """Return a search origin, never a source-gap authority."""

    return (
        frame_spec.format_gap_prior_mm
        if frame_spec.format_gap_prior_mm is not None
        else 0.0
    )


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
    *,
    epsilon: float = 0.0,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if maximum < minimum:
        if minimum - maximum > epsilon:
            return None
        return FiniteInterval.exact((minimum + maximum) / 2.0)
    return FiniteInterval(minimum, maximum)


def _hull(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    if not values:
        raise ValueError("interval hull requires values")
    return FiniteInterval(
        min(value.minimum for value in values),
        max(value.maximum for value in values),
    )


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )


def _subtract(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _common(values: tuple[FiniteInterval, ...]) -> FiniteInterval | None:
    if not values:
        return None
    minimum = max(value.minimum for value in values)
    maximum = min(value.maximum for value in values)
    return None if maximum < minimum else FiniteInterval(minimum, maximum)


def _conditional_fit_and_full(
    fit_values: tuple[FiniteInterval, ...],
    full_values: tuple[FiniteInterval, ...],
) -> tuple[FiniteInterval, FiniteInterval] | None:
    """Keep the robust center as preference inside the full safety domain."""

    full = _common(full_values)
    if full is None:
        return None
    fit = _common(fit_values)
    if fit is not None:
        fit = _intersection(fit, full)
    return (full if fit is None else fit), full


def direction_class_key(direction: SharedStripDirection) -> tuple[object, ...]:
    return (
        round(direction.canonical_angle_degrees, 12),
        round(direction.full_angle_interval_degrees.minimum, 12),
        round(direction.full_angle_interval_degrees.maximum, 12),
        tuple(map(str, direction.selected_observation_ids)),
    )


def merge_sampling_equivalent_direction_classes(
    directions: tuple[SharedStripDirection, ...],
) -> tuple[SharedStripDirection, ...]:
    """Merge only direction classes that produce the exact same transform.

    The interval hull preserves every cross_proposal-bound direction interpretation;
    ordinary support or residual scores never collapse a distinct transform.
    """

    grouped: dict[float, list[SharedStripDirection]] = {}
    for direction in directions:
        grouped.setdefault(direction.canonical_angle_degrees, []).append(direction)
    merged: list[SharedStripDirection] = []
    for canonical_angle, members in grouped.items():
        observation_ids = tuple(
            sorted(
                {
                    observation_id
                    for member in members
                    for observation_id in member.selected_observation_ids
                },
                key=str,
            )
        )
        full_angle_interval = FiniteInterval(
            min(
                member.full_angle_interval_degrees.minimum
                for member in members
            ),
            max(
                member.full_angle_interval_degrees.maximum
                for member in members
            ),
        )
        merged.append(
            SharedStripDirection(
                direction_id=_stable_id(
                    "cross_proposal-direction-class",
                    canonical_angle,
                    full_angle_interval.minimum,
                    full_angle_interval.maximum,
                    *(str(identity) for identity in observation_ids),
                ),
                selected_observation_ids=observation_ids,
                full_angle_interval_degrees=full_angle_interval,
                canonical_angle_degrees=canonical_angle,
            )
        )
    return tuple(sorted(merged, key=direction_class_key))


def _physical_bound_direction_classes(
    cross_proposals: tuple[CrossAxisProposal, ...],
) -> tuple[SharedStripDirection, ...]:
    directions: list[SharedStripDirection] = []
    for cross_proposal in cross_proposals:
        fit_intervals = tuple(
            item.fit_angle_interval_degrees
            for item in cross_proposal.raw_observations
            if item.fit_angle_interval_degrees is not None
        )
        if len(fit_intervals) != len(cross_proposal.raw_observations):
            raise ValueError("cross_proposal direction lacks fit intervals")
        resolution = resolve_shared_strip_direction(cross_proposal.raw_observations)
        if resolution.direction is not None:
            hull = _hull(
                tuple(
                    item.angle_interval_degrees
                    for item in cross_proposal.raw_observations
                )
            )
            if _hull(fit_intervals).width > (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
            ):
                continue
            directions.append(
                SharedStripDirection(
                    direction_id=_stable_id(
                        "cross_proposal-direction-safety-hull",
                        resolution.direction.direction_id,
                        hull.minimum,
                        hull.maximum,
                    ),
                    selected_observation_ids=(
                        resolution.direction.selected_observation_ids
                    ),
                    full_angle_interval_degrees=hull,
                    canonical_angle_degrees=(
                        resolution.direction.canonical_angle_degrees
                    ),
                )
            )
            continue
        full_intervals = tuple(
            item.angle_interval_degrees
            for item in cross_proposal.raw_observations
        )
        if len(fit_intervals) < 2:
            continue
        fit_hull = _hull(fit_intervals)
        if fit_hull.width > (
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
        ):
            continue
        hull = _hull(full_intervals)
        canonical = observed_strip_angle_estimate_degrees(
            cross_proposal.raw_observations
        )
        canonical = min(
            fit_hull.maximum,
            max(fit_hull.minimum, canonical),
        )
        identities = tuple(
            sorted(
                (
                    item.observation_id
                    for item in cross_proposal.raw_observations
                ),
                key=str,
            )
        )
        directions.append(
            SharedStripDirection(
                direction_id=_stable_id(
                    "bounded-cross_proposal-direction",
                    hull.minimum,
                    hull.maximum,
                    canonical,
                    *(str(identity) for identity in identities),
                ),
                selected_observation_ids=identities,
                full_angle_interval_degrees=hull,
                canonical_angle_degrees=canonical,
            )
        )
    return merge_sampling_equivalent_direction_classes(tuple(directions))


def _role_relative_projection(
    role: OrdinalBoundaryRole,
    frame_spec: FramePhysicalSpec,
    width_state: JointAxisGeometry,
    gap_model: LaneGapModel | None = None,
) -> FiniteInterval:
    index = role.lane_ordinal - 1
    width_count = index + (1 if role.role == BoundaryRole.END else 0)
    width = width_state.project_affine(
        q_coefficient=width_count * frame_spec.frame_width_mm,
        scale_coefficient=0.0,
    )
    gap = (
        gap_model.gap_interval_px
        if gap_model is not None
        and gap_model.state == EvidenceState.SUPPORTED
        and gap_model.gap_interval_px is not None
        else width_state.project_affine(
            q_coefficient=0.0,
            scale_coefficient=_gap_seed_mm(frame_spec),
        )
    )
    return _add(
        width,
        FiniteInterval(index * gap.minimum, index * gap.maximum),
    )


def _role_canonical_relative(
    role: OrdinalBoundaryRole,
    frame_spec: FramePhysicalSpec,
    width_state: JointAxisGeometry,
    gap_model: LaneGapModel | None = None,
) -> float:
    scale, normalized, _factor = width_state.canonical_state()
    index = role.lane_ordinal - 1
    return (
        (index + (1 if role.role == BoundaryRole.END else 0))
        * frame_spec.frame_width_mm
        * normalized
        + index
        * (
            gap_model.canonical_placement_pitch_px
            - width_state.extent_projection_px().center
            if gap_model is not None
            and gap_model.state == EvidenceState.SUPPORTED
            else _gap_seed_mm(frame_spec) * scale
        )
    )


def _role_affine_coefficients(
    role: OrdinalBoundaryRole,
    frame_spec: FramePhysicalSpec,
) -> tuple[float, float]:
    index = role.lane_ordinal - 1
    return (
        (
            index
            + (1 if role.role == BoundaryRole.END else 0)
        )
        * frame_spec.frame_width_mm,
        index * _gap_seed_mm(frame_spec),
    )


def _sequence_role_proposals(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    roles: tuple[OrdinalBoundaryRole, ...],
) -> tuple[SequenceRoleProposal, ...]:
    runs = {run.run_id: run for run in lane.sequence_profile.runs}
    values: list[SequenceRoleProposal] = []
    for region in lane.sequence_profile.runs:
        run = runs[region.run_id]
        for role in roles:
            if not run.anchor_qualified_for(role.role):
                continue
            relative = _role_relative_projection(
                role,
                geometry.frame_spec,
                geometry.width_state,
            )
            values.append(
                SequenceRoleProposal(
                    proposal_id=_stable_id(
                        "phase-proposal",
                        geometry.frame_spec.frame_spec_id,
                        run.run_id,
                        role.role_index,
                    ),
                    run_id=run.run_id,
                    role=role,
                    phase_interval_px=_subtract(
                        run.coordinate_interval_px,
                        relative,
                    ),
                    transition_ids=run.transition_ids,
                    role_coordinate_px=_role_canonical_relative(
                        role,
                        geometry.frame_spec,
                        geometry.width_state,
                    ),
                )
            )
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.proposal_id))
    )


def _line_boundary_coordinate(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> float:
    line = observation.line
    if boundary_axis == BoundaryAxis.Y:
        if abs(line.normal_y) <= 1.0e-12:
            raise ValueError("cross-boundary line cannot project y")
        return (
            line.offset_px - line.normal_x * trace_coordinate_px
        ) / line.normal_y
    if abs(line.normal_x) <= 1.0e-12:
        raise ValueError("cross-boundary line cannot project x")
    return (
        line.offset_px - line.normal_y * trace_coordinate_px
    ) / line.normal_x


def reference_role_transition_ids(
    measurement_set: PhotoBoundaryMeasurementSet,
    *,
    target_coordinate_px: float,
    equivalence_px: float,
) -> tuple[ObservationId, ...]:
    """Bind one unambiguous measured transition per registered trace.

    The physical cross_proposal reference proposes where to look inside the already
    completed query.  It does not create evidence: a trace is omitted whenever
    its two nearest transitions are indistinguishable at the frozen geometry
    equivalence scale.
    """

    if not math.isfinite(target_coordinate_px) or equivalence_px <= 0.0:
        raise ValueError("reference transition proposal is invalid")
    by_trace: dict[int, list[PhotoBoundaryTransition]] = {}
    for transition in measurement_set.transitions:
        by_trace.setdefault(transition.trace_coordinate_px, []).append(
            transition
        )
    selected: list[ObservationId] = []
    for trace in measurement_set.query.trace_positions_px:
        ordered = sorted(
            by_trace.get(trace, ()),
            key=lambda item: (
                abs(item.coordinate_px - target_coordinate_px),
                str(item.transition_id),
            ),
        )
        if not ordered:
            continue
        if (
            len(ordered) > 1
            and abs(
                abs(ordered[1].coordinate_px - target_coordinate_px)
                - abs(ordered[0].coordinate_px - target_coordinate_px)
            )
            <= equivalence_px
        ):
            continue
        selected.append(ordered[0].transition_id)
    return tuple(selected)


def _observation_coordinate_interval(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> FiniteInterval:
    line = observation.line
    if boundary_axis == BoundaryAxis.Y:
        normal = line.normal_y
        other = line.normal_x
    else:
        normal = line.normal_x
        other = line.normal_y
    if abs(normal) <= 1.0e-12:
        raise ValueError("cross-boundary line cannot project coordinate")
    values = tuple(
        (offset - other * trace_coordinate_px) / normal
        for offset in (
            observation.offset_interval_px.minimum,
            observation.offset_interval_px.maximum,
        )
    )
    return FiniteInterval(min(values), max(values))


def _reference_role_run(
    lane: LaneObservationInput,
    *,
    role: BoundaryRole,
    measurement_set: PhotoBoundaryMeasurementSet,
    target_coordinate_px: float,
    equivalence_px: float,
    support_interval_px: FiniteInterval | None = None,
) -> tuple[ProfileRun, PhotoBoundaryObservation] | None:
    transition_ids = reference_role_transition_ids(
        measurement_set,
        target_coordinate_px=target_coordinate_px,
        equivalence_px=equivalence_px,
    )
    observation = fit_format_bound_boundary_observation(
        measurement_set,
        transition_ids=transition_ids,
        role=role,
        source_axis_long=lane.width_axis,
        boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
        minimum_trace_fraction=(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
        ),
        support_interval_px=support_interval_px,
    )
    if observation is None:
        return None
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    role_preference = (
        observation.left_background_preference_fraction
        if role == BoundaryRole.TOP
        else observation.right_background_preference_fraction
    )
    if (
        observation.background_side_support_fraction
        < spec.directional_background_support_minimum
        or role_preference < spec.directional_role_preference_minimum
    ):
        return None
    selected = tuple(
        transition
        for transition in measurement_set.transitions
        if transition.transition_id in set(observation.transition_ids)
    )
    traces = tuple(
        sorted({transition.trace_coordinate_px for transition in selected})
    )
    queried = tuple(
        trace
        for trace in measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(float(trace), epsilon=0.5)
    )
    return (
        ProfileRun(
            run_id=_stable_id(
                "reference-role-run",
                role.value,
                *(str(identity) for identity in observation.transition_ids),
            ),
            coordinate_interval_px=_observation_coordinate_interval(
                observation,
                boundary_axis=lane.height_axis,
                trace_coordinate_px=lane.width_authority_px.center,
            ),
            transition_ids=observation.transition_ids,
            trace_coordinates_px=traces,
            role_hint=role,
            qualified_anchor_roles=(),
            support_fraction=len(traces) / len(queried),
            continuous_support_fraction=(
                observation.continuous_support_fraction
            ),
            fit_residual_px=observation.fit_residual_px,
            evidence_strength=sum(
                transition.gradient_z
                + max(transition.tone_z, transition.texture_z)
                for transition in selected
            )
            / len(selected),
            pair_qualified=True,
        ),
        observation,
    )


def _inlier_profile_run(
    lane: LaneObservationInput,
    run: ProfileRun,
    observation: PhotoBoundaryObservation,
    measurement_set: PhotoBoundaryMeasurementSet,
    support_interval_px: FiniteInterval | None = None,
) -> ProfileRun:
    selected = tuple(
        transition
        for transition in measurement_set.transitions
        if transition.transition_id in set(observation.transition_ids)
    )
    traces = tuple(
        sorted({transition.trace_coordinate_px for transition in selected})
    )
    queried = tuple(
        trace
        for trace in measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(float(trace), epsilon=0.5)
    )
    return ProfileRun(
        run_id=_stable_id(
            "inlier-profile-run",
            run.run_id,
            observation.observation_id,
        ),
        coordinate_interval_px=_observation_coordinate_interval(
            observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=lane.width_authority_px.center,
        ),
        transition_ids=observation.transition_ids,
        trace_coordinates_px=traces,
        role_hint=run.role_hint,
        qualified_anchor_roles=run.qualified_anchor_roles,
        support_fraction=(
            observation.trace_support_count / len(queried)
        ),
        continuous_support_fraction=(
            observation.continuous_support_fraction
        ),
        fit_residual_px=observation.fit_residual_px,
        evidence_strength=sum(
            transition.gradient_z
            + max(transition.tone_z, transition.texture_z)
            for transition in selected
        )
        / len(selected),
        pair_qualified=run.pair_qualified,
    )


def _reference_pair_cross_proposal(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    broad_height: FiniteInterval,
    *,
    support_interval_px: FiniteInterval | None = None,
) -> CrossAxisProposal | None:
    height = geometry.height_state.extent_projection_px()
    center = lane.height_authority_px.center
    equivalence_px = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.geometry_equivalence_mm
        * lane.height_scale_px_per_mm.maximum
    )
    top = _reference_role_run(
        lane,
        role=BoundaryRole.TOP,
        measurement_set=lane.top_measurement_set,
        target_coordinate_px=center - height.center / 2.0,
        equivalence_px=equivalence_px,
        support_interval_px=support_interval_px,
    )
    bottom = _reference_role_run(
        lane,
        role=BoundaryRole.BOTTOM,
        measurement_set=lane.bottom_measurement_set,
        target_coordinate_px=center + height.center / 2.0,
        equivalence_px=equivalence_px,
        support_interval_px=support_interval_px,
    )
    if top is None or bottom is None:
        return None
    polarities = tuple(
        (
            1
            if sum(value > 0 for value in values)
            > sum(value < 0 for value in values)
            else -1
        )
        for run in (top[0], bottom[0])
        for values in (
            tuple(
                lane.transition_by_id[str(identity)].polarity
                for identity in run.transition_ids
                if lane.transition_by_id[str(identity)].polarity != 0
            ),
        )
        if values
    )
    if len(polarities) != 2 or polarities[0] != -polarities[1]:
        return None
    origin = _intersection(
        top[0].coordinate_interval_px,
        _subtract(bottom[0].coordinate_interval_px, broad_height),
    )
    if origin is None:
        return None
    angle_hull = _hull(
        (top[1].angle_interval_degrees, bottom[1].angle_interval_degrees)
    )
    if (
        angle_hull.width
        > PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
    ):
        return None
    return CrossAxisProposal(
        cross_proposal_id=_stable_id(
            "reference-pair-height-cross_proposal",
            geometry.frame_spec.frame_spec_id,
            top[0].run_id,
            bottom[0].run_id,
        ),
        frame_spec_id=geometry.frame_spec.frame_spec_id,
        origin_interval_px=origin,
        observed_runs=(top[0], bottom[0]),
        raw_observations=(top[1], bottom[1]),
    )


def _format_bound_opposite_run(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    top_run: ProfileRun,
    top_observation: PhotoBoundaryObservation,
    support_interval_px: FiniteInterval | None = None,
) -> ProfileRun | None:
    """Bind bottom transitions through the top edge and height cross_proposal.

    The bottom query is registered and executed before this function.  This
    stage only groups its existing transitions against one fixed physical
    height; it does not widen coverage or create another query authority.
    """

    height = geometry.height_state.extent_projection_px()
    by_trace: dict[int, list[PhotoBoundaryTransition]] = {}
    top_transitions = tuple(
        transition
        for identity in top_run.transition_ids
        if (
            transition := lane.transition_by_id.get(str(identity))
        )
        is not None
    )
    top_polarities = tuple(
        transition.polarity
        for transition in top_transitions
        if transition.polarity != 0
    )
    if not top_polarities:
        return None
    top_polarity = (
        1
        if sum(value > 0 for value in top_polarities)
        > sum(value < 0 for value in top_polarities)
        else -1
    )
    for transition in lane.bottom_measurement_set.transitions:
        if (
            support_interval_px is not None
            and not support_interval_px.contains(
                float(transition.trace_coordinate_px),
                epsilon=0.5,
            )
        ):
            continue
        if transition.polarity != -top_polarity:
            continue
        top_coordinate = _line_boundary_coordinate(
            top_observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=float(transition.trace_coordinate_px),
        )
        implied = _subtract(
            transition.coordinate_interval_px,
            FiniteInterval.exact(top_coordinate),
        )
        if _intersection(implied, height) is not None:
            by_trace.setdefault(
                transition.trace_coordinate_px,
                [],
            ).append(transition)

    selected: list[PhotoBoundaryTransition] = []
    for trace in lane.bottom_measurement_set.query.trace_positions_px:
        values = by_trace.get(trace, ())
        if not values:
            continue
        ordered = sorted(
            values,
            key=lambda item: (
                -item.coordinate_px,
                str(item.transition_id),
            ),
        )
        if (
            len(ordered) > 1
            and math.isclose(
                ordered[0].coordinate_px,
                ordered[1].coordinate_px,
                abs_tol=1.0e-9,
            )
        ):
            continue
        selected.append(ordered[0])

    queried = tuple(
        trace
        for trace in lane.bottom_measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(float(trace), epsilon=0.5)
    )
    minimum = max(
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_trace_count,
        math.ceil(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
            * len(queried)
        ),
    )
    if len(selected) < minimum:
        return None
    reference = lane.width_authority_px.center
    top_reference = _line_boundary_coordinate(
        top_observation,
        boundary_axis=lane.height_axis,
        trace_coordinate_px=reference,
    )
    projected: list[FiniteInterval] = []
    for transition in selected:
        top_at_trace = _line_boundary_coordinate(
            top_observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=float(transition.trace_coordinate_px),
        )
        projected.append(
            _add(
                transition.coordinate_interval_px,
                FiniteInterval.exact(top_reference - top_at_trace),
            )
        )
    centers = sorted(value.center for value in projected)
    center = centers[len(centers) // 2]
    deviations = sorted(abs(value - center) for value in centers)
    mad = deviations[len(deviations) // 2]
    half_width = max(value.width / 2.0 for value in projected)
    interval = FiniteInterval(
        center - 3.0 * mad - half_width,
        center + 3.0 * mad + half_width,
    )
    traces = tuple(sorted(item.trace_coordinate_px for item in selected))
    continuity = continuous_trace_support_fraction(queried, traces)
    return ProfileRun(
        run_id=_stable_id(
            "cross_proposal-bound-opposite-run",
            geometry.frame_spec.frame_spec_id,
            top_observation.observation_id,
            *(str(item.transition_id) for item in selected),
        ),
        coordinate_interval_px=interval,
        transition_ids=tuple(
            sorted(
                (item.transition_id for item in selected),
                key=str,
            )
        ),
        trace_coordinates_px=traces,
        role_hint=BoundaryRole.BOTTOM,
        qualified_anchor_roles=(),
        support_fraction=len(selected) / len(queried),
        continuous_support_fraction=continuity,
        fit_residual_px=mad,
        evidence_strength=sum(
            item.gradient_z + max(item.tone_z, item.texture_z)
            for item in selected
        )
        / len(selected),
        pair_qualified=True,
    )


def _cross_pair_seed_qualified(run: ProfileRun) -> bool:
    """Admit a measured edge only as one half of a complete physical pair."""

    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    return (
        run.role_hint in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        and run.support_fraction >= spec.minimum_cross_trace_fraction
        and run.continuous_support_fraction
        >= spec.minimum_continuous_support_fraction
    )


def build_cross_axis_proposals(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    *,
    support_interval_px: FiniteInterval | None = None,
) -> tuple[CrossAxisProposal, ...]:
    allowance_mm = PHOTO_BOUNDARY_MEASUREMENT_SPEC.dimension_search_allowance_mm
    scale = geometry.height_state.scale_authority
    broad_height = FiniteInterval(
        max(0.0, geometry.frame_spec.frame_height_mm - allowance_mm)
        * scale.minimum,
        (geometry.frame_spec.frame_height_mm + allowance_mm) * scale.maximum,
    )
    fit_cache: dict[tuple[BoundaryRole, str], PhotoBoundaryObservation | None] = {}
    fitted: dict[
        BoundaryRole,
        list[tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval]],
    ] = {BoundaryRole.TOP: [], BoundaryRole.BOTTOM: []}
    for role, measurement_set in (
        (BoundaryRole.TOP, lane.top_measurement_set),
        (BoundaryRole.BOTTOM, lane.bottom_measurement_set),
    ):
        for run in lane.cross_profile.runs:
            if (
                run.role_hint != role
                or not (
                    run.pair_qualified
                    or run.anchor_qualified_for(role)
                    or _cross_pair_seed_qualified(run)
                )
            ):
                continue
            key = (role, run.run_id)
            if key not in fit_cache:
                fit_cache[key] = fit_format_bound_boundary_observation(
                    measurement_set,
                    transition_ids=run.transition_ids,
                    role=role,
                    source_axis_long=lane.width_axis,
                    boundary_axis_scale_px_per_mm=(
                        lane.height_scale_px_per_mm
                    ),
                    minimum_trace_fraction=(
                        PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
                    ),
                    support_interval_px=support_interval_px,
                )
            observation = fit_cache[key]
            if observation is None:
                continue
            run = _inlier_profile_run(
                lane,
                run,
                observation,
                measurement_set,
                support_interval_px,
            )
            origin = (
                run.coordinate_interval_px
                if role == BoundaryRole.TOP
                else _subtract(run.coordinate_interval_px, broad_height)
            )
            fitted[role].append((run, observation, origin))
    for top_run, top_observation, _top_origin in tuple(
        fitted[BoundaryRole.TOP]
    ):
        bottom_run = _format_bound_opposite_run(
            lane,
            geometry,
            top_run,
            top_observation,
            support_interval_px,
        )
        if bottom_run is None:
            continue
        bottom_observation = fit_format_bound_boundary_observation(
            lane.bottom_measurement_set,
            transition_ids=bottom_run.transition_ids,
            role=BoundaryRole.BOTTOM,
            source_axis_long=lane.width_axis,
            boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
            minimum_trace_fraction=(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
            ),
            support_interval_px=support_interval_px,
        )
        if bottom_observation is None:
            continue
        if bottom_observation.background_side_support_fraction < (
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.directional_background_support_minimum
        ):
            continue
        bottom_run = _inlier_profile_run(
            lane,
            bottom_run,
            bottom_observation,
            lane.bottom_measurement_set,
            support_interval_px,
        )
        fitted[BoundaryRole.BOTTOM].append(
            (
                bottom_run,
                bottom_observation,
                _subtract(bottom_run.coordinate_interval_px, broad_height),
            )
        )
    for role in fitted:
        fitted[role].sort(
            key=lambda item: (item[2].center, item[0].run_id)
        )

    cross_proposals: list[CrossAxisProposal] = []
    bottom_values = fitted[BoundaryRole.BOTTOM]
    bottom_centers = tuple(item[2].center for item in bottom_values)
    maximum_bottom_half_width = max(
        (item[2].width / 2.0 for item in bottom_values),
        default=0.0,
    )
    for top in fitted[BoundaryRole.TOP]:
        top_origin = top[2]
        start = bisect_left(
            bottom_centers,
            top_origin.minimum - maximum_bottom_half_width,
        )
        stop = bisect_right(
            bottom_centers,
            top_origin.maximum + maximum_bottom_half_width,
        )
        for bottom in bottom_values[start:stop]:
            origin = _intersection(top_origin, bottom[2])
            if origin is None:
                continue
            cross_proposals.append(
                CrossAxisProposal(
                    cross_proposal_id=_stable_id(
                        "provisional-height-cross_proposal",
                        geometry.frame_spec.frame_spec_id,
                        top[0].run_id,
                        bottom[0].run_id,
                    ),
                    frame_spec_id=geometry.frame_spec.frame_spec_id,
                    origin_interval_px=origin,
                    observed_runs=(top[0], bottom[0]),
                    raw_observations=(top[1], bottom[1]),
                )
            )
    for values in fitted.values():
        for run, observation, origin in values:
            if not run.anchor_qualified_for(run.role_hint):
                continue
            cross_proposals.append(
                CrossAxisProposal(
                    cross_proposal_id=_stable_id(
                        "provisional-height-cross_proposal",
                        geometry.frame_spec.frame_spec_id,
                        run.run_id,
                    ),
                    frame_spec_id=geometry.frame_spec.frame_spec_id,
                    origin_interval_px=origin,
                    observed_runs=(run,),
                    raw_observations=(observation,),
                )
            )
    if not cross_proposals:
        reference_pair = _reference_pair_cross_proposal(
            lane,
            geometry,
            broad_height,
            support_interval_px=support_interval_px,
        )
        if reference_pair is not None:
            cross_proposals.append(reference_pair)
    unique = {item.cross_proposal_id: item for item in cross_proposals}
    return tuple(unique[key] for key in sorted(unique))


def build_lane_physical_proposals(
    lane: LaneObservationInput,
    frame_spec: FramePhysicalSpec,
) -> LanePhysicalProposals:
    geometry = SourceScanGeometry.create(
        frame_spec,
        width_scale_px_per_mm=lane.width_scale_px_per_mm,
        height_scale_px_per_mm=lane.height_scale_px_per_mm,
    )
    roles = ordered_ordinal_roles(lane.output_slot_count)
    proposals = _sequence_role_proposals(lane, geometry, roles)
    groups, work = build_sequence_groups(
        proposals,
        roles,
        frame_width_lower_px=geometry.width_state.extent_projection_px().minimum,
    )
    cross_proposals = build_cross_axis_proposals(lane, geometry)
    frame_proposals = (
        ()
        if not groups
        else (
            FrameChainProposals(
                frame_spec=frame_spec,
                initial_source_scan_geometry=geometry,
                roles=roles,
                role_proposals=proposals,
                sequence_groups=groups,
                registered_sequence_role_queries=(),
                cross_proposals=cross_proposals,
                grouping_work=work,
            ),
        )
    )
    observations = tuple(
        {
            str(observation.observation_id): observation
            for cross_proposal in cross_proposals
            for observation in cross_proposal.raw_observations
        }.values()
    )
    directions = _physical_bound_direction_classes(cross_proposals)
    return LanePhysicalProposals(
        lane=lane,
        frame_proposals=frame_proposals,
        raw_top_bottom_observations=tuple(
            sorted(observations, key=lambda item: str(item.observation_id))
        ),
        direction_classes=tuple(
            sorted(directions, key=direction_class_key)
        ),
    )


def shared_source_direction_classes(
    lane_proposals: tuple[LanePhysicalProposals, ...],
) -> tuple[SharedStripDirection, ...]:
    if not lane_proposals:
        return ()
    if any(not lane.direction_classes for lane in lane_proposals):
        return ()
    if (
        len(lane_proposals) == 1
        and len(lane_proposals[0].direction_classes) == 1
    ):
        return lane_proposals[0].direction_classes
    selected_ids = {
        str(identity)
        for lane in lane_proposals
        for direction in lane.direction_classes
        for identity in direction.selected_observation_ids
    }
    observations = tuple(
        observation
        for lane in lane_proposals
        for observation in lane.raw_top_bottom_observations
        if str(observation.observation_id) in selected_ids
    )
    directions = tuple(
        direction
        for lane in lane_proposals
        for direction in lane.direction_classes
    )
    if len(lane_proposals) > 1 or any(
        len(lane.direction_classes) > 1 for lane in lane_proposals
    ):
        hull = FiniteInterval(
            min(
                direction.full_angle_interval_degrees.minimum
                for direction in directions
            ),
            max(
                direction.full_angle_interval_degrees.maximum
                for direction in directions
            ),
        )
        if (
            max(
                direction.canonical_angle_degrees
                for direction in directions
            )
            - min(
                direction.canonical_angle_degrees
                for direction in directions
            )
            > PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
        ):
            return tuple(sorted(directions, key=direction_class_key))
        canonical = observed_strip_angle_estimate_degrees(observations)
        canonical = min(hull.maximum, max(hull.minimum, canonical))
        observation_ids = tuple(
            sorted(
                (observation.observation_id for observation in observations),
                key=str,
            )
        )
        return (
            SharedStripDirection(
                direction_id=_stable_id(
                    "bounded-shared-direction",
                    hull.minimum,
                    hull.maximum,
                    canonical,
                    *(str(identity) for identity in observation_ids),
                ),
                selected_observation_ids=observation_ids,
                full_angle_interval_degrees=hull,
                canonical_angle_degrees=canonical,
            ),
        )
    resolution = resolve_shared_strip_direction(observations)
    return () if resolution.direction is None else (resolution.direction,)


def lane_directions_within_source_family(
    lane_proposals: tuple[LanePhysicalProposals, ...],
    source_direction: SharedStripDirection,
) -> tuple[SharedStripDirection, ...]:
    lane_directions: list[SharedStripDirection] = []
    for lane in lane_proposals:
        compatible = tuple(
            direction
            for direction in lane.direction_classes
            if _intersection(
                direction.full_angle_interval_degrees,
                source_direction.full_angle_interval_degrees,
            )
            is not None
            and abs(
                direction.canonical_angle_degrees
                - source_direction.canonical_angle_degrees
            )
            <= PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
        )
        if len(compatible) != 1:
            return ()
        lane_directions.append(compatible[0])
    return tuple(lane_directions)


@dataclass(frozen=True)
class _BoundRunProjection:
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-8,
            )
        ):
            raise ValueError("bound run projection is invalid")


def _project_profile_run(
    run: ProfileRun,
    *,
    transitions: dict[str, PhotoBoundaryTransition],
    direction: SharedStripDirection,
    boundary_axis: BoundaryAxis,
    source_width_axis: BoundaryAxis,
    reference_trace_px: float,
    boundary_scale_px_per_mm: PositiveInterval,
) -> _BoundRunProjection:
    try:
        bound = tuple(transitions[str(identity)] for identity in run.transition_ids)
    except KeyError as exc:
        raise ValueError("profile run transition is unavailable") from exc
    if not bound:
        raise ValueError("profile run has no transition evidence")
    if boundary_axis == source_width_axis:
        canonical_slope = canonical_source_sequence_axis_slope(
            direction,
            source_width_axis,
        )
        slope_interval = source_sequence_axis_slope_interval(
            direction,
            source_width_axis,
        )
    else:
        canonical_slope = canonical_source_cross_axis_slope(
            direction,
            boundary_axis,
        )
        slope_interval = source_cross_axis_slope_interval(
            direction,
            boundary_axis,
        )
    centers = tuple(
        transition.coordinate_px
        + canonical_slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition in bound
    )
    weights = tuple(
        max(
            1.0,
            transition.gradient_z
            + max(transition.tone_z, transition.texture_z),
        )
        for transition in bound
    )
    canonical = robust_scalar_location(
        centers,
        weights,
        boundary_scale_px_per_mm,
    )
    residuals = tuple(value - canonical for value in centers)
    center = sorted(residuals)[len(residuals) // 2]
    absolute = sorted(abs(value - center) for value in residuals)
    mad = absolute[len(absolute) // 2]
    numeric = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.transition_coordinate_sampling_uncertainty_px
    )
    fit_uncertainty = mad / math.sqrt(len(bound)) + numeric
    fit = FiniteInterval(
        canonical - fit_uncertainty,
        canonical + fit_uncertainty,
    )
    projected = tuple(
        coordinate
        + slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition in bound
        for coordinate in (
            transition.coordinate_interval_px.minimum,
            transition.coordinate_interval_px.maximum,
        )
        for slope in (slope_interval.minimum, slope_interval.maximum)
    )
    full = FiniteInterval(
        min(projected) - numeric,
        max(projected) + numeric,
    )
    if not full.contains(canonical, epsilon=1.0e-8):
        raise ValueError("canonical run position escaped exact projection")
    full = _hull((full, fit))
    return _BoundRunProjection(canonical, fit, full)


def _background_preference(run: ProfileRun, role: BoundaryRole) -> float:
    del role
    # Directional role preference already belongs to anchor qualification.
    # Canonical ranking uses only the format-neutral strength retained here.
    return min(1.0, run.evidence_strength / 12.0)


def _registered_sequence_transition_index(
    lane: LaneObservationInput,
    direction: SharedStripDirection,
) -> dict[int, tuple[tuple[float, PhotoBoundaryTransition], ...]]:
    sequence_query_ids = {
        item.query.query_id for item in lane.sequence_measurement_sets
    }
    canonical_slope = canonical_source_sequence_axis_slope(
        direction,
        lane.width_axis,
    )
    reference = lane.height_authority_px.center
    values: dict[int, list[tuple[float, PhotoBoundaryTransition]]] = {}
    for transition in lane.transition_by_id.values():
        if transition.query_id not in sequence_query_ids:
            continue
        projected = transition.coordinate_px + canonical_slope * (
            reference - float(transition.trace_coordinate_px)
        )
        values.setdefault(transition.trace_coordinate_px, []).append(
            (projected, transition)
        )
    return {
        trace: tuple(
            sorted(items, key=lambda item: (item[0], str(item[1].transition_id)))
        )
        for trace, items in values.items()
    }


def _register_sequence_role_queries(
    proposal: LanePhysicalProposals,
) -> LanePhysicalProposals:
    frame_specs: list[FrameChainProposals] = []
    search_allowance_px = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.center_offset_allowance_mm
        * proposal.lane.width_scale_px_per_mm.maximum
    )
    for frame_spec in proposal.frame_proposals:
        queries = tuple(
            RegisteredSequenceRoleQuery(
                query_id=_stable_id(
                    "registered-sequence-role-query",
                    seed.chain_proposal_id,
                    role.role_index,
                ),
                chain_proposal_id=seed.chain_proposal_id,
                role=role,
                target_interval_px=_add(
                    _add(
                        _add(
                            seed.base_phase_interval_px,
                            _role_relative_projection(
                                role,
                                frame_spec.frame_spec,
                                frame_spec.initial_source_scan_geometry.width_state,
                            ),
                        ),
                        local_advance_prefix(
                            seed.local_advance_relations,
                            lane_ordinal=role.lane_ordinal,
                        )[0],
                    ),
                    FiniteInterval(
                        -search_allowance_px,
                        search_allowance_px,
                    ),
                ),
            )
            for seed in build_sequence_chain_proposals(frame_spec)
            for role in frame_spec.roles
        )
        frame_specs.append(
            replace(
                frame_spec,
                registered_sequence_role_queries=queries,
            )
        )
    return replace(proposal, frame_proposals=tuple(frame_specs))


def _registered_sequence_role_run(
    lane: LaneObservationInput,
    query: RegisteredSequenceRoleQuery,
    direction: SharedStripDirection,
    transition_index: dict[
        int,
        tuple[tuple[float, PhotoBoundaryTransition], ...],
    ],
) -> ProfileRun | None:
    """Bind an existing registered transition field to one cross_proposal role."""

    slope_interval = source_sequence_axis_slope_interval(
        direction,
        lane.width_axis,
    )
    reference = lane.height_authority_px.center
    by_trace: dict[int, list[tuple[float, PhotoBoundaryTransition]]] = {}
    for trace, indexed in transition_index.items():
        coordinates = tuple(item[0] for item in indexed)
        start = bisect_left(coordinates, query.target_interval_px.minimum)
        stop = bisect_right(coordinates, query.target_interval_px.maximum)
        if start < stop:
            by_trace[trace] = list(indexed[start:stop])
    equivalence = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.geometry_equivalence_mm
        * lane.width_scale_px_per_mm.maximum
    )
    target = query.target_interval_px.center
    selected: list[tuple[float, PhotoBoundaryTransition]] = []
    for trace in sorted(by_trace):
        ordered = sorted(
            by_trace[trace],
            key=lambda item: (abs(item[0] - target), str(item[1].transition_id)),
        )
        if (
            len(ordered) > 1
            and abs(
                abs(ordered[1][0] - target)
                - abs(ordered[0][0] - target)
            )
            <= equivalence
        ):
            continue
        selected.append(ordered[0])
    if not selected:
        return None
    centers = sorted(item[0] for item in selected)
    center = centers[len(centers) // 2]
    connection = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_mm
        * lane.width_scale_px_per_mm.maximum
    )
    selected = tuple(
        item for item in selected if abs(item[0] - center) <= connection
    )
    queried_traces = tuple(
        sorted(
            {
                trace
                for item in lane.sequence_measurement_sets
                for trace in item.query.trace_positions_px
            }
        )
    )
    minimum = max(
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_trace_count,
        math.ceil(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
            * len(queried_traces)
        ),
    )
    if len(selected) < minimum:
        return None
    traces = tuple(sorted(item[1].trace_coordinate_px for item in selected))
    continuity = continuous_trace_support_fraction(queried_traces, traces)
    mean_gradient = sum(item[1].gradient_z for item in selected) / len(selected)
    mean_tone_or_texture = sum(
        max(item[1].tone_z, item[1].texture_z) for item in selected
    ) / len(selected)
    if (
        mean_gradient < PHOTO_BOUNDARY_MEASUREMENT_SPEC.gradient_z_minimum
        or mean_tone_or_texture
        < PHOTO_BOUNDARY_MEASUREMENT_SPEC.tone_or_texture_z_minimum
    ):
        return None
    projected_interval_values = tuple(
        coordinate
        + slope * (reference - float(transition.trace_coordinate_px))
        for _projected, transition in selected
        for coordinate in (
            transition.coordinate_interval_px.minimum,
            transition.coordinate_interval_px.maximum,
        )
        for slope in (slope_interval.minimum, slope_interval.maximum)
    )
    selected_centers = tuple(item[0] for item in selected)
    median = sorted(selected_centers)[len(selected_centers) // 2]
    residual = sorted(abs(value - median) for value in selected_centers)[
        len(selected_centers) // 2
    ]
    identities = tuple(
        sorted((item[1].transition_id for item in selected), key=str)
    )
    return ProfileRun(
        run_id=_stable_id(
            "registered-sequence-role-run",
            query.query_id,
            *(str(identity) for identity in identities),
        ),
        coordinate_interval_px=FiniteInterval(
            min(projected_interval_values),
            max(projected_interval_values),
        ),
        transition_ids=identities,
        trace_coordinates_px=traces,
        role_hint=None,
        qualified_anchor_roles=(query.role.role,),
        support_fraction=len(traces) / len(queried_traces),
        continuous_support_fraction=continuity,
        fit_residual_px=residual,
        evidence_strength=mean_gradient + mean_tone_or_texture,
        pair_qualified=True,
    )


def _bind_registered_sequence_roles(
    proposal: LanePhysicalProposals,
    direction: SharedStripDirection,
) -> tuple[LanePhysicalProposals, dict[str, ProfileRun], int]:
    queries = tuple(
        query
        for frame_spec in proposal.frame_proposals
        for query in frame_spec.registered_sequence_role_queries
    )
    if not queries:
        return proposal, {}, 0
    transition_index = _registered_sequence_transition_index(
        proposal.lane,
        direction,
    )
    runs: dict[str, ProfileRun] = {}
    for query in queries:
        run = _registered_sequence_role_run(
            proposal.lane,
            query,
            direction,
            transition_index,
        )
        if run is not None:
            runs[query.query_id] = run
    merged = {
        run.run_id: run
        for run in (
            *proposal.lane.sequence_profile.runs,
            *runs.values(),
        )
    }
    profile = BasicAxisProfile(
        "sequence",
        proposal.lane.sequence_profile.coordinate_count,
        tuple(
            sorted(
                {
                    trace
                    for run in merged.values()
                    for trace in run.trace_coordinates_px
                }
            )
        ),
        tuple(
            sorted(
                merged.values(),
                key=lambda item: (
                    item.coordinate_interval_px.center,
                    item.run_id,
                ),
            )
        ),
    )
    return (
        replace(proposal, lane=replace(proposal.lane, sequence_profile=profile)),
        runs,
        len(queries),
    )


def _registered_pair_seeds(
    lane: LaneObservationInput,
    frame_spec: FrameChainProposals,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    registered_runs: dict[str, ProfileRun],
) -> tuple[SequenceChainProposal, ...]:
    query_by_role = {
        query.role.role_index: query
        for query in frame_spec.registered_sequence_role_queries
        if query.chain_proposal_id == seed.chain_proposal_id and query.query_id in registered_runs
    }
    values: list[SequenceChainProposal] = []
    for ordinal in range(1, len(frame_spec.roles) // 2 + 1):
        roles = (
            frame_spec.roles[(ordinal - 1) * 2],
            frame_spec.roles[(ordinal - 1) * 2 + 1],
        )
        queries = tuple(query_by_role.get(role.role_index) for role in roles)
        if any(query is None for query in queries):
            continue
        runs = tuple(registered_runs[query.query_id] for query in queries)
        projections = tuple(
            _project_profile_run(
                run,
                transitions=lane.transition_by_id,
                direction=direction,
                boundary_axis=lane.width_axis,
                source_width_axis=lane.width_axis,
                reference_trace_px=lane.height_authority_px.center,
                boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
            )
            for run in runs
        )
        observed_width = _subtract(
            projections[1].fit_position_interval_px,
            projections[0].fit_position_interval_px,
        )
        if (
            _intersection(
                observed_width,
                frame_spec.initial_source_scan_geometry.width_state.extent_projection_px(),
            )
            is None
        ):
            continue
        proposals: list[SequenceRoleProposal] = []
        phase_intervals: list[FiniteInterval] = [seed.base_phase_interval_px]
        for role, run in zip(roles, runs, strict=True):
            prefix, _canonical_prefix = local_advance_prefix(
                seed.local_advance_relations,
                lane_ordinal=role.lane_ordinal,
            )
            phase = _subtract(
                _subtract(
                    run.coordinate_interval_px,
                    _role_relative_projection(
                        role,
                        frame_spec.frame_spec,
                        frame_spec.initial_source_scan_geometry.width_state,
                    ),
                ),
                prefix,
            )
            phase_intervals.append(phase)
            proposals.append(
                SequenceRoleProposal(
                    proposal_id=_stable_id(
                        "registered-sequence-role-proposal",
                        seed.chain_proposal_id,
                        role.role_index,
                        run.run_id,
                    ),
                    run_id=run.run_id,
                    role=role,
                    phase_interval_px=phase,
                    transition_ids=run.transition_ids,
                    role_coordinate_px=_role_canonical_relative(
                        role,
                        frame_spec.frame_spec,
                        frame_spec.initial_source_scan_geometry.width_state,
                    ),
                )
            )
        phase = _common(tuple(phase_intervals))
        if phase is None:
            continue
        relation_candidates: list[LocalAdvanceRelation] = []
        original_evidence = _materialized_role_evidence(
            lane,
            seed.role_proposals,
            direction,
        )
        for observation in original_evidence:
            if (
                observation.role.role != BoundaryRole.START
                or abs(observation.role.lane_ordinal - ordinal) != 1
            ):
                continue
            if observation.role.lane_ordinal < ordinal:
                advance = _subtract(
                    projections[0].fit_position_interval_px,
                    observation.fit_position_interval_px,
                )
                relation_ordinal = observation.role.lane_ordinal
            else:
                advance = _subtract(
                    observation.fit_position_interval_px,
                    projections[0].fit_position_interval_px,
                )
                relation_ordinal = ordinal
            observed_gap = _subtract(advance, observed_width)
            combined_evidence = _materialized_role_evidence(
                lane,
                tuple((*seed.role_proposals, *proposals)),
                direction,
            )
            gap_model = _gap_model_from_bound_roles(
                frame_spec,
                frame_spec.initial_source_scan_geometry,
                lane.lane_id,
                combined_evidence,
            )
            delta = local_advance_delta_from_observed_gap(
                observed_gap,
                frame_spec.initial_source_scan_geometry,
                gap_model,
            )
            if delta is None:
                continue
            relation_candidates.append(
                LocalAdvanceRelation(
                    relation_ordinal=relation_ordinal,
                    kind=(
                        LocalAdvanceKind.NOMINAL
                        if delta == FiniteInterval.exact(0.0)
                        else LocalAdvanceKind.OBSERVED_UNCLASSIFIED
                        if gap_model.state != EvidenceState.SUPPORTED
                        else LocalAdvanceKind.WIDE
                        if delta.center > 0.0
                        else LocalAdvanceKind.NARROW
                    ),
                    delta_interval_px=delta,
                    canonical_delta_px=delta.center,
                    observation_ids=tuple(
                        ObservationId(value)
                        for value in sorted(
                            {
                                *(
                                    str(identity)
                                    for identity in observation.transition_ids
                                ),
                                *(
                                    str(identity)
                                    for run in runs
                                    for identity in run.transition_ids
                                ),
                            }
                        )
                    ),
                )
            )
        relations = list(seed.local_advance_relations)
        for relation in relation_candidates:
            index = relation.relation_ordinal - 1
            relations[index] = _merge_local_advance_relations(
                (relations[index],),
                (relation,),
            )[0]
        combined = {
            proposal.proposal_id: proposal for proposal in (*seed.role_proposals, *proposals)
        }
        local = {
            proposal.proposal_id: proposal
            for proposal in (*seed.local_advance_proposals, *proposals)
        }
        values.append(
            replace(
                seed,
                chain_proposal_id=_stable_id(
                    "registered-pair-seed",
                    seed.chain_proposal_id,
                    ordinal,
                    *(proposal.proposal_id for proposal in proposals),
                ),
                base_phase_interval_px=phase,
                role_proposals=tuple(combined[key] for key in sorted(combined)),
                local_advance_proposals=tuple(
                    local[key] for key in sorted(local)
                ),
                local_advance_relations=tuple(relations),
                exclusion_authorized=True,
            )
        )
    return tuple(values) if values else (seed,)


def _frame_spec_materialization_seeds(
    proposal: LanePhysicalProposals,
    frame_spec: FrameChainProposals,
    direction: SharedStripDirection,
    registered_runs: dict[str, ProfileRun],
) -> tuple[SequenceChainProposal, ...]:
    values = tuple(
        refined_seed
        for seed in build_sequence_chain_proposals(frame_spec)
        for refined_seed in _registered_pair_seeds(
            proposal.lane,
            frame_spec,
            seed,
            direction,
            registered_runs,
        )
    )
    unique = {item.chain_proposal_id: item for item in values}
    return tuple(unique[key] for key in sorted(unique))


def _materialized_role_evidence(
    lane: LaneObservationInput,
    proposals: tuple[SequenceRoleProposal, ...],
    direction: SharedStripDirection,
) -> tuple[BoundRoleEvidence, ...]:
    run_by_id = {run.run_id: run for run in lane.sequence_profile.runs}
    edge_by_run = {edge.run_id: edge for edge in lane.sequence_edges}
    values: list[BoundRoleEvidence] = []
    for proposal in proposals:
        run = run_by_id[proposal.run_id]
        projection = _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.height_authority_px.center,
            boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
        )
        values.append(
            BoundRoleEvidence(
                role=proposal.role,
                run_id=run.run_id,
                observation_id=(
                    None
                    if run.run_id not in edge_by_run
                    else edge_by_run[run.run_id].observation_id
                ),
                canonical_position_px=projection.canonical_position_px,
                fit_position_interval_px=projection.fit_position_interval_px,
                full_position_interval_px=projection.full_position_interval_px,
                transition_ids=run.transition_ids,
                support_fraction=run.support_fraction,
                continuous_support_fraction=run.continuous_support_fraction,
                fit_residual_px=run.fit_residual_px,
                background_preference=_background_preference(
                    run,
                    proposal.role.role,
                ),
            )
        )
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.run_id))
    )


def _role_evidence_intervals(
    observations: tuple[BoundRoleEvidence, ...],
) -> dict[int, tuple[FiniteInterval, FiniteInterval, tuple[ObservationId, ...]]]:
    by_role: dict[int, list[BoundRoleEvidence]] = {}
    for observation in observations:
        by_role.setdefault(observation.role.role_index, []).append(observation)
    result = {}
    for role_index, values in by_role.items():
        fit = _common(tuple(item.fit_position_interval_px for item in values))
        full = _common(tuple(item.full_position_interval_px for item in values))
        if fit is None or full is None:
            continue
        result[role_index] = (
            fit,
            _hull((fit, full)),
            tuple(
                ObservationId(identity)
                for identity in sorted(
                    {
                        str(transition_id)
                        for item in values
                        for transition_id in item.transition_ids
                    }
                )
            ),
        )
    return result


def _common_extent_constraint(
    constraints: tuple[tuple[FiniteInterval, tuple[ObservationId, ...]], ...],
) -> tuple[FiniteInterval, tuple[ObservationId, ...]] | None:
    if not constraints:
        return None
    common = _common(tuple(item[0] for item in constraints))
    if common is None:
        return None
    identities = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for _interval, values in constraints
                for identity in values
            }
        )
    )
    return common, identities


def _refine_source_geometry(
    lane: LaneObservationInput,
    proposal: FrameChainProposals,
    direction: SharedStripDirection,
    compatible_cross_proposals: tuple[CrossAxisProposal, ...],
    *,
    sequence_seeds: tuple[SequenceChainProposal, ...] | None = None,
) -> SourceScanGeometry:
    geometry = proposal.initial_source_scan_geometry
    width_state = geometry.width_state
    for seed in (
        build_sequence_chain_proposals(proposal)
        if sequence_seeds is None
        else sequence_seeds
    ):
        if not seed.exclusion_authorized:
            continue
        evidence = _materialized_role_evidence(
            lane,
            seed.role_proposals,
            direction,
        )
        ordered = tuple(
            sorted(evidence, key=lambda item: item.role.role_index)
        )
        frame_width_lower = width_state.extent_projection_px().minimum
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1 :]:
                if not set(map(str, left.transition_ids)).isdisjoint(
                    map(str, right.transition_ids)
                ):
                    continue
                left_template = _role_canonical_relative(
                    left.role,
                    proposal.frame_spec,
                    width_state,
                )
                right_template = _role_canonical_relative(
                    right.role,
                    proposal.frame_spec,
                    width_state,
                )
                if right_template - left_template + 1.0e-9 < frame_width_lower:
                    continue
                left_prefix, _ = local_advance_prefix(
                    seed.local_advance_relations,
                    lane_ordinal=left.role.lane_ordinal,
                )
                right_prefix, _ = local_advance_prefix(
                    seed.local_advance_relations,
                    lane_ordinal=right.role.lane_ordinal,
                )
                observed = _subtract(
                    _subtract(
                        right.fit_position_interval_px,
                        left.fit_position_interval_px,
                    ),
                    _subtract(right_prefix, left_prefix),
                )
                left_q, left_scale = _role_affine_coefficients(
                    left.role,
                    proposal.frame_spec,
                )
                right_q, right_scale = _role_affine_coefficients(
                    right.role,
                    proposal.frame_spec,
                )
                observation_ids = tuple(
                    ObservationId(value)
                    for value in sorted(
                        {
                            *(str(identity) for identity in left.transition_ids),
                            *(str(identity) for identity in right.transition_ids),
                        }
                    )
                )
                width_state = width_state.intersect_affine_observation(
                    observed,
                    q_coefficient=right_q - left_q,
                    scale_coefficient=right_scale - left_scale,
                    observation_ids=observation_ids,
                )

        phase_intervals: list[FiniteInterval] = []
        for observation in evidence:
            prefix, _ = local_advance_prefix(
                seed.local_advance_relations,
                lane_ordinal=observation.role.lane_ordinal,
            )
            phase_intervals.append(
                _subtract(
                    _subtract(
                        observation.fit_position_interval_px,
                        _role_relative_projection(
                            observation.role,
                            proposal.frame_spec,
                            width_state,
                        ),
                    ),
                    prefix,
                )
            )
        phase = _common(tuple(phase_intervals))
        if phase is None:
            continue
        indexed_runs = tuple(
            sorted(
                lane.sequence_profile.runs,
                key=lambda item: (
                    item.coordinate_interval_px.center,
                    item.run_id,
                ),
            )
        )
        centers = tuple(
            item.coordinate_interval_px.center for item in indexed_runs
        )
        maximum_half_width = max(
            (
                item.coordinate_interval_px.width / 2.0
                for item in indexed_runs
            ),
            default=0.0,
        )

        def unique_registered_run(
            role: OrdinalBoundaryRole,
        ) -> tuple[ProfileRun, _BoundRunProjection] | None:
            prefix, _ = local_advance_prefix(
                seed.local_advance_relations,
                lane_ordinal=role.lane_ordinal,
            )
            predicted = _add(
                _add(
                    phase,
                    _role_relative_projection(
                        role,
                        proposal.frame_spec,
                        width_state,
                    ),
                ),
                prefix,
            )
            binding_allowance = (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.dimension_search_allowance_mm
                * lane.width_scale_px_per_mm.maximum
            )
            binding_domain = FiniteInterval(
                predicted.minimum - binding_allowance,
                predicted.maximum + binding_allowance,
            )
            start = bisect_left(
                centers,
                binding_domain.minimum - maximum_half_width,
            )
            stop = bisect_right(
                centers,
                binding_domain.maximum + maximum_half_width,
            )
            candidates: list[tuple[ProfileRun, _BoundRunProjection]] = []
            allowed_gap = FiniteInterval(
                -width_state.extent_projection_px().maximum,
                lane.width_authority_px.width,
            )
            for run_index in range(start, stop):
                run = indexed_runs[run_index]
                if _intersection(
                    binding_domain,
                    run.coordinate_interval_px,
                ) is None:
                    continue
                projected = _project_profile_run(
                    run,
                    transitions=lane.transition_by_id,
                    direction=direction,
                    boundary_axis=lane.width_axis,
                    source_width_axis=lane.width_axis,
                    reference_trace_px=lane.height_authority_px.center,
                    boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
                )
                if _intersection(
                    binding_domain,
                    projected.fit_position_interval_px,
                ) is not None:
                    neighbor_index = (
                        run_index - 1
                        if role.role == BoundaryRole.START
                        else run_index + 1
                    )
                    if not 0 <= neighbor_index < len(indexed_runs):
                        continue
                    neighbor = indexed_runs[neighbor_index]
                    observed_gap = (
                        _subtract(
                            run.coordinate_interval_px,
                            neighbor.coordinate_interval_px,
                        )
                        if role.role == BoundaryRole.START
                        else _subtract(
                            neighbor.coordinate_interval_px,
                            run.coordinate_interval_px,
                        )
                    )
                    if _intersection(observed_gap, allowed_gap) is not None:
                        candidates.append((run, projected))
            return candidates[0] if len(candidates) == 1 else None

        for ordinal in range(2, lane.output_slot_count):
            start_role = proposal.roles[(ordinal - 1) * 2]
            end_role = proposal.roles[(ordinal - 1) * 2 + 1]
            start_projection = unique_registered_run(start_role)
            end_projection = unique_registered_run(end_role)
            if start_projection is None or end_projection is None:
                continue
            observed_width = _subtract(
                end_projection[1].fit_position_interval_px,
                start_projection[1].fit_position_interval_px,
            )
            matching_ids = tuple(
                ObservationId(value)
                for value in sorted(
                    {
                        str(identity)
                        for run in (start_projection[0], end_projection[0])
                        for identity in run.transition_ids
                    }
                )
            )
            if not matching_ids:
                continue
            try:
                width_tolerance = (
                    FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio
                )
                width_state = width_state.intersect_affine_observation(
                    FiniteInterval(
                        observed_width.minimum
                        / (
                            proposal.frame_spec.frame_width_mm
                            * (1.0 + width_tolerance)
                        ),
                        observed_width.maximum
                        / (
                            proposal.frame_spec.frame_width_mm
                            * (1.0 - width_tolerance)
                        ),
                    ),
                    q_coefficient=0.0,
                    scale_coefficient=1.0,
                    observation_ids=matching_ids,
                )
            except ValueError:
                continue

    height_constraints: list[
        tuple[FiniteInterval, tuple[ObservationId, ...]]
    ] = []
    for cross_proposal in compatible_cross_proposals:
        template_runs = {
            run.role_hint: run
            for run in cross_proposal.observed_runs
        }
        if set(template_runs) != {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            continue
        top = _project_profile_run(
            template_runs[BoundaryRole.TOP],
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.width_authority_px.center,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        bottom = _project_profile_run(
            template_runs[BoundaryRole.BOTTOM],
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.width_authority_px.center,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        observed_height = _subtract(
            bottom.full_position_interval_px,
            top.full_position_interval_px,
        )
        if (
            _intersection(
                observed_height,
                geometry.height_state.extent_projection_px(),
            )
            is not None
        ):
            height_constraints.append(
                (
                    observed_height,
                    tuple(
                        sorted(
                            (
                                *template_runs[
                                    BoundaryRole.TOP
                                ].transition_ids,
                                *template_runs[
                                    BoundaryRole.BOTTOM
                                ].transition_ids,
                            ),
                            key=str,
                        )
                    ),
                )
            )
    height_state = geometry.height_state
    if width_state.observation_ids:
        width_scale = lane.width_scale_px_per_mm
        height_scale = lane.height_scale_px_per_mm
        scale_ratio = (
            (height_scale.minimum + height_scale.maximum)
            / (width_scale.minimum + width_scale.maximum)
        )
        coupled_scale = width_state.feasible_scale_interval()
        try:
            height_state = height_state.intersect_affine_observation(
                FiniteInterval(
                    coupled_scale.minimum * scale_ratio,
                    coupled_scale.maximum * scale_ratio,
                ),
                q_coefficient=0.0,
                scale_coefficient=1.0,
                observation_ids=width_state.observation_ids,
            )
        except ValueError:
            pass
    height_constraints = [
        constraint
        for constraint in height_constraints
        if _intersection(
            constraint[0],
            height_state.extent_projection_px(),
        )
        is not None
    ]
    height_common = _common_extent_constraint(tuple(height_constraints))
    if height_common is not None:
        height_state = height_state.intersect_observed_extent(
            height_common[0],
            observation_ids=height_common[1],
        )
    return SourceScanGeometry(
        geometry_id=_stable_id(
            "source-scan-geometry",
            proposal.frame_spec.frame_spec_id,
            width_state.vertices,
            height_state.vertices,
            width_state.observation_ids,
            height_state.observation_ids,
        ),
        frame_spec=proposal.frame_spec,
        width_state=width_state,
        height_state=height_state,
    )


def _interval_sum(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    result = FiniteInterval.exact(0.0)
    for value in values:
        result = _add(result, value)
    return result


def local_advance_delta_from_observed_gap(
    observed_gap_px: FiniteInterval,
    geometry: SourceScanGeometry,
    gap_model: LaneGapModel,
) -> FiniteInterval | None:
    """Constrain one observed gap by physical ordering, not a fixed gap."""

    width = geometry.width_state.extent_projection_px()
    allowed_gap_px = FiniteInterval(-width.maximum, observed_gap_px.maximum)
    constrained_gap = _intersection(observed_gap_px, allowed_gap_px)
    if constrained_gap is None:
        return None
    nominal_gap_px = (
        gap_model.gap_interval_px
        if gap_model.state == EvidenceState.SUPPORTED
        and gap_model.gap_interval_px is not None
        else geometry.width_state.project_affine(
            q_coefficient=0.0,
            scale_coefficient=_gap_seed_mm(geometry.frame_spec),
        )
    )
    if _intersection(constrained_gap, nominal_gap_px) is not None:
        return FiniteInterval.exact(0.0)
    return _subtract(constrained_gap, nominal_gap_px)


def _gap_model_from_bound_roles(
    proposal: FrameChainProposals,
    geometry: SourceScanGeometry,
    lane_id: str,
    observations: tuple[BoundRoleEvidence, ...],
) -> LaneGapModel:
    return LaneGapModel.from_ordinal_edges(
        geometry.width_state,
        lane_id=lane_id,
        edge_families=tuple(
            tuple(
                (
                    observation.role.lane_ordinal,
                    observation.fit_position_interval_px,
                    observation.transition_ids,
                )
                for observation in observations
                if observation.role.role == role
            )
            for role in (BoundaryRole.START, BoundaryRole.END)
        ),
        format_gap_prior_mm=proposal.frame_spec.format_gap_prior_mm,
    )


def local_advance_prefix(
    relations: tuple[LocalAdvanceRelation, ...],
    *,
    lane_ordinal: int,
) -> tuple[FiniteInterval, float]:
    """Return the one-time phase step accumulated before one frame."""

    if lane_ordinal <= 0 or tuple(
        item.relation_ordinal for item in relations
    ) != tuple(range(1, len(relations) + 1)):
        raise ValueError("local advance relations must be ordered")
    prefix = relations[: lane_ordinal - 1]
    return (
        _interval_sum(tuple(item.delta_interval_px for item in prefix)),
        sum(item.canonical_delta_px for item in prefix),
    )


def _local_advance_relations(
    proposal: FrameChainProposals,
    geometry: SourceScanGeometry,
    gap_model: LaneGapModel,
    observations: tuple[BoundRoleEvidence, ...],
) -> tuple[LocalAdvanceRelation, ...]:
    by_role = _role_evidence_intervals(observations)
    relations: list[LocalAdvanceRelation] = []
    for ordinal in range(1, len(proposal.roles) // 2):
        end_index = ordinal * 2 - 1
        next_start_index = ordinal * 2
        end = by_role.get(end_index)
        start = by_role.get(next_start_index)
        if end is None or start is None:
            relations.append(
                LocalAdvanceRelation(
                    relation_ordinal=ordinal,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                )
            )
            continue
        observed_gap = _subtract(start[0], end[0])
        observation_ids = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(identity) for identity in end[2]),
                    *(str(identity) for identity in start[2]),
                }
            )
        )
        delta = local_advance_delta_from_observed_gap(
            observed_gap,
            geometry,
            gap_model,
        )
        if delta is None:
            raise ValueError("observed gap exceeds format local advance authority")
        if delta == FiniteInterval.exact(0.0):
            relations.append(
                LocalAdvanceRelation(
                    relation_ordinal=ordinal,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=observation_ids,
                )
            )
            continue
        canonical_delta = delta.center
        gap_center = observed_gap.center
        if gap_model.state != EvidenceState.SUPPORTED:
            kind = LocalAdvanceKind.OBSERVED_UNCLASSIFIED
        elif gap_center < 0.0:
            kind = LocalAdvanceKind.OVERLAP
        elif observed_gap.contains(0.0):
            kind = LocalAdvanceKind.CONTACT
        elif canonical_delta > 0.0:
            kind = LocalAdvanceKind.WIDE
        else:
            kind = LocalAdvanceKind.NARROW
        relations.append(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=kind,
                delta_interval_px=delta,
                canonical_delta_px=canonical_delta,
                observation_ids=observation_ids,
            )
        )
    return tuple(relations)


def _supported_role_subset(
    group: SequenceHypothesisGroup,
    *,
    first_ordinal: int,
    last_ordinal: int,
    frame_width_lower_px: float,
) -> tuple[SequenceRoleProposal, ...]:
    proposals = tuple(
        item
        for item in group.role_proposals
        if first_ordinal <= item.role.lane_ordinal <= last_ordinal
    )
    if not proposals or not group_support_exclusion_authorized(
        role_coordinates_px=tuple(item.role_coordinate_px for item in proposals),
        role_identities=tuple(
            (item.role.lane_ordinal, item.role.role) for item in proposals
        ),
        transition_id_sets=tuple(item.transition_ids for item in proposals),
        frame_width_lower_px=frame_width_lower_px,
    ):
        return ()
    return proposals


def _structural_authority_proposals(
    proposals: tuple[SequenceRoleProposal, ...],
    *,
    frame_width_lower_px: float,
) -> tuple[SequenceRoleProposal, ...]:
    """Return the widest independent role pair that owns absolute phase.

    Other transitions in the same sequence hypothesis group remain query evidence, but an
    adjacent separator side cannot become another absolute-phase authority.
    Local adjacency is consumed by ``LocalAdvanceRelation`` instead.
    """

    pairs: list[tuple[float, str, str, SequenceRoleProposal, SequenceRoleProposal]] = []
    for left_index, left in enumerate(proposals):
        left_ids = set(map(str, left.transition_ids))
        for right in proposals[left_index + 1 :]:
            if not left_ids.isdisjoint(map(str, right.transition_ids)):
                continue
            opposite = (
                left.role.lane_ordinal == right.role.lane_ordinal
                and {left.role.role, right.role.role}
                == {BoundaryRole.START, BoundaryRole.END}
            )
            separation = abs(
                left.role_coordinate_px - right.role_coordinate_px
            )
            if not opposite and separation + 1.0e-9 < frame_width_lower_px:
                continue
            pairs.append(
                (
                    separation,
                    left.proposal_id,
                    right.proposal_id,
                    left,
                    right,
                )
            )
    if not pairs:
        return proposals
    _distance, _left_id, _right_id, left, right = min(
        pairs,
        key=lambda item: (-item[0], item[1], item[2]),
    )
    return tuple(
        sorted((left, right), key=lambda item: item.role.role_index)
    )


def _phase_step_relation(
    upstream: SequenceHypothesisGroup,
    downstream: SequenceHypothesisGroup,
    *,
    relation_ordinal: int,
    upstream_proposals: tuple[SequenceRoleProposal, ...],
    downstream_proposals: tuple[SequenceRoleProposal, ...],
) -> LocalAdvanceRelation | None:
    upstream_ids = {
        str(identity)
        for proposal in upstream_proposals
        for identity in proposal.transition_ids
    }
    downstream_ids = {
        str(identity)
        for proposal in downstream_proposals
        for identity in proposal.transition_ids
    }
    if (
        upstream is downstream
        or not upstream_ids.isdisjoint(downstream_ids)
        or _intersection(
            upstream.phase_interval_px,
            downstream.phase_interval_px,
        )
        is not None
    ):
        return None
    delta = _subtract(
        downstream.phase_interval_px,
        upstream.phase_interval_px,
    )
    if delta.contains(0.0):
        return None
    return LocalAdvanceRelation(
        relation_ordinal=relation_ordinal,
        kind=LocalAdvanceKind.OBSERVED_UNCLASSIFIED,
        delta_interval_px=delta,
        canonical_delta_px=delta.center,
        observation_ids=tuple(
            ObservationId(value)
            for value in sorted(upstream_ids | downstream_ids)
        ),
    )


def build_sequence_chain_proposals(
    proposal: FrameChainProposals,
) -> tuple[SequenceChainProposal, ...]:
    groups = proposal.sequence_groups
    slot_count = len(proposal.roles) // 2
    frame_width_lower = (
        proposal.initial_source_scan_geometry.width_state.extent_projection_px().minimum
    )
    downstream_by_split: dict[
        int,
        tuple[SequenceHypothesisGroup, tuple[SequenceRoleProposal, ...]] | None,
    ] = {}
    upstream_support: dict[tuple[str, int], tuple[SequenceRoleProposal, ...]] = {}
    for split in range(1, slot_count):
        downstream: list[
            tuple[SequenceHypothesisGroup, tuple[SequenceRoleProposal, ...]]
        ] = []
        for group in groups:
            upstream_support[(group.group_id, split)] = _supported_role_subset(
                group,
                first_ordinal=1,
                last_ordinal=split,
                frame_width_lower_px=frame_width_lower,
            )
            proposals = _supported_role_subset(
                group,
                first_ordinal=split + 1,
                last_ordinal=slot_count,
                frame_width_lower_px=frame_width_lower,
            )
            if proposals:
                downstream.append((group, proposals))
        downstream_by_split[split] = (
            downstream[0] if len(downstream) == 1 else None
        )

    seeds: list[SequenceChainProposal] = []
    for initial in groups:
        current = initial
        group_for_ordinal: list[SequenceHypothesisGroup] = []
        relations: list[LocalAdvanceRelation] = []
        group_ids = [initial.group_id]
        for split in range(1, slot_count):
            group_for_ordinal.append(current)
            downstream = downstream_by_split[split]
            relation = None
            if downstream is not None:
                upstream_proposals = upstream_support[(current.group_id, split)]
                if upstream_proposals:
                    relation = _phase_step_relation(
                        current,
                        downstream[0],
                        relation_ordinal=split,
                        upstream_proposals=upstream_proposals,
                        downstream_proposals=downstream[1],
                    )
            if relation is None:
                relation = LocalAdvanceRelation(
                    relation_ordinal=split,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                )
            else:
                current = downstream[0]
                if current.group_id not in group_ids:
                    group_ids.append(current.group_id)
            relations.append(relation)
        group_for_ordinal.append(current)
        proposals = tuple(
            sorted(
                {
                    proposal.proposal_id: proposal
                    for ordinal, group in enumerate(group_for_ordinal, start=1)
                    for proposal in group.role_proposals
                    if proposal.role.lane_ordinal == ordinal
                }.values(),
                key=lambda item: (item.role.role_index, item.proposal_id),
            )
        )
        if not proposals:
            continue
        local_advance_proposals = proposals
        if initial.exclusion_authorized:
            proposals = _structural_authority_proposals(
                proposals,
                frame_width_lower_px=frame_width_lower,
            )
        seeds.append(
            SequenceChainProposal(
                chain_proposal_id=_stable_id(
                    "sequence-chain-proposal",
                    *(group_ids),
                    *(item.kind.value for item in relations),
                    *(item.delta_interval_px for item in relations),
                ),
                sequence_group_ids=tuple(group_ids),
                base_phase_interval_px=initial.phase_interval_px,
                role_proposals=proposals,
                local_advance_proposals=local_advance_proposals,
                local_advance_relations=tuple(relations),
                exclusion_authorized=(
                    initial.exclusion_authorized
                    and all(
                        item.kind == LocalAdvanceKind.NOMINAL
                        or bool(item.observation_ids)
                        for item in relations
                    )
                ),
            )
        )
    unique = {item.chain_proposal_id: item for item in seeds}
    return tuple(unique[key] for key in sorted(unique))


def _merge_local_advance_relations(
    declared: tuple[LocalAdvanceRelation, ...],
    observed: tuple[LocalAdvanceRelation, ...],
) -> tuple[LocalAdvanceRelation, ...]:
    if len(declared) != len(observed):
        raise ValueError("local advance relation sets disagree")
    merged: list[LocalAdvanceRelation] = []
    for left, right in zip(declared, observed, strict=True):
        if left.relation_ordinal != right.relation_ordinal:
            raise ValueError("local advance relation ordinals disagree")
        left_is_nominal = left.kind == LocalAdvanceKind.NOMINAL
        right_is_nominal = right.kind == LocalAdvanceKind.NOMINAL
        if not left_is_nominal and right_is_nominal and right.observation_ids:
            raise ValueError("observed nominal gap contradicts phase step")
        if left_is_nominal:
            merged.append(right)
            continue
        if right_is_nominal:
            merged.append(left)
            continue
        common = _intersection(left.delta_interval_px, right.delta_interval_px)
        if common is None:
            raise ValueError("local phase-step evidence conflicts")
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(item) for item in left.observation_ids),
                    *(str(item) for item in right.observation_ids),
                }
            )
        )
        merged.append(
            LocalAdvanceRelation(
                relation_ordinal=left.relation_ordinal,
                kind=(
                    left.kind
                    if left.kind == right.kind
                    else right.kind
                    if left.kind == LocalAdvanceKind.OBSERVED_UNCLASSIFIED
                    else left.kind
                    if right.kind == LocalAdvanceKind.OBSERVED_UNCLASSIFIED
                    else LocalAdvanceKind.WIDE
                    if common.center > 0.0
                    else LocalAdvanceKind.NARROW
                ),
                delta_interval_px=common,
                canonical_delta_px=common.center,
                observation_ids=identities,
            )
        )
    return tuple(merged)


def _registered_sequence_run_direction_interval(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
) -> FiniteInterval | None:
    """Bound one already measured short-edge slope without making it phase."""

    values = tuple(
        transitions[str(identity)]
        for identity in run.transition_ids
        if str(identity) in transitions
    )
    traces = np.asarray(
        [item.trace_coordinate_px for item in values],
        dtype=np.float64,
    )
    coordinates = np.asarray(
        [item.coordinate_px for item in values],
        dtype=np.float64,
    )
    if len(values) < 2 or float(np.ptp(traces)) <= 0.0:
        return None
    design = np.column_stack((traces, np.ones_like(traces)))
    slope, intercept = np.linalg.lstsq(
        design,
        coordinates,
        rcond=None,
    )[0]
    residual = np.abs(coordinates - (slope * traces + intercept))
    interval_half_width = np.asarray(
        [item.coordinate_interval_px.width / 2.0 for item in values],
        dtype=np.float64,
    )
    slope_allowance = 2.0 * float(
        np.max(residual + interval_half_width)
    ) / float(np.ptp(traces))
    return FiniteInterval(
        math.degrees(math.atan(float(slope) - slope_allowance)),
        math.degrees(math.atan(float(slope) + slope_allowance)),
    )


def _materialize_sequence_placement(
    lane: LaneObservationInput,
    proposal: FrameChainProposals,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
) -> SequencePlacement:
    observations = _materialized_role_evidence(
        lane,
        seed.role_proposals,
        direction,
    )
    if not observations:
        raise ValueError("sequence placement has no absolute pixel anchor")
    observed_by_role = {
        (item.run_id, item.role.lane_ordinal, item.role.role): item
        for item in observations
    }
    bound_separator_bands = tuple(
        BoundSeparatorBand(
            observation=band,
            relation_ordinal=ordinal,
            left_role_index=(ordinal - 1) * 2 + 1,
            right_role_index=ordinal * 2,
        )
        for band in lane.separator_bands
        for ordinal in range(1, lane.output_slot_count)
        if (
            (band.left_run_id, ordinal, BoundaryRole.END)
            in observed_by_role
            and (
                band.right_run_id,
                ordinal + 1,
                BoundaryRole.START,
            )
            in observed_by_role
        )
    )
    gap_model = _gap_model_from_bound_roles(
        proposal,
        geometry,
        lane.lane_id,
        observations,
    )
    relations = _merge_local_advance_relations(
        seed.local_advance_relations,
        _local_advance_relations(
            proposal,
            geometry,
            gap_model,
            _materialized_role_evidence(
                lane,
                seed.local_advance_proposals,
                direction,
            ),
        ),
    )
    fit_phases: list[FiniteInterval] = []
    full_phases: list[FiniteInterval] = []
    implied_canonical: list[float] = []
    weights: list[float] = []
    for observation in observations:
        prefix_interval, prefix_canonical = local_advance_prefix(
            relations,
            lane_ordinal=observation.role.lane_ordinal,
        )
        relative = _role_relative_projection(
            observation.role,
            proposal.frame_spec,
            geometry.width_state,
            gap_model,
        )
        fit_phases.append(
            _subtract(
                _subtract(observation.fit_position_interval_px, relative),
                prefix_interval,
            )
        )
        full_phases.append(
            _subtract(
                _subtract(observation.full_position_interval_px, relative),
                prefix_interval,
            )
        )
        implied_canonical.append(
            observation.canonical_position_px
            - _role_canonical_relative(
                observation.role,
                proposal.frame_spec,
                geometry.width_state,
                gap_model,
            )
            - prefix_canonical
        )
        weights.append(
            max(
                1.0,
                observation.support_fraction
                + observation.continuous_support_fraction,
            )
        )
    phase_fit = _common(tuple(fit_phases))
    phase_full = _common(tuple(full_phases))
    if phase_fit is None or phase_full is None:
        raise ValueError("cross_proposal-bound observations disagree on phase")
    phase_full = _hull((phase_full, phase_fit))
    canonical_phase = robust_scalar_location(
        tuple(implied_canonical),
        tuple(weights),
        geometry.width_state.feasible_scale_interval(),
    )
    if not phase_fit.contains(canonical_phase, epsilon=1.0e-9):
        canonical_phase = phase_fit.center
    by_role = _role_evidence_intervals(observations)
    registered_safety_projections = tuple(
        sorted(
            (
                (
                    projection.full_position_interval_px.center,
                    run,
                    projection,
                )
                for run in lane.sequence_profile.runs
                if run.pair_qualified
                for projection in (
                    _project_profile_run(
                        run,
                        transitions=lane.transition_by_id,
                        direction=direction,
                        boundary_axis=lane.width_axis,
                        source_width_axis=lane.width_axis,
                        reference_trace_px=lane.height_authority_px.center,
                        boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
                    ),
                )
            ),
            key=lambda item: (item[0], item[1].run_id),
        )
    )
    safety_projection_centers = tuple(
        item[0] for item in registered_safety_projections
    )
    maximum_safety_half_width = max(
        (
            item[2].full_position_interval_px.width / 2.0
            for item in registered_safety_projections
        ),
        default=0.0,
    )
    safety_lookup_allowance = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.center_offset_allowance_mm
        * lane.width_scale_px_per_mm.maximum
    )
    canonical_positions: list[float] = []
    fit_positions: list[FiniteInterval] = []
    full_positions: list[FiniteInterval] = []
    sequence_edge_direction_intervals: list[FiniteInterval] = []
    safety_support_transition_ids: list[tuple[ObservationId, ...]] = []
    for role in proposal.roles:
        prefix_interval, prefix_canonical = local_advance_prefix(
            relations,
            lane_ordinal=role.lane_ordinal,
        )
        relative = _role_relative_projection(
            role,
            proposal.frame_spec,
            geometry.width_state,
            gap_model,
        )
        relative_canonical = _role_canonical_relative(
            role,
            proposal.frame_spec,
            geometry.width_state,
            gap_model,
        )
        fit = _add(_add(phase_fit, relative), prefix_interval)
        full = _add(_add(phase_full, relative), prefix_interval)
        observed = by_role.get(role.role_index)
        if observed is not None:
            fit_intersection = _intersection(fit, observed[0])
            full_intersection = _intersection(full, observed[1])
            if fit_intersection is None or full_intersection is None:
                raise ValueError("observed role contradicts propagated cross_proposal")
            fit = fit_intersection
            full = _hull((fit, full_intersection))
        corridor = FiniteInterval(
            fit.minimum - safety_lookup_allowance,
            fit.maximum + safety_lookup_allowance,
        )
        start = bisect_left(
            safety_projection_centers,
            corridor.minimum - maximum_safety_half_width,
        )
        stop = bisect_right(
            safety_projection_centers,
            corridor.maximum + maximum_safety_half_width,
        )
        registered_support = tuple(
            (run, projection)
            for _center, run, projection in registered_safety_projections[
                start:stop
            ]
            if _intersection(
                corridor,
                projection.full_position_interval_px,
            )
            is not None
        )
        if registered_support:
            nearest_distance = min(
                abs(
                    projection.full_position_interval_px.center
                    - fit.center
                )
                for _run, projection in registered_support
            )
            equivalence = (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.geometry_equivalence_mm
                * lane.width_scale_px_per_mm.maximum
            )
            registered_support = tuple(
                (run, projection)
                for run, projection in registered_support
                if abs(
                    projection.full_position_interval_px.center
                    - fit.center
                )
                <= nearest_distance + equivalence
            )
        if registered_support:
            full = _hull(
                (
                    full,
                    *(
                        projection.full_position_interval_px
                        for _run, projection in registered_support
                    ),
                )
            )
        canonical_sequence_slope = canonical_source_sequence_axis_slope(
            direction,
            lane.width_axis,
        )
        direction_intervals = tuple(
            interval
            for run, _projection in registered_support
            if (
                interval := _registered_sequence_run_direction_interval(
                    run,
                    lane.transition_by_id,
                )
            )
            is not None
        )
        direction_interval = (
            _hull(direction_intervals)
            if direction_intervals
            else FiniteInterval.exact(
                math.degrees(math.atan(canonical_sequence_slope))
            )
        )
        direction_slopes = (
            math.tan(math.radians(direction_interval.minimum)),
            math.tan(math.radians(direction_interval.maximum)),
        )
        direction_displacement = max(
            abs(value - canonical_sequence_slope)
            for value in direction_slopes
        ) * max(
            abs(
                lane.height_authority_px.minimum
                - lane.height_authority_px.center
            ),
            abs(
                lane.height_authority_px.maximum
                - lane.height_authority_px.center
            ),
        )
        full = FiniteInterval(
            full.minimum - direction_displacement,
            full.maximum + direction_displacement,
        )
        canonical = canonical_phase + relative_canonical + prefix_canonical
        if not fit.contains(canonical, epsilon=1.0e-8):
            # Canonical preference has no authority outside the conditional
            # feasible interval.  The midpoint is the deterministic fallback,
            # never a clamp of the invalid preference.
            canonical = fit.center
        canonical_positions.append(canonical)
        fit_positions.append(fit)
        full_positions.append(_hull((full, fit)))
        sequence_edge_direction_intervals.append(direction_interval)
        safety_support_transition_ids.append(
            tuple(
                ObservationId(value)
                for value in sorted(
                    {
                        str(identity)
                        for run, _projection in registered_support
                        for identity in run.transition_ids
                    }
                )
            )
        )
    return SequencePlacement(
        placement_id=_stable_id(
            "sequence-placement",
            proposal.frame_spec.frame_spec_id,
            seed.chain_proposal_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        chain_proposal_id=seed.chain_proposal_id,
        sequence_group_ids=seed.sequence_group_ids,
        source_scan_geometry_id=geometry.geometry_id,
        roles=proposal.roles,
        phase_fit_interval_px=phase_fit,
        phase_full_interval_px=phase_full,
        lane_gap_model=gap_model,
        local_advance_relations=relations,
        canonical_positions_px=tuple(canonical_positions),
        fit_positions_px=tuple(fit_positions),
        full_positions_px=tuple(full_positions),
        sequence_edge_direction_intervals_degrees=tuple(
            sequence_edge_direction_intervals
        ),
        safety_support_transition_ids=tuple(
            safety_support_transition_ids
        ),
        observations=observations,
        separator_bands=bound_separator_bands,
        exclusion_authorized=seed.exclusion_authorized,
    )


def _slope_displacement_interval(
    slope: FiniteInterval,
    trace_delta_px: float,
) -> FiniteInterval:
    values = (
        slope.minimum * trace_delta_px,
        slope.maximum * trace_delta_px,
    )
    return FiniteInterval(min(values), max(values))


def _materialize_cross_placement(
    lane: LaneObservationInput,
    cross_proposal: CrossAxisProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
    frame_reference_traces_px: tuple[float, ...],
    frame_reference_intervals_px: tuple[FiniteInterval, ...],
) -> CrossPlacement:
    lane_reference = lane.width_authority_px.center
    observed_runs = {
        run.role_hint: run
        for run in cross_proposal.observed_runs
    }
    lane_projections = {
        role: _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane_reference,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        for role, run in observed_runs.items()
    }
    extent = geometry.height_state.extent_projection_px()
    phase = _conditional_fit_and_full(
        tuple(
            projection.fit_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(projection.fit_position_interval_px, extent)
            for role, projection in lane_projections.items()
        ),
        tuple(
            projection.full_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(projection.full_position_interval_px, extent)
            for role, projection in lane_projections.items()
        ),
    )
    if phase is None:
        raise ValueError("cross_proposal-bound height roles disagree on source height")
    phase_fit, phase_full = phase
    canonical_slope = canonical_source_cross_axis_slope(
        direction,
        lane.height_axis,
    )
    slope_interval = source_cross_axis_slope_interval(
        direction,
        lane.height_axis,
    )
    if len(frame_reference_traces_px) != len(frame_reference_intervals_px):
        raise ValueError("cross placement frame references are incomplete")
    frame_states: list[
        tuple[
            dict[BoundaryRole, FiniteInterval],
            dict[BoundaryRole, FiniteInterval],
            float,
        ]
    ] = []
    for reference, reference_interval in zip(
        frame_reference_traces_px,
        frame_reference_intervals_px,
        strict=True,
    ):
        delta = reference - lane_reference
        canonical_shift = canonical_slope * delta
        shift = _slope_displacement_interval(slope_interval, delta)
        model_top_fit = _add(phase_fit, shift)
        model_bottom_fit = _add(model_top_fit, extent)
        full_shifts = tuple(
            _slope_displacement_interval(
                slope_interval,
                endpoint - lane_reference,
            )
            for endpoint in (
                reference_interval.minimum,
                reference_interval.maximum,
            )
        )
        model_top_full = _add(phase_full, _hull(full_shifts))
        model_bottom_full = _add(model_top_full, extent)
        frame_fit = {
            BoundaryRole.TOP: model_top_fit,
            BoundaryRole.BOTTOM: model_bottom_fit,
        }
        frame_full = {
            BoundaryRole.TOP: model_top_full,
            BoundaryRole.BOTTOM: model_bottom_full,
        }
        for role, run in observed_runs.items():
            direct_values = tuple(
                _project_profile_run(
                    run,
                    transitions=lane.transition_by_id,
                    direction=direction,
                    boundary_axis=lane.height_axis,
                    source_width_axis=lane.width_axis,
                    reference_trace_px=endpoint,
                    boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
                )
                for endpoint in (
                    reference,
                    reference_interval.minimum,
                    reference_interval.maximum,
                )
            )
            conditioned = _conditional_fit_and_full(
                (
                    frame_fit[role],
                    direct_values[0].fit_position_interval_px,
                ),
                (
                    frame_full[role],
                    _hull(
                        tuple(
                            item.full_position_interval_px
                            for item in direct_values
                        )
                    ),
                ),
            )
            if conditioned is None:
                raise ValueError("exact height projection contradicts cross_proposal")
            frame_fit[role], frame_full[role] = conditioned
        frame_states.append((frame_fit, frame_full, canonical_shift))

    extent_constraints = tuple(
        intersection
        for _frame_fit, frame_full, _canonical_shift in frame_states
        if (
            intersection := _intersection(
                extent,
                _subtract(
                    frame_full[BoundaryRole.BOTTOM],
                    frame_full[BoundaryRole.TOP],
                ),
            )
        )
        is not None
    )
    if len(extent_constraints) != len(frame_states):
        raise ValueError("frame height is outside joint source geometry")
    shared_extent = _common(extent_constraints)
    if shared_extent is None:
        raise ValueError("frame cross_proposals have no shared physical extent")
    _scale, normalized, _factor = geometry.height_state.canonical_state()
    canonical_extent_preference = (
        geometry.height_state.design_extent_mm * normalized
    )
    canonical_extent = (
        canonical_extent_preference
        if shared_extent.contains(canonical_extent_preference)
        else shared_extent.center
    )
    canonical_extent_interval = FiniteInterval.exact(canonical_extent)
    canonical_phase_condition = _conditional_fit_and_full(
        tuple(
            projection.fit_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(
                projection.fit_position_interval_px,
                canonical_extent_interval,
            )
            for role, projection in lane_projections.items()
        ),
        tuple(
            projection.full_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(
                projection.full_position_interval_px,
                canonical_extent_interval,
            )
            for role, projection in lane_projections.items()
        ),
    )
    if canonical_phase_condition is None:
        raise ValueError("canonical source height is outside observed roles")
    canonical_phase_interval = canonical_phase_condition[0]
    canonical_phase_preference = sum(
        projection.canonical_position_px
        - (canonical_extent if role == BoundaryRole.BOTTOM else 0.0)
        for role, projection in lane_projections.items()
    ) / len(lane_projections)
    canonical_phase = (
        canonical_phase_preference
        if canonical_phase_interval.contains(canonical_phase_preference)
        else canonical_phase_interval.center
    )

    top_canonical: list[float] = []
    bottom_canonical: list[float] = []
    top_fit: list[FiniteInterval] = []
    bottom_fit: list[FiniteInterval] = []
    top_full: list[FiniteInterval] = []
    bottom_full: list[FiniteInterval] = []
    for frame_fit, frame_full, canonical_shift in frame_states:
        frame_phase = _conditional_fit_and_full(
            (
                frame_fit[BoundaryRole.TOP],
                _subtract(
                    frame_fit[BoundaryRole.BOTTOM],
                    canonical_extent_interval,
                ),
            ),
            (
                frame_full[BoundaryRole.TOP],
                _subtract(
                    frame_full[BoundaryRole.BOTTOM],
                    canonical_extent_interval,
                ),
            ),
        )
        if frame_phase is None:
            raise ValueError("canonical source height is infeasible at frame")
        frame_phase_interval = frame_phase[0]
        predicted_phase = canonical_phase + canonical_shift
        frame_phase = (
            predicted_phase
            if frame_phase_interval.contains(predicted_phase)
            else frame_phase_interval.center
        )
        canonical_top = frame_phase
        canonical_bottom = frame_phase + canonical_extent
        if canonical_top >= canonical_bottom:
            raise ValueError("canonical height placement is unordered")
        conditional_top_fit = (
            frame_fit[BoundaryRole.TOP]
            if frame_fit[BoundaryRole.TOP].contains(
                canonical_top,
                epsilon=1.0e-8,
            )
            else FiniteInterval.exact(canonical_top)
        )
        conditional_bottom_fit = (
            frame_fit[BoundaryRole.BOTTOM]
            if frame_fit[BoundaryRole.BOTTOM].contains(
                canonical_bottom,
                epsilon=1.0e-8,
            )
            else FiniteInterval.exact(canonical_bottom)
        )
        top_canonical.append(canonical_top)
        bottom_canonical.append(canonical_bottom)
        top_fit.append(conditional_top_fit)
        bottom_fit.append(conditional_bottom_fit)
        top_full.append(
            _hull((conditional_top_fit, frame_full[BoundaryRole.TOP]))
        )
        bottom_full.append(
            _hull(
                (
                    conditional_bottom_fit,
                    frame_full[BoundaryRole.BOTTOM],
                )
            )
        )
    observation_by_role = {
        observation.role: observation for observation in cross_proposal.raw_observations
    }
    return CrossPlacement(
        placement_id=_stable_id(
            "cross-placement",
            cross_proposal.cross_proposal_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        cross_proposal_id=cross_proposal.cross_proposal_id,
        source_scan_geometry_id=geometry.geometry_id,
        lane_reference_trace_px=lane_reference,
        frame_reference_traces_px=frame_reference_traces_px,
        top_canonical_positions_px=tuple(top_canonical),
        bottom_canonical_positions_px=tuple(bottom_canonical),
        top_fit_positions_px=tuple(top_fit),
        bottom_fit_positions_px=tuple(bottom_fit),
        top_full_positions_px=tuple(top_full),
        bottom_full_positions_px=tuple(bottom_full),
        evidence=tuple(
            CrossRoleEvidence(
                role=role,
                run_id=run.run_id,
                observation=observation_by_role[role],
                canonical_position_at_lane_reference_px=(
                    lane_projections[role].canonical_position_px
                ),
                fit_position_at_lane_reference_px=(
                    lane_projections[role].fit_position_interval_px
                ),
                full_position_at_lane_reference_px=(
                    lane_projections[role].full_position_interval_px
                ),
            )
            for role, run in observed_runs.items()
        ),
    )


def _boundary_geometry(
    *,
    role: BoundaryRole,
    canonical_position_px: float,
    full_position_interval_px: FiniteInterval,
    reference_trace_px: float,
    support_projection_px: FiniteInterval,
    boundary_axis: BoundaryAxis,
    source_width_axis: BoundaryAxis,
    direction: SharedStripDirection,
    observation_ids: tuple[ObservationId, ...],
    position_source: PositionSource,
    named_position_inference: str | None,
    sequence_direction_interval_degrees: FiniteInterval | None = None,
    sequence_direction_reference_id: str | None = None,
) -> FrameBoundaryGeometry:
    if not observation_ids:
        raise ValueError("frame boundary requires position evidence")
    return FrameBoundaryGeometry(
        role=role,
        line=canonical_boundary_line(
            direction,
            boundary_axis=boundary_axis,
            source_axis_long=source_width_axis,
            trace_coordinate_px=reference_trace_px,
            position_px=canonical_position_px,
            support_projection_px=support_projection_px,
        ),
        reference_trace_px=reference_trace_px,
        canonical_position_px=canonical_position_px,
        full_position_interval_px=full_position_interval_px,
        full_direction_interval_degrees=(
            sequence_direction_interval_degrees
            if role in {BoundaryRole.START, BoundaryRole.END}
            else direction.full_angle_interval_degrees
        ),
        position_source=position_source,
        position_observation_ids=observation_ids,
        named_position_inference=named_position_inference,
        direction_authority=(
            DirectionAuthority.BOUNDED_SEQUENCE_EDGE_DIRECTION
            if role in {BoundaryRole.START, BoundaryRole.END}
            else DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
        ),
        direction_reference_id=(
            sequence_direction_reference_id
            if role in {BoundaryRole.START, BoundaryRole.END}
            else direction.direction_id
        ),
    )


def _canonical_frames(
    lane: LaneObservationInput,
    direction: SharedStripDirection,
    sequence: SequencePlacement,
    cross: CrossPlacement,
) -> tuple[FixedFormatFrame, ...]:
    sequence_observations: dict[int, tuple[ObservationId, ...]] = {}
    for role_index in range(len(sequence.roles)):
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    str(identity)
                    for item in sequence.observations
                    if item.role.role_index == role_index
                    for identity in item.transition_ids
                }
            )
        )
        if identities:
            sequence_observations[role_index] = identities
    all_sequence_ids = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for item in sequence.observations
                for identity in item.transition_ids
            }
        )
    )
    cross_by_role = {
        item.role: tuple(item.observation.transition_ids)
        for item in cross.evidence
    }
    all_cross_ids = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for item in cross.evidence
                for identity in item.observation.transition_ids
            }
        )
    )
    frames: list[FixedFormatFrame] = []
    for ordinal in range(1, len(sequence.roles) // 2 + 1):
        start_index = (ordinal - 1) * 2
        end_index = start_index + 1
        frame_reference = (
            sequence.canonical_positions_px[start_index]
            + sequence.canonical_positions_px[end_index]
        ) / 2.0
        width_support = FiniteInterval(
            sequence.full_positions_px[start_index].minimum,
            sequence.full_positions_px[end_index].maximum,
        )
        start_ids = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(item) for item in sequence_observations.get(start_index, ())),
                    *(
                        str(item)
                        for item in sequence.safety_support_transition_ids[
                            start_index
                        ]
                    ),
                }
            )
        ) or all_sequence_ids
        end_ids = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(item) for item in sequence_observations.get(end_index, ())),
                    *(
                        str(item)
                        for item in sequence.safety_support_transition_ids[
                            end_index
                        ]
                    ),
                }
            )
        ) or all_sequence_ids
        top_ids = cross_by_role.get(BoundaryRole.TOP, all_cross_ids)
        bottom_ids = cross_by_role.get(BoundaryRole.BOTTOM, all_cross_ids)
        start = _boundary_geometry(
            role=BoundaryRole.START,
            canonical_position_px=sequence.canonical_positions_px[start_index],
            full_position_interval_px=sequence.full_positions_px[start_index],
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=start_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if start_index in sequence_observations
                else PositionSource.INFERRED_SEQUENCE
            ),
            named_position_inference=(
                None
                if start_index in sequence_observations
                else "start_from_chain_phase_and_lane_gap"
            ),
            sequence_direction_interval_degrees=(
                sequence.sequence_edge_direction_intervals_degrees[
                    start_index
                ]
            ),
            sequence_direction_reference_id=sequence.placement_id,
        )
        end = _boundary_geometry(
            role=BoundaryRole.END,
            canonical_position_px=sequence.canonical_positions_px[end_index],
            full_position_interval_px=sequence.full_positions_px[end_index],
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=end_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if end_index in sequence_observations
                else PositionSource.INFERRED_SEQUENCE
            ),
            named_position_inference=(
                None
                if end_index in sequence_observations
                else "end_from_chain_phase_and_lane_gap"
            ),
            sequence_direction_interval_degrees=(
                sequence.sequence_edge_direction_intervals_degrees[
                    end_index
                ]
            ),
            sequence_direction_reference_id=sequence.placement_id,
        )
        top = _boundary_geometry(
            role=BoundaryRole.TOP,
            canonical_position_px=cross.top_canonical_positions_px[ordinal - 1],
            full_position_interval_px=cross.top_full_positions_px[ordinal - 1],
            reference_trace_px=frame_reference,
            support_projection_px=width_support,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=top_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.TOP in cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.TOP in cross_by_role
                else "top_from_observed_bottom_and_source_height"
            ),
        )
        bottom = _boundary_geometry(
            role=BoundaryRole.BOTTOM,
            canonical_position_px=(
                cross.bottom_canonical_positions_px[ordinal - 1]
            ),
            full_position_interval_px=(
                cross.bottom_full_positions_px[ordinal - 1]
            ),
            reference_trace_px=frame_reference,
            support_projection_px=width_support,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=bottom_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.BOTTOM in cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.BOTTOM in cross_by_role
                else "bottom_from_observed_top_and_source_height"
            ),
        )
        polygon = (
            top.line.intersection(start.line),
            top.line.intersection(end.line),
            bottom.line.intersection(end.line),
            bottom.line.intersection(start.line),
        )
        frames.append(
            FixedFormatFrame(
                placement_geometry_id=_stable_id(
                    "frame-complete-format-chain",
                    sequence.placement_id,
                    cross.placement_id,
                    ordinal,
                ),
                lane_id=lane.lane_id,
                lane_ordinal=ordinal,
                top=top,
                bottom=bottom,
                start=start,
                end=end,
                canonical_source_polygon=polygon,
            )
        )
    return tuple(frames)


def _sequence_within_authority(
    placement: SequencePlacement,
    authority: FiniteInterval,
) -> bool:
    return all(
        authority.contains(position.minimum, epsilon=1.0e-8)
        and authority.contains(position.maximum, epsilon=1.0e-8)
        for position in placement.full_positions_px
    )


def _cross_within_authority(
    placement: CrossPlacement,
    authority: FiniteInterval,
) -> bool:
    return all(
        authority.contains(position.minimum, epsilon=1.0e-8)
        and authority.contains(position.maximum, epsilon=1.0e-8)
        for position in (
            *placement.top_full_positions_px,
            *placement.bottom_full_positions_px,
        )
    )


def _compatible_cross_proposals(
    lane_proposal: LanePhysicalProposals,
    frame_proposal: FrameChainProposals,
    direction: SharedStripDirection,
) -> tuple[CrossAxisProposal, ...]:
    selected_ids = {str(identity) for identity in direction.selected_observation_ids}
    return tuple(
        cross_proposal
        for cross_proposal in frame_proposal.cross_proposals
        if {
            str(observation.observation_id)
            for observation in cross_proposal.raw_observations
        }.issubset(selected_ids)
    )


def _direction_bound_cross_profile_runs(
    lane: LaneObservationInput,
    direction: SharedStripDirection,
    sequence_support_px: FiniteInterval,
) -> tuple[ProfileRun, ...]:
    """Aggregate registered transitions like a bounded multi-trace profile.

    V4.2.8's useful separator producer combined many scan lines before it
    localized an edge.  V5 keeps the stronger authority model: pixels have
    already been queried, the shared direction is cross_proposal-bound, and every
    aggregate run still consists solely of auditable transition identities.
    Two half-bin lattices prevent a real line from disappearing on one bin
    boundary; all structurally supported bins survive, so this is not top-K
    selection or a candidate score competition.
    """

    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    reference = lane.width_authority_px.center
    slope = canonical_source_cross_axis_slope(
        direction,
        lane.height_axis,
    )
    bin_width = max(
        1.0,
        spec.local_window_mm * lane.height_scale_px_per_mm.maximum,
    )
    values: list[ProfileRun] = []
    for role, measurement_set in (
        (BoundaryRole.TOP, lane.top_measurement_set),
        (BoundaryRole.BOTTOM, lane.bottom_measurement_set),
    ):
        queried = tuple(
            trace
            for trace in measurement_set.query.trace_positions_px
            if sequence_support_px.contains(float(trace), epsilon=0.5)
        )
        if not queried:
            continue
        queried_set = set(queried)
        minimum_support = max(
            spec.minimum_trace_count,
            math.ceil(spec.minimum_cross_fit_trace_fraction * len(queried)),
        )
        projected = tuple(
            (
                transition,
                transition.coordinate_px
                + slope * (reference - transition.trace_coordinate_px),
            )
            for transition in measurement_set.transitions
            if transition.trace_coordinate_px in queried_set
            and transition.polarity != 0
        )
        for polarity in (-1, 1):
            polarity_values = tuple(
                item for item in projected if item[0].polarity == polarity
            )
            for offset in (0.0, bin_width / 2.0):
                buckets: dict[int, dict[int, list[tuple[PhotoBoundaryTransition, float]]]] = {}
                for transition, coordinate in polarity_values:
                    bucket = math.floor((coordinate - offset) / bin_width)
                    buckets.setdefault(bucket, {}).setdefault(
                        transition.trace_coordinate_px,
                        [],
                    ).append((transition, coordinate))
                for bucket, by_trace in buckets.items():
                    center = offset + (bucket + 0.5) * bin_width
                    selected: list[tuple[PhotoBoundaryTransition, float]] = []
                    ambiguous = False
                    for trace in queried:
                        candidates = by_trace.get(trace, ())
                        if not candidates:
                            continue
                        ordered = sorted(
                            candidates,
                            key=lambda item: (
                                abs(item[1] - center),
                                str(item[0].transition_id),
                            ),
                        )
                        if (
                            len(ordered) > 1
                            and math.isclose(
                                abs(ordered[0][1] - center),
                                abs(ordered[1][1] - center),
                                abs_tol=1.0e-9,
                            )
                        ):
                            ambiguous = True
                            continue
                        selected.append(ordered[0])
                    traces = tuple(
                        sorted(item[0].trace_coordinate_px for item in selected)
                    )
                    continuity = continuous_trace_support_fraction(
                        queried,
                        traces,
                    )
                    if (
                        len(traces) < minimum_support
                        or continuity < spec.minimum_continuous_support_fraction
                        or not selected
                    ):
                        continue
                    transitions = tuple(item[0] for item in selected)
                    mean_gradient = sum(
                        item.gradient_z for item in transitions
                    ) / len(transitions)
                    mean_tone_or_texture = sum(
                        max(item.tone_z, item.texture_z)
                        for item in transitions
                    ) / len(transitions)
                    if (
                        mean_gradient < spec.gradient_z_minimum
                        or mean_tone_or_texture
                        < spec.tone_or_texture_z_minimum
                    ):
                        continue
                    coordinates = tuple(item[1] for item in selected)
                    coordinate_center = float(np.median(coordinates))
                    residual = float(
                        np.median(
                            np.abs(
                                np.asarray(coordinates, dtype=np.float64)
                                - coordinate_center
                            )
                        )
                    )
                    half_width = max(
                        item.coordinate_interval_px.width / 2.0
                        for item in transitions
                    )
                    identities = tuple(
                        sorted(
                            (item.transition_id for item in transitions),
                            key=str,
                        )
                    )
                    values.append(
                        ProfileRun(
                            run_id=_stable_id(
                                "direction-bound-cross-profile-run",
                                role.value,
                                polarity,
                                *(str(identity) for identity in identities),
                            ),
                            coordinate_interval_px=FiniteInterval(
                                coordinate_center - residual - half_width,
                                coordinate_center + residual + half_width,
                            ),
                            transition_ids=identities,
                            trace_coordinates_px=traces,
                            role_hint=role,
                            qualified_anchor_roles=(),
                            support_fraction=len(traces) / len(queried),
                            continuous_support_fraction=continuity,
                            fit_residual_px=residual,
                            evidence_strength=(
                                mean_gradient + mean_tone_or_texture
                            ),
                            pair_qualified=not ambiguous,
                        )
                    )
    unique = {
        (
            item.role_hint,
            tuple(map(str, item.transition_ids)),
        ): item
        for item in values
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.coordinate_interval_px.center,
                item.run_id,
            ),
        )
    )


def _staged_cross_proposals(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    direction: SharedStripDirection,
    sequence_support_px: FiniteInterval,
) -> tuple[CrossAxisProposal, ...]:
    """Rebind registered cross evidence inside one complete sequence span.

    The source-wide top/bottom lattice establishes possible shared directions.
    A partial strip, however, must not lose its actual photo edge merely because
    the rest of the scan canvas contains no frames.  This stage performs no new
    pixel query: it groups the already registered transition records again with
    support restricted to the full uncertain span of this sequence cross_proposal.
    """

    top_regions = track_side_transition_regions(
        (lane.top_measurement_set,),
        reference_trace_px=lane.width_authority_px.center,
        boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
        support_interval_px=sequence_support_px,
    )
    bottom_regions = track_side_transition_regions(
        (lane.bottom_measurement_set,),
        reference_trace_px=lane.width_authority_px.center,
        boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
        support_interval_px=sequence_support_px,
    )
    tracked_profile = cross_profile_from_regions(
        top_regions,
        bottom_regions,
        coordinate_count=(
            int(math.floor(lane.height_authority_px.maximum))
            - int(math.ceil(lane.height_authority_px.minimum))
            + 1
        ),
        transition_by_id=lane.transition_by_id,
    )
    aggregate_runs = _direction_bound_cross_profile_runs(
        lane,
        direction,
        sequence_support_px,
    )
    scoped_lane = replace(
        lane,
        cross_profile=BasicAxisProfile(
            "cross",
            tracked_profile.coordinate_count,
            tuple(
                sorted(
                    {
                        *tracked_profile.trace_coordinates_px,
                        *(
                            trace
                            for run in aggregate_runs
                            for trace in run.trace_coordinates_px
                        ),
                    }
                )
            ),
            tuple(
                sorted(
                    {
                        run.run_id: run
                        for run in (*tracked_profile.runs, *aggregate_runs)
                    }.values(),
                    key=lambda item: (
                        item.coordinate_interval_px.center,
                        item.run_id,
                    ),
                )
            ),
        ),
    )

    return tuple(
        cross_proposal
        for cross_proposal in build_cross_axis_proposals(
            scoped_lane,
            geometry,
            support_interval_px=sequence_support_px,
        )
        if all(
            _intersection(
                observation.angle_interval_degrees,
                direction.full_angle_interval_degrees,
            )
            is not None
            for observation in cross_proposal.raw_observations
        )
    )


def _materialize_frame_spec_seed(
    lane_proposal: LanePhysicalProposals,
    frame_proposal: FrameChainProposals,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    source_geometry: SourceScanGeometry | None = None,
) -> tuple[CompleteFormatChain, ...]:
    """Materialize one complete cross_proposal interpretation.

    A seed owns one correlated source-geometry and local-advance hypothesis.
    Conflicting interpretations remain separate physical placements.
    """

    lane = lane_proposal.lane
    compatible_cross_proposals = _compatible_cross_proposals(
        lane_proposal,
        frame_proposal,
        direction,
    )
    if not compatible_cross_proposals:
        return ()
    if source_geometry is None:
        try:
            geometry = _refine_source_geometry(
                lane,
                frame_proposal,
                direction,
                compatible_cross_proposals,
                sequence_seeds=(seed,),
            )
            bound_roles = _materialized_role_evidence(
                lane,
                seed.local_advance_proposals,
                direction,
            )
            observed_relations = _local_advance_relations(
                frame_proposal,
                geometry,
                _gap_model_from_bound_roles(
                    frame_proposal,
                    geometry,
                    lane.lane_id,
                    bound_roles,
                ),
                bound_roles,
            )
            joint_relations = _merge_local_advance_relations(
                seed.local_advance_relations,
                observed_relations,
            )
            if joint_relations != seed.local_advance_relations:
                seed = replace(
                    seed,
                    local_advance_relations=joint_relations,
                )
                geometry = _refine_source_geometry(
                    lane,
                    frame_proposal,
                    direction,
                    compatible_cross_proposals,
                    sequence_seeds=(seed,),
                )
        except ValueError:
            return ()
    else:
        if source_geometry.frame_spec != frame_proposal.frame_spec:
            raise ValueError("source geometry frame_spec disagrees")
        geometry = source_geometry
    try:
        sequence = _materialize_sequence_placement(
            lane,
            frame_proposal,
            seed,
            direction,
            geometry,
        )
    except ValueError:
        return ()
    if not _sequence_within_authority(sequence, lane.width_authority_px):
        return ()
    sequence_support_px = FiniteInterval(
        min(item.minimum for item in sequence.full_positions_px),
        max(item.maximum for item in sequence.full_positions_px),
    )
    staged_heights = _staged_cross_proposals(
        lane,
        geometry,
        direction,
        sequence_support_px,
    )
    if staged_heights:
        compatible_cross_proposals = tuple(
            {
                item.cross_proposal_id: item
                for item in (*compatible_cross_proposals, *staged_heights)
            }.values()
        )
        if source_geometry is None:
            try:
                geometry = _refine_source_geometry(
                    lane,
                    frame_proposal,
                    direction,
                    compatible_cross_proposals,
                    sequence_seeds=(seed,),
                )
                sequence = _materialize_sequence_placement(
                    lane,
                    frame_proposal,
                    seed,
                    direction,
                    geometry,
                )
            except ValueError:
                return ()
    if not _sequence_within_authority(sequence, lane.width_authority_px):
        return ()
    frame_references = tuple(
        (
            sequence.canonical_positions_px[index * 2]
            + sequence.canonical_positions_px[index * 2 + 1]
        )
        / 2.0
        for index in range(lane.output_slot_count)
    )
    frame_reference_intervals = tuple(
        FiniteInterval(
            (
                sequence.full_positions_px[index * 2].minimum
                + sequence.full_positions_px[index * 2 + 1].minimum
            )
            / 2.0,
            (
                sequence.full_positions_px[index * 2].maximum
                + sequence.full_positions_px[index * 2 + 1].maximum
            )
            / 2.0,
        )
        for index in range(lane.output_slot_count)
    )
    crosses: list[CrossPlacement] = []
    for cross_proposal in compatible_cross_proposals:
        try:
            crosses.append(
                _materialize_cross_placement(
                    lane,
                    cross_proposal,
                    direction,
                    geometry,
                    frame_references,
                    frame_reference_intervals,
                )
            )
        except ValueError:
            continue
    if not crosses:
        return ()
    unique_crosses = {item.placement_id: item for item in crosses}
    retained_crosses = tuple(
        unique_crosses[key]
        for key in sorted(unique_crosses)
        if _cross_within_authority(
            unique_crosses[key],
            lane.height_authority_px,
        )
    )
    if not retained_crosses:
        return ()
    height_by_id = {
        item.cross_proposal_id: item for item in compatible_cross_proposals
    }

    def lane_geometry_for(cross: CrossPlacement) -> LaneGeometry:
        centerlines = tuple(
            FiniteInterval(
                (top.minimum + bottom.minimum) / 2.0,
                (top.maximum + bottom.maximum) / 2.0,
            )
            for top, bottom in zip(
                cross.top_full_positions_px,
                cross.bottom_full_positions_px,
                strict=True,
            )
        )
        return LaneGeometry(
            lane_geometry_id=_stable_id(
                "lane-geometry",
                lane.lane_id,
                direction.direction_id,
                sequence.phase_full_interval_px.minimum,
                sequence.phase_full_interval_px.maximum,
                sequence.lane_gap_model.gap_model_id,
                *(value.minimum for value in centerlines),
                *(value.maximum for value in centerlines),
            ),
            lane_id=lane.lane_id,
            direction=direction,
            centerline_intervals_px=centerlines,
            sequence_phase_interval_px=sequence.phase_full_interval_px,
            gap_model=sequence.lane_gap_model,
            width_authority_px=lane.width_authority_px,
            height_authority_px=lane.height_authority_px,
        )

    return tuple(
        CompleteFormatChain(
            placement_id=_stable_id(
                "complete-format-chain",
                lane.lane_id,
                frame_proposal.frame_spec.frame_spec_id,
                direction.direction_id,
                geometry.geometry_id,
                sequence.placement_id,
                cross.placement_id,
            ),
            lane_id=lane.lane_id,
            frame_spec=frame_proposal.frame_spec,
            output_slot_count=lane.output_slot_count,
            source_scan_geometry=geometry,
            chain_proposal=seed,
            cross_proposal=height_by_id[cross.cross_proposal_id],
            lane_geometry=lane_geometry_for(cross),
            sequence=sequence,
            cross=cross,
            fixed_frames=FixedFormatFrameSet(
                fixed_frame_set_id=_stable_id(
                    "canonical-complete-format-chain",
                    sequence.placement_id,
                    cross.placement_id,
                ),
                sequence_placement_id=sequence.placement_id,
                cross_placement_id=cross.placement_id,
                frames=_canonical_frames(
                    lane,
                    direction,
                    sequence,
                    cross,
                ),
            ),
        )
        for cross in retained_crosses
    )


def rematerialize_complete_chain(
    lane_proposal: LanePhysicalProposals,
    chain: CompleteFormatChain,
    source_scan_geometry: SourceScanGeometry,
) -> CompleteFormatChain:
    """Apply the selected source-wide W/H state to one lane chain.

    Lane discovery may narrow the same source state from different physical
    strips.  Output geometry is materialized again from the selected joint
    state so two lanes cannot retain independent pixel scales.
    """

    frame_proposal = next(
        (
            item
            for item in lane_proposal.frame_proposals
            if item.frame_spec == chain.frame_spec
        ),
        None,
    )
    if frame_proposal is None:
        raise ValueError("selected chain has no frame proposal")
    candidates = _materialize_frame_spec_seed(
        lane_proposal,
        frame_proposal,
        chain.chain_proposal,
        chain.lane_geometry.direction,
        source_geometry=source_scan_geometry,
    )
    matches = tuple(
        item
        for item in candidates
        if item.cross_proposal.cross_proposal_id
        == chain.cross_proposal.cross_proposal_id
    )
    if len(matches) != 1:
        raise ValueError("source-wide W/H state cannot materialize selected chain")
    return replace(matches[0], placement_id=chain.placement_id)


def materialize_lane_placements(
    proposal: LanePhysicalProposals,
    direction: SharedStripDirection,
    registered_runs: dict[str, ProfileRun],
) -> tuple[tuple[CompleteFormatChain, ...], int]:
    proposed_unsorted = tuple(
        (frame_spec, seed)
        for frame_spec in sorted(
            proposal.frame_proposals,
            key=lambda item: item.frame_spec.frame_spec_id,
        )
        for seed in _frame_spec_materialization_seeds(
            proposal,
            frame_spec,
            direction,
            registered_runs,
        )
    )
    proposed = tuple(
        sorted(
            proposed_unsorted,
            key=lambda item: (
                -sum(
                    {
                        proposal.role.role
                        for proposal in item[1].role_proposals
                        if proposal.role.lane_ordinal == ordinal
                    }
                    == {BoundaryRole.START, BoundaryRole.END}
                    for ordinal in {
                        proposal.role.lane_ordinal for proposal in item[1].role_proposals
                    }
                ),
                -len({proposal.role.role_index for proposal in item[1].role_proposals}),
                min(proposal.role.lane_ordinal for proposal in item[1].role_proposals),
                tuple(
                    value
                    for proposal in item[1].role_proposals
                    for value in (
                        proposal.phase_interval_px.minimum.hex(),
                        proposal.phase_interval_px.maximum.hex(),
                    )
                ),
                tuple(
                    sorted(
                        str(identity)
                        for proposal in item[1].role_proposals
                        for identity in proposal.transition_ids
                    )
                ),
                item[0].frame_spec.frame_spec_id,
                item[1].chain_proposal_id,
            ),
        )
    )
    seed_materializations = tuple(
        placements
        for frame_spec, seed in proposed
        if (placements := _materialize_frame_spec_seed(
            proposal,
            frame_spec,
            seed,
            direction,
        ))
    )
    values = tuple(
        placement
        for placements in seed_materializations
        for placement in placements
    )
    unique = {item.placement_id: item for item in values}
    ordered = tuple(unique[key] for key in sorted(unique))
    proposed_count = max(len(proposed), len(ordered))
    return (
        ordered,
        proposed_count,
    )


def _basic_lane_structurally_closed(
    placements: tuple[CompleteFormatChain, ...],
) -> bool:
    return bool(placements) and all(
        placement.sequence.exclusion_authorized
        for placement in placements
    )


def materialize_source_placements(
    lane_proposals: tuple[LanePhysicalProposals, ...],
    lane_directions: tuple[SharedStripDirection, ...],
) -> SourcePlacementMaterialization:
    """Materialize every lane from one source-wide frame_spec geometry."""

    if not lane_proposals:
        return SourcePlacementMaterialization((), (), (), ())
    if len(lane_proposals) != len(lane_directions):
        raise ValueError("each lane requires one lane-owned direction")
    basic_independent = tuple(
        materialize_lane_placements(lane, direction, {})
        for lane, direction in zip(
            lane_proposals,
            lane_directions,
            strict=True,
        )
    )
    basic_closed = tuple(
        _basic_lane_structurally_closed(materialization[0])
        for materialization in basic_independent
    )
    if all(basic_closed):
        refined_lane_proposals = lane_proposals
        refinement_counts = [0 for _lane in lane_proposals]
        registered_runs_by_lane = [
            {} for _lane in refined_lane_proposals
        ]
        independent = basic_independent
    else:
        bound = tuple(
            (
                (lane, {}, 0)
                if closed
                else _bind_registered_sequence_roles(
                    _register_sequence_role_queries(lane),
                    direction,
                )
            )
            for lane, direction, closed in zip(
                lane_proposals,
                lane_directions,
                basic_closed,
                strict=True,
            )
        )
        refined_lane_proposals = tuple(item[0] for item in bound)
        registered_runs_by_lane = [item[1] for item in bound]
        refinement_counts = [item[2] for item in bound]
        independent = tuple(
            (
                basic
                if closed
                else materialize_lane_placements(
                    lane,
                    direction,
                    registered_runs,
                )
            )
            for lane, direction, registered_runs, basic, closed in zip(
                refined_lane_proposals,
                lane_directions,
                registered_runs_by_lane,
                basic_independent,
                basic_closed,
                strict=True,
            )
        )
    if len(refined_lane_proposals) > 2:
        raise ValueError("physical-chain source supports at most two lanes")
    return SourcePlacementMaterialization(
        placements_by_lane=tuple(item[0] for item in independent),
        proposed_complete_chain_counts_by_lane=tuple(
            item[1] for item in independent
        ),
        refinement_query_counts_by_lane=tuple(refinement_counts),
        lane_proposals=refined_lane_proposals,
    )
