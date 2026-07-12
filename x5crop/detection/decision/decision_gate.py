from __future__ import annotations

from .vocabulary import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_COUNT_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_FRAME_SEQUENCE_NOT_CONSERVED,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)
from ...domain import Box, CropEnvelope
from ...geometry.boxes import map_work_box
from ...output.model import FrameBleedPlan, OutputGeometry
from ...units import ScanCalibration
from ..candidate.assessment.candidate_gate import CandidateGateAssessment
from ..candidate.selection.model import SelectionResult
from x5crop.domain import EvidenceState
from ..gate_checks import GateCheck
from ..evidence.transform_geometry import TransformGeometryEvidence
from ..physical.model import DualLaneSolution
from .model import DecisionGateAssessment, DecisionResult


_CANDIDATE_REASON_BY_CHECK = {
    "frame_topology_integrity": FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    "content_preservation": FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    "photo_geometry_consistency": FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    "frame_sequence_conservation": FINAL_REASON_FRAME_SEQUENCE_NOT_CONSERVED,
    "evidence_independence": FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    "boundary_proof": FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
}


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


def _decision_check(
    code: str,
    state: EvidenceState,
    final_reason: str,
) -> GateCheck:
    return GateCheck(
        code=code,
        stage="decision",
        state=state,
        final_review_reason=final_reason,
    )


def _project_candidate_checks(
    candidate_gate: CandidateGateAssessment,
) -> tuple[GateCheck, ...]:
    checks: list[GateCheck] = []
    for check in candidate_gate.checks:
        if not check.blocks:
            continue
        final_reason = _CANDIDATE_REASON_BY_CHECK.get(check.code)
        if final_reason is None:
            raise ValueError(f"unowned candidate gate check: {check.code}")
        checks.append(
            _decision_check(
                f"candidate_{check.code}",
                EvidenceState.CONTRADICTED,
                final_reason,
            )
        )
    return tuple(checks)


def decision_gate_assessment(
    *,
    candidate_gate: CandidateGateAssessment,
    automatic_processing: EvidenceState,
    selection_consensus: EvidenceState,
    output_protection: EvidenceState,
    transform_geometry: EvidenceState,
    count_resolution: EvidenceState,
    geometry_resolution: EvidenceState,
) -> DecisionGateAssessment:
    checks = (
        *(
            ()
            if automatic_processing == EvidenceState.CONTRADICTED
            else _project_candidate_checks(candidate_gate)
        ),
        _decision_check(
            "count_resolution",
            count_resolution,
            FINAL_REASON_COUNT_RESOLUTION_UNAVAILABLE,
        ),
        _decision_check(
            "geometry_resolution",
            geometry_resolution,
            FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
        ),
        _decision_check(
            "automatic_processing_eligibility",
            automatic_processing,
            FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
        ),
        _decision_check(
            "selection_geometry_consensus",
            selection_consensus,
            FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
        ),
        _decision_check(
            "output_content_protection",
            output_protection,
            FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
        ),
        _decision_check(
            "transform_geometry_integrity",
            transform_geometry,
            FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
        ),
    )
    return DecisionGateAssessment(checks=checks)


def apply_decision_gate(
    selection: SelectionResult,
    frame_bleed_plan: FrameBleedPlan,
    transform_geometry: TransformGeometryEvidence,
    scan_calibration: ScanCalibration,
    *,
    image_width: int,
    image_height: int,
) -> DecisionResult:
    selected = selection.selected
    candidate_gate = selected.assessment.gate
    resolution = selection.geometry_resolution
    automatic_processing_state = (
        EvidenceState.SUPPORTED
        if selected.geometry.automatic_processing_supported
        else EvidenceState.CONTRADICTED
    )
    final_stage_applicable = bool(
        automatic_processing_state == EvidenceState.SUPPORTED
        and candidate_gate.passed
    )
    if final_stage_applicable:
        count_resolution_state = (
            EvidenceState.SUPPORTED
            if resolution.count_resolved and resolution.larger_counts_evaluated
            else EvidenceState.CONTRADICTED
        )
        geometry_resolution_state = (
            EvidenceState.NOT_APPLICABLE
            if count_resolution_state != EvidenceState.SUPPORTED
            else EvidenceState.SUPPORTED
            if (
                resolution.placement_resolved
                and resolution.boundaries_resolved
                and resolution.content_preservation_compatible
            )
            else EvidenceState.CONTRADICTED
        )
        selection_consensus_state = (
            EvidenceState.CONTRADICTED
            if selection.consensus == "disagreed"
            else EvidenceState.SUPPORTED
        )
        output_protection_state = (
            EvidenceState.SUPPORTED
            if frame_bleed_plan.feasible
            else EvidenceState.CONTRADICTED
        )
        transform_geometry_state = transform_geometry.state
    else:
        count_resolution_state = EvidenceState.NOT_APPLICABLE
        geometry_resolution_state = EvidenceState.NOT_APPLICABLE
        selection_consensus_state = EvidenceState.NOT_APPLICABLE
        output_protection_state = EvidenceState.NOT_APPLICABLE
        transform_geometry_state = EvidenceState.NOT_APPLICABLE
    decision_gate = decision_gate_assessment(
        candidate_gate=candidate_gate,
        automatic_processing=automatic_processing_state,
        selection_consensus=selection_consensus_state,
        output_protection=output_protection_state,
        transform_geometry=transform_geometry_state,
        count_resolution=count_resolution_state,
        geometry_resolution=geometry_resolution_state,
    )
    geometry = OutputGeometry(
        crop_envelope=CropEnvelope(
            map_work_box(
                selected.geometry.crop_envelope.box,
                selected.geometry.layout,
                image_width,
                image_height,
            )
        ),
        frames=tuple(
            map_work_box(
                frame,
                selected.geometry.layout,
                image_width,
                image_height,
            )
            for frame in _crop_envelope_frames(selection)
        ),
    )
    return DecisionResult(
        format_id=selected.geometry.format_id,
        layout=selected.geometry.layout,
        strip_mode=selected.geometry.strip_mode,
        count=selected.geometry.count,
        decision_gate=decision_gate,
        decision_geometry=geometry,
        frame_bleed_plan=frame_bleed_plan,
        scan_calibration=scan_calibration,
        diagnostics=selected.assessment.gate.diagnostics,
    )
