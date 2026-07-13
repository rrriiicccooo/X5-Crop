from __future__ import annotations

from dataclasses import replace
from math import ceil

from ..detection.candidate.model import CandidateEvidence, DualLaneEvidence
from ..detection.candidate.selection.model import SelectionResult
from ..domain import Box, InterPhotoBoundaryReference
from ..output.frame_bleed import frame_bleed_plan
from ..output.model import AxisBleedParameters, FrameBleedPlan, FrameOverlapRequirement
from ..detection.physical.model import DualLanePhotoSolution


def _frame_output_bounds(selection: SelectionResult) -> tuple[Box, ...]:
    geometry = selection.selected.geometry
    envelopes = geometry.frame_crop_envelopes
    if not isinstance(geometry, DualLanePhotoSolution):
        return (geometry.holder_span.box,) * len(envelopes)
    bounds: list[Box] = []
    for envelope in envelopes:
        center_y = 0.5 * float(envelope.box.top + envelope.box.bottom)
        matches = tuple(
            lane
            for lane in geometry.lane_boxes
            if float(lane.top) <= center_y < float(lane.bottom)
        )
        if len(matches) != 1:
            raise ValueError("frame must belong to exactly one output bound")
        bounds.append(matches[0])
    return tuple(bounds)


def _lane_frame_indexes(selection: SelectionResult) -> tuple[tuple[int, ...], ...]:
    geometry = selection.selected.geometry
    envelopes = geometry.frame_crop_envelopes
    if not isinstance(geometry, DualLanePhotoSolution):
        return (tuple(range(len(envelopes))),)
    lane_indexes: list[list[int]] = [[] for _lane in geometry.lane_boxes]
    for frame_index, envelope in enumerate(envelopes):
        center_y = 0.5 * float(envelope.box.top + envelope.box.bottom)
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
    selection: SelectionResult,
) -> tuple[FrameOverlapRequirement, ...]:
    evidence = selection.selected.assessment.evidence
    if isinstance(evidence, CandidateEvidence):
        relations = tuple(
            observation.spacing_evidence
            for observation in evidence.inter_photo_boundary_preservation.observations
        )
    elif isinstance(evidence, DualLaneEvidence):
        relations = tuple(
            replace(
                observation.spacing_evidence,
                boundary=InterPhotoBoundaryReference(
                    lane_index,
                    observation.boundary.boundary_index,
                ),
            )
            for lane_index, lane_evidence in enumerate(
                evidence.lane_evidence,
                start=1,
            )
            for observation in (
                lane_evidence.inter_photo_boundary_preservation.observations
            )
        )
    else:
        relations = ()
    lane_indexes = _lane_frame_indexes(selection)
    requirements: list[FrameOverlapRequirement] = []
    for relation in relations:
        if relation.kind != "overlap":
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
                    f"{relation.provenance.observation_id}"
                ),
            )
        )
    return tuple(requirements)


def prepare_frame_bleed(
    selection: SelectionResult,
    user_bleed: AxisBleedParameters,
) -> FrameBleedPlan:
    geometry = selection.selected.geometry
    if not selection.geometry_resolution.supported:
        return frame_bleed_plan(
            frames=(),
            frame_output_bounds=(),
            overlap_requirements=(),
            user_bleed=user_bleed,
            layout=geometry.layout,
        )
    frames = tuple(item.box for item in geometry.frame_crop_envelopes)
    return frame_bleed_plan(
        frames=frames,
        frame_output_bounds=_frame_output_bounds(selection),
        overlap_requirements=_overlap_requirements(selection),
        user_bleed=user_bleed,
        layout=geometry.layout,
    )
