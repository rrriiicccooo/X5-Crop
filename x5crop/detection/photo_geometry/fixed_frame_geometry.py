"""Materialize fixed-format frame boundaries from one complete axis pair."""

from __future__ import annotations

from ...domain import FiniteInterval, ObservationId
from .boundary_geometry import canonical_boundary_line
from .chains import (
    CrossPlacement,
    FixedFormatFrame,
    SequencePlacement,
)
from .chain_proposals import LaneObservationInput
from .interval_math import add, common, hull, intersect, subtract
from .model import (
    BoundaryRole,
    DirectionAuthority,
    PositionSource,
)
from .output_model import FrameBoundaryGeometry, SharedStripDirection
from .physical_identity import physical_fact_id


def _boundary_geometry(
    *,
    role: BoundaryRole,
    canonical_position_px: float,
    full_position_interval_px: FiniteInterval,
    reference_trace_px: float,
    support_projection_px: FiniteInterval,
    lane: LaneObservationInput,
    direction: SharedStripDirection,
    observation_ids: tuple[ObservationId, ...],
    position_source: PositionSource,
    named_position_inference: str | None,
    sequence_direction_interval_degrees: FiniteInterval | None = None,
    sequence_direction_reference_id: str | None = None,
    cross_direction_interval_degrees: FiniteInterval | None = None,
) -> FrameBoundaryGeometry:
    if not observation_ids:
        raise ValueError("frame boundary requires position evidence")
    boundary_axis = (
        lane.width_axis
        if role in {BoundaryRole.START, BoundaryRole.END}
        else lane.height_axis
    )
    return FrameBoundaryGeometry(
        role=role,
        line=canonical_boundary_line(
            direction,
            boundary_axis=boundary_axis,
            source_axis_long=lane.width_axis,
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
            else (
                cross_direction_interval_degrees
                or direction.full_angle_interval_degrees
            )
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


def correlated_fixed_width_intervals(
    start: FiniteInterval,
    end: FiniteInterval,
    width: FiniteInterval,
    *,
    start_direct: bool,
    end_direct: bool,
) -> tuple[FiniteInterval, FiniteInterval]:
    """Retain the exact opposite-side relation of one fixed-width frame."""

    if start_direct and not end_direct:
        inferred_end = intersect(end, add(start, width))
        if inferred_end is None:
            raise ValueError("direct start contradicts shared frame width")
        return start, inferred_end
    if end_direct and not start_direct:
        inferred_start = intersect(start, subtract(end, width))
        if inferred_start is None:
            raise ValueError("direct end contradicts shared frame width")
        return inferred_start, end
    return start, end


def canonical_frames(
    lane: LaneObservationInput,
    direction: SharedStripDirection,
    sequence: SequencePlacement,
    cross: CrossPlacement,
    frame_width_px: FiniteInterval,
) -> tuple[FixedFormatFrame, ...]:
    sequence_observations: dict[int, tuple[ObservationId, ...]] = {}
    sequence_safety_intervals: dict[int, FiniteInterval] = {}
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
            safety = common(
                tuple(
                    item.safety_position_interval_px
                    for item in sequence.observations
                    if item.role.role_index == role_index
                )
            )
            if safety is not None:
                sequence_safety_intervals[role_index] = safety
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
    direct_cross_by_role = {
        item.role: tuple(item.observation.transition_ids)
        for item in cross.evidence
    }
    cross_by_role = {
        role: tuple(
            ObservationId(value)
            for value in sorted(
                str(item) for item in direct_cross_by_role.get(role, ())
            )
        )
        for role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        if role in direct_cross_by_role
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
    retained_cross_directions = {
        item.role: item.observation.angle_interval_degrees
        for item in cross.evidence
    }

    def cross_direction_interval(role: BoundaryRole) -> FiniteInterval:
        observed = retained_cross_directions.get(role)
        opposite = retained_cross_directions.get(
            BoundaryRole.BOTTOM
            if role == BoundaryRole.TOP
            else BoundaryRole.TOP
        )
        if observed is not None:
            retained = observed
        elif opposite is not None:
            retained = opposite
        else:
            retained = direction.full_angle_interval_degrees
        return hull(
            (
                retained,
                FiniteInterval.exact(direction.canonical_angle_degrees),
            )
        )

    def sequence_direction_interval(
        role_index: int,
        opposite_role_index: int,
    ) -> FiniteInterval:
        retained = sequence.role_full_direction_intervals_degrees[role_index]
        if (
            role_index not in sequence_observations
            and opposite_role_index in sequence_observations
        ):
            retained = hull(
                (
                    retained,
                    sequence.role_full_direction_intervals_degrees[
                        opposite_role_index
                    ],
                )
            )
        return hull(
            (
                retained,
                FiniteInterval.exact(direction.canonical_angle_degrees),
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
        start_ids = sequence_observations.get(start_index, ()) or all_sequence_ids
        end_ids = sequence_observations.get(end_index, ()) or all_sequence_ids
        start_interval, end_interval = correlated_fixed_width_intervals(
            sequence.full_positions_px[start_index],
            sequence.full_positions_px[end_index],
            frame_width_px,
            start_direct=start_index in sequence_observations,
            end_direct=end_index in sequence_observations,
        )
        width_support = FiniteInterval(
            start_interval.minimum,
            end_interval.maximum,
        )
        top_ids = cross_by_role.get(BoundaryRole.TOP, all_cross_ids)
        bottom_ids = cross_by_role.get(BoundaryRole.BOTTOM, all_cross_ids)
        start = _boundary_geometry(
            role=BoundaryRole.START,
            canonical_position_px=sequence.canonical_positions_px[start_index],
            full_position_interval_px=hull(
                (
                    start_interval,
                    sequence_safety_intervals.get(
                        start_index,
                        start_interval,
                    ),
                )
            ),
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            lane=lane,
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
                sequence_direction_interval(start_index, end_index)
            ),
            sequence_direction_reference_id=sequence.placement_id,
        )
        end = _boundary_geometry(
            role=BoundaryRole.END,
            canonical_position_px=sequence.canonical_positions_px[end_index],
            full_position_interval_px=hull(
                (
                    end_interval,
                    sequence_safety_intervals.get(
                        end_index,
                        end_interval,
                    ),
                )
            ),
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            lane=lane,
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
                sequence_direction_interval(end_index, start_index)
            ),
            sequence_direction_reference_id=sequence.placement_id,
        )
        top = _boundary_geometry(
            role=BoundaryRole.TOP,
            canonical_position_px=cross.top_canonical_positions_px[ordinal - 1],
            full_position_interval_px=cross.top_full_positions_px[ordinal - 1],
            reference_trace_px=frame_reference,
            support_projection_px=width_support,
            lane=lane,
            direction=direction,
            observation_ids=top_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.TOP in direct_cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.TOP in direct_cross_by_role
                else "top_from_observed_bottom_and_source_height"
            ),
            cross_direction_interval_degrees=(
                cross_direction_interval(BoundaryRole.TOP)
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
            lane=lane,
            direction=direction,
            observation_ids=bottom_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.BOTTOM in direct_cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.BOTTOM in direct_cross_by_role
                else "bottom_from_observed_top_and_source_height"
            ),
            cross_direction_interval_degrees=(
                cross_direction_interval(BoundaryRole.BOTTOM)
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
                placement_geometry_id=physical_fact_id(
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
