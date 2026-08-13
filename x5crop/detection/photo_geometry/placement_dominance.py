"""Selected-envelope relations that never mix physical evidence axes."""

from __future__ import annotations

from .chains import CompleteFormatChain
def minimum_safe_outer_boundary_relation(
    left_placement_ids: tuple[str, ...],
    right_placement_ids: tuple[str, ...],
    placements_by_id: dict[str, CompleteFormatChain],
) -> int | None:
    """Compare only differing first/last edges of one sequence core.

    Content veto has already established that either outer alternative is
    safe.  A later outer start or earlier outer end retains the smaller fixed
    format placement.  Direction-induced raster rounding on internal frames
    is deliberately irrelevant: it is not another physical edge vote.
    """

    if len(left_placement_ids) != len(right_placement_ids):
        return None
    left_not_wider = True
    right_not_wider = True
    left_strict = False
    right_strict = False
    for left_id, right_id in zip(
        left_placement_ids,
        right_placement_ids,
        strict=True,
    ):
        left = placements_by_id[left_id]
        right = placements_by_id[right_id]
        if (
            left.output_slot_count != right.output_slot_count
            or left.source_scan_geometry.frame_spec
            != right.source_scan_geometry.frame_spec
        ):
            return None
        final_role_index = left.output_slot_count * 2 - 1

        def role_observation_id(
            placement: CompleteFormatChain,
            role_index: int,
        ) -> ObservationId | None:
            return next(
                (
                    item.observation_id
                    for item in placement.sequence.observations
                    if item.role.role_index == role_index
                ),
                None,
            )

        if role_observation_id(left, 0) != role_observation_id(right, 0):
            left_start = left.fixed_frames.frames[0].start.full_position_interval_px
            right_start = right.fixed_frames.frames[0].start.full_position_interval_px
            if left_start.minimum < right_start.minimum:
                left_not_wider = False
                right_strict = True
            elif left_start.minimum > right_start.minimum:
                right_not_wider = False
                left_strict = True
        if role_observation_id(left, final_role_index) != role_observation_id(
            right,
            final_role_index,
        ):
            left_end = left.fixed_frames.frames[-1].end.full_position_interval_px
            right_end = right.fixed_frames.frames[-1].end.full_position_interval_px
            if left_end.maximum > right_end.maximum:
                left_not_wider = False
                right_strict = True
            elif left_end.maximum < right_end.maximum:
                right_not_wider = False
                left_strict = True
    if left_not_wider and left_strict:
        return 1
    if right_not_wider and right_strict:
        return -1
    if left_not_wider and right_not_wider:
        return 0
    return None
