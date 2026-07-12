from __future__ import annotations

from math import ceil

from ..detection.candidate.model import AssessedCandidate
from ..domain import Box
from ..output.frame_bleed import frame_bleed_plan
from ..output.model import AxisBleedParameters, FrameBleedPlan, FrameOverlapRequirement
from ..detection.physical.model import DualLaneSolution


def _frame_output_bounds(candidate: AssessedCandidate) -> tuple[Box, ...]:
    geometry = candidate.geometry
    if not isinstance(geometry, DualLaneSolution):
        return (geometry.holder_span.box,) * len(geometry.frames)
    bounds: list[Box] = []
    for frame in geometry.frames:
        center_y = 0.5 * float(frame.top + frame.bottom)
        matches = tuple(
            lane
            for lane in geometry.lane_boxes
            if float(lane.top) <= center_y < float(lane.bottom)
        )
        if len(matches) != 1:
            raise ValueError("frame must belong to exactly one output bound")
        bounds.append(matches[0])
    return tuple(bounds)


def _lane_frame_indexes(candidate: AssessedCandidate) -> tuple[tuple[int, ...], ...]:
    geometry = candidate.geometry
    if not isinstance(geometry, DualLaneSolution):
        return (tuple(range(len(geometry.frames))),)
    lane_indexes: list[list[int]] = [[] for _lane in geometry.lane_boxes]
    for frame_index, frame in enumerate(geometry.frames):
        center_y = 0.5 * float(frame.top + frame.bottom)
        matches = tuple(
            lane_index
            for lane_index, lane in enumerate(geometry.lane_boxes)
            if float(lane.top) <= center_y < float(lane.bottom)
        )
        if len(matches) != 1:
            raise ValueError("frame must belong to exactly one lane")
        lane_indexes[matches[0]].append(frame_index)
    return tuple(tuple(indexes) for indexes in lane_indexes)


def _overlap_requirements(
    candidate: AssessedCandidate,
) -> tuple[FrameOverlapRequirement, ...]:
    geometry = candidate.geometry
    lane_indexes = _lane_frame_indexes(candidate)
    requirements: list[FrameOverlapRequirement] = []
    for relation in geometry.inter_frame_spacings:
        if relation.signed_width_px.minimum >= 0.0:
            continue
        boundary = relation.boundary
        lane_index = 0 if boundary.lane_index is None else boundary.lane_index - 1
        if lane_index < 0 or lane_index >= len(lane_indexes):
            raise ValueError("inter-frame relation references a missing lane")
        frames = lane_indexes[lane_index]
        left_position = boundary.boundary_index - 1
        right_position = boundary.boundary_index
        if left_position < 0 or right_position >= len(frames):
            raise ValueError("inter-frame relation references a missing boundary")
        requirements.append(
            FrameOverlapRequirement(
                boundary=boundary,
                left_frame_index=frames[left_position],
                right_frame_index=frames[right_position],
                required_px=max(1, int(ceil(-relation.signed_width_px.minimum))),
                physically_supported=relation.supports_output_protection,
                provenance=(
                    f"{relation.provenance.root_measurement.value}:"
                    f"{relation.provenance.source}"
                ),
            )
        )
    return tuple(requirements)


def prepare_frame_bleed(
    candidate: AssessedCandidate,
    user_bleed: AxisBleedParameters,
) -> FrameBleedPlan:
    return frame_bleed_plan(
        frames=candidate.geometry.frames,
        frame_output_bounds=_frame_output_bounds(candidate),
        overlap_requirements=_overlap_requirements(candidate),
        user_bleed=user_bleed,
        layout=candidate.geometry.layout,
    )
