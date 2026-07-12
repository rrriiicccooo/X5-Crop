from __future__ import annotations

from ...domain import Box, CropEnvelope
from ...geometry.boxes import map_work_box
from ...output.model import FrameBleedPlan, OutputGeometry
from ..candidate.selection.model import SelectionResult
from ..decision.model import DecisionGateAssessment
from ..physical.model import DualLaneSolution
from .model import FinalDetection, FinalizationPlan


def _crop_envelope_frames(selection: SelectionResult) -> tuple[Box, ...]:
    geometry = selection.selected.geometry
    if not isinstance(geometry, DualLaneSolution):
        envelope = geometry.crop_envelope.box
        last_index = len(geometry.frames) - 1
        return tuple(
            Box(
                envelope.left if index == 0 else frame.left,
                envelope.top,
                envelope.right if index == last_index else frame.right,
                envelope.bottom,
            )
            for index, frame in enumerate(geometry.frames)
        )
    if len(geometry.lane_boxes) != len(geometry.lane_crop_envelopes):
        raise ValueError("dual-lane geometry requires one crop envelope per lane")
    lane_frame_indexes: list[list[int]] = [
        [] for _lane in geometry.lane_boxes
    ]
    for frame_index, frame in enumerate(geometry.frames):
        center_y = 0.5 * float(frame.top + frame.bottom)
        matches = tuple(
            lane_index
            for lane_index, lane in enumerate(geometry.lane_boxes)
            if float(lane.top) <= center_y < float(lane.bottom)
        )
        if len(matches) != 1:
            raise ValueError("frame must belong to exactly one dual-lane region")
        lane_frame_indexes[matches[0]].append(frame_index)
    frames = list(geometry.frames)
    for lane_index, indexes in enumerate(lane_frame_indexes):
        if not indexes:
            raise ValueError("dual-lane region has no frames")
        envelope = geometry.lane_crop_envelopes[lane_index].box
        for position, frame_index in enumerate(indexes):
            frame = frames[frame_index]
            frames[frame_index] = Box(
                envelope.left if position == 0 else frame.left,
                envelope.top,
                envelope.right if position == len(indexes) - 1 else frame.right,
                envelope.bottom,
            )
    return tuple(frames)


def finalization_plan_for_selection(
    selection: SelectionResult,
    frame_bleed_plan: FrameBleedPlan,
    *,
    image_width: int,
    image_height: int,
) -> FinalizationPlan:
    geometry = selection.selected.geometry
    decision_geometry = OutputGeometry(
        crop_envelope=CropEnvelope(
            map_work_box(
                geometry.crop_envelope.box,
                geometry.layout,
                image_width,
                image_height,
            )
        ),
        frames=tuple(
            map_work_box(
                frame,
                geometry.layout,
                image_width,
                image_height,
            )
            for frame in _crop_envelope_frames(selection)
        ),
    )
    return FinalizationPlan(
        layout=geometry.layout,
        image_width=image_width,
        image_height=image_height,
        decision_geometry=decision_geometry,
        frame_bleed_plan=frame_bleed_plan,
    )


def finalize_detection(
    decision: DecisionGateAssessment,
    finalization_plan: FinalizationPlan,
) -> FinalDetection:
    return FinalDetection(
        decision=decision,
        finalization_plan=finalization_plan,
    )
