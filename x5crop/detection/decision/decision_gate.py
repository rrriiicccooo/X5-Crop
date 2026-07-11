from __future__ import annotations

from ...constants import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)
from ...domain import OutputProtectionPlan
from ...geometry.boxes import map_work_box
from ...output.model import OutputGeometry
from ...units import ScanCalibration
from ..candidate.assessment.candidate_gate import CandidateGateAssessment
from ..candidate.selection.model import SelectionResult
from ..evidence.exposure_overlap import ExposureOverlapEvidence
from ..evidence.state import EvidenceState
from ..gate_checks import GateCheck
from ..evidence.transform_geometry import TransformGeometryEvidence
from .model import DecisionGateAssessment, FinalDetection, FinalDetectionTrace


_CANDIDATE_REASON_BY_CHECK = {
    "frame_topology_integrity": FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    "content_preservation": FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    "photo_geometry_consistency": FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    "evidence_independence": FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    "boundary_proof": FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
}


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
    output_protection: EvidenceState,
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
            "output_content_protection",
            output_protection,
            FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
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
    output_protection_plan: OutputProtectionPlan,
    exposure_overlap: ExposureOverlapEvidence,
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
        output_protection=(
            EvidenceState.SUPPORTED
            if output_protection_plan.feasible
            else EvidenceState.CONTRADICTED
        ),
        transform_geometry=transform_geometry,
    )
    geometry = OutputGeometry(
        outer=map_work_box(
            selected.geometry.crop_envelope.box,
            selected.geometry.layout,
            image_width,
            image_height,
        ),
        frames=tuple(
            map_work_box(
                frame,
                selected.geometry.layout,
                image_width,
                image_height,
            )
            for frame in selected.geometry.frames
        ),
    )
    return FinalDetection(
        format_id=selected.geometry.format_id,
        layout=selected.geometry.layout,
        strip_mode=selected.geometry.strip_mode,
        count=selected.geometry.count,
        confidence=selected.assessment.scores.confidence,
        work_film_span=selected.geometry.visible_sequence_span.box,
        pitch=selected.geometry.pitch,
        decision_gate=decision_gate,
        decision_geometry=geometry,
        output_geometry=geometry,
        separator_observations=selected.geometry.separators,
        output_protection=output_protection_plan,
        scan_calibration=scan_calibration,
        diagnostics=selected.assessment.diagnostics,
        trace=FinalDetectionTrace(
            selection=selection,
            exposure_overlap=exposure_overlap,
        ),
    )
