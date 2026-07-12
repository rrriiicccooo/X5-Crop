from __future__ import annotations

from math import ceil

from ..detection.candidate.model import AssessedCandidate
from ..domain import AxisBleedParameters, CropEnvelope
from ..output.frame_bleed import frame_bleed_plan
from ..output.model import FrameBleedPlan, FrameOverlapRequirement
from ..detection.physical.model import DualLaneSolution


def _frame_crop_envelopes(candidate: AssessedCandidate) -> tuple[CropEnvelope, ...]:
    geometry = candidate.geometry
    if not isinstance(geometry, DualLaneSolution):
        return (geometry.crop_envelope,) * len(geometry.frames)
    envelopes: list[CropEnvelope] = []
    for frame in geometry.frames:
        center_y = 0.5 * float(frame.top + frame.bottom)
        matches = tuple(
            envelope
            for lane, envelope in zip(
                geometry.lane_boxes,
                geometry.lane_crop_envelopes,
                strict=True,
            )
            if float(lane.top) <= center_y < float(lane.bottom)
        )
        if len(matches) != 1:
            raise ValueError("frame must belong to exactly one crop envelope")
        envelopes.append(matches[0])
    return tuple(envelopes)


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
    lane_indexes = _lane_frame_indexes(candidate)
    requirements: list[FrameOverlapRequirement] = []
    for relation in candidate.assessment.evidence.frame_sequence.spacings:
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
                    f"{relation.provenance.root_measurement}:"
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
        frame_crop_envelopes=_frame_crop_envelopes(candidate),
        overlap_requirements=_overlap_requirements(candidate),
        user_bleed=user_bleed,
        layout=candidate.geometry.layout,
    )
