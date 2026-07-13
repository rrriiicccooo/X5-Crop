from __future__ import annotations

from .vocabulary import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_COUNT_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_FRAME_SEQUENCE_NOT_CONSERVED,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)
from ...output.model import FrameBleedPlan
from ..candidate.assessment.candidate_gate import CandidateGateAssessment
from ..candidate.selection.model import SelectionConsensus, SelectionResult
from x5crop.domain import EvidenceState
from ..gate_checks import GateCheck, GateStage
from ..evidence.transform_geometry import TransformGeometryEvidence
from .model import DecisionGateAssessment


_CANDIDATE_REASON_BY_CHECK = {
    "content_preservation": FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    "photo_geometry_consistency": FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    "frame_sequence_conservation": FINAL_REASON_FRAME_SEQUENCE_NOT_CONSERVED,
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
        stage=GateStage.DECISION,
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
    candidate_gate: CandidateGateAssessment | None,
    automatic_processing: EvidenceState,
    selection_consensus: EvidenceState,
    output_protection: EvidenceState,
    transform_geometry: EvidenceState,
    count_resolution: EvidenceState,
    geometry_resolution: EvidenceState,
) -> DecisionGateAssessment:
    if (
        automatic_processing != EvidenceState.CONTRADICTED
        and candidate_gate is None
    ):
        raise ValueError("automatic processing requires CandidateGate")
    candidate_checks = (
        ()
        if automatic_processing == EvidenceState.CONTRADICTED
        or candidate_gate is None
        else _project_candidate_checks(candidate_gate)
    )
    checks = (
        *candidate_checks,
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
) -> DecisionGateAssessment:
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
        and candidate_gate is not None
        and candidate_gate.passed
    )
    if final_stage_applicable:
        count_resolution_state = (
            EvidenceState.SUPPORTED
            if resolution.count_resolved and resolution.larger_counts_evaluated
            else EvidenceState.CONTRADICTED
        )
        if (
            count_resolution_state != EvidenceState.SUPPORTED
            or selection.consensus == SelectionConsensus.DISAGREED
        ):
            geometry_resolution_state = EvidenceState.NOT_APPLICABLE
        elif resolution.state == EvidenceState.SUPPORTED:
            geometry_resolution_state = EvidenceState.SUPPORTED
        else:
            geometry_resolution_state = EvidenceState.CONTRADICTED
        selection_consensus_state = (
            EvidenceState.CONTRADICTED
            if selection.consensus == SelectionConsensus.DISAGREED
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
    return decision_gate
