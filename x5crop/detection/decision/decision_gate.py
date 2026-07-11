from __future__ import annotations

from ...constants import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    FINAL_REASON_FRAME_SEQUENCE_NOT_CONSERVED,
    FINAL_REASON_OUTPUT_BLEED_UNRESOLVED,
    FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)
from ...domain import Box, CropEnvelope, OutputBleedPlan
from ...geometry.boxes import map_work_box
from ...output.model import OutputGeometry
from ...units import ScanCalibration
from ..candidate.assessment.candidate_gate import CandidateGateAssessment
from ..candidate.selection.model import SelectionResult
from x5crop.domain import EvidenceState
from ..gate_checks import GateCheck
from ..evidence.transform_geometry import TransformGeometryEvidence
from .model import DecisionGateAssessment, FinalDetection


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
    if not geometry.lane_crop_envelopes:
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
        consequence="blocker",
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
    output_bleed: EvidenceState,
    transform_geometry: TransformGeometryEvidence,
) -> DecisionGateAssessment:
    checks = (
        *_project_candidate_checks(candidate_gate),
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
            "output_bleed_feasibility",
            output_bleed,
            FINAL_REASON_OUTPUT_BLEED_UNRESOLVED,
        ),
        _decision_check(
            "transform_geometry_integrity",
            transform_geometry.state,
            FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
        ),
    )
    return DecisionGateAssessment(checks=checks)


def apply_decision_gate(
    selection: SelectionResult,
    output_bleed_plan: OutputBleedPlan,
    transform_geometry: TransformGeometryEvidence,
    scan_calibration: ScanCalibration,
    *,
    image_width: int,
    image_height: int,
) -> FinalDetection:
    selected = selection.selected
    candidate_gate = selected.assessment.gate
    decision_gate = decision_gate_assessment(
        candidate_gate=candidate_gate,
        automatic_processing=(
            EvidenceState.SUPPORTED
            if selected.geometry.automatic_processing_supported
            else EvidenceState.CONTRADICTED
        ),
        selection_consensus=(
            EvidenceState.CONTRADICTED
            if selection.consensus == "disagreed"
            else EvidenceState.SUPPORTED
        ),
        output_bleed=(
            EvidenceState.SUPPORTED
            if output_bleed_plan.feasible
            else EvidenceState.CONTRADICTED
        ),
        transform_geometry=transform_geometry,
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
    return FinalDetection(
        format_id=selected.geometry.format_id,
        layout=selected.geometry.layout,
        strip_mode=selected.geometry.strip_mode,
        count=selected.geometry.count,
        confidence=selected.assessment.scores.confidence,
        visible_sequence_span=selected.geometry.visible_sequence_span,
        crop_envelope=selected.geometry.crop_envelope,
        decision_gate=decision_gate,
        decision_geometry=geometry,
        output_geometry=geometry,
        separator_observations=selected.geometry.separator_observations,
        separator_assignments=selected.geometry.separator_assignments,
        frame_boundaries=selected.geometry.frame_boundaries,
        output_bleed_plan=output_bleed_plan,
        scan_calibration=scan_calibration,
        diagnostics=selected.assessment.diagnostics,
        selection=selection,
    )
