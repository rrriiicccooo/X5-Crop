from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ...constants import (
    CANDIDATE_SOURCE_HARD_SAFETY,
    CANDIDATE_SOURCE_REVIEW_ONLY,
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
from ...domain import DetectionCandidate, FinalDetection, OutputProtectionPlan
from ..evidence.content.preservation import ContentPreservationEvidence, content_preservation_evidence
from ..evidence.state import EvidenceState
from ..gate_checks import GateCheck, gate_check_details
from .evidence_summary import evidence_summary_for


_CANDIDATE_REASON_BY_CHECK = {
    "frame_topology_integrity": FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    "content_preservation": FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    "photo_geometry_consistency": FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    "evidence_independence": FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    "boundary_proof": FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
}


@dataclass(frozen=True)
class DecisionGateInput:
    candidate_gate: dict[str, Any]
    automatic_processing: EvidenceState
    content_preservation: ContentPreservationEvidence
    selection_consensus: EvidenceState
    output_protection: EvidenceState
    transform_geometry: EvidenceState


@dataclass(frozen=True)
class DecisionGateAssessment:
    passed: bool
    checks: tuple[GateCheck, ...]
    final_review_reasons: tuple[str, ...]
    reason_inputs: tuple[dict[str, str], ...]

    def report_detail(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "checks": gate_check_details(list(self.checks)),
            "reason_inputs": [dict(item) for item in self.reason_inputs],
        }


def _decision_check(
    code: str,
    state: EvidenceState,
    final_reason: str,
    *,
    detail: dict[str, Any] | None = None,
) -> GateCheck:
    return GateCheck(
        code=code,
        stage="decision",
        state=state,
        consequence="blocker",
        detail={"final_review_reason": final_reason, **(detail or {})},
    )


def _project_candidate_checks(candidate_gate: dict[str, Any]) -> list[GateCheck]:
    projected: list[GateCheck] = []
    checks = candidate_gate.get("checks", [])
    if not isinstance(checks, list):
        return projected
    for check in checks:
        if not isinstance(check, dict) or not bool(check.get("blocks", False)):
            continue
        code = str(check.get("code", ""))
        final_reason = _CANDIDATE_REASON_BY_CHECK.get(code)
        if final_reason is None:
            raise ValueError(f"unowned candidate gate check: {code}")
        projected.append(
            _decision_check(
                code=f"candidate_{code}",
                state=EvidenceState.CONTRADICTED,
                final_reason=final_reason,
                detail={"candidate_check": code},
            )
        )
    return projected


def _required_candidate_gate(assessment: dict[str, Any]) -> dict[str, Any]:
    candidate_gate = assessment.get("candidate_gate")
    if not isinstance(candidate_gate, dict):
        raise ValueError("decision requires candidate gate")
    if not isinstance(candidate_gate.get("passed"), bool):
        raise ValueError("decision requires candidate gate passed state")
    for field in ("checks", "proof_paths", "failed_checks", "diagnostics"):
        if not isinstance(candidate_gate.get(field), list):
            raise ValueError(f"decision requires candidate gate {field}")
    return dict(candidate_gate)


def decision_gate_assessment(decision_input: DecisionGateInput) -> DecisionGateAssessment:
    checks = [
        *_project_candidate_checks(decision_input.candidate_gate),
        _decision_check(
            "automatic_processing_eligibility",
            decision_input.automatic_processing,
            FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
        ),
        _decision_check(
            "selected_content_preservation",
            decision_input.content_preservation.state,
            FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
            detail=decision_input.content_preservation.report_detail(),
        ),
        _decision_check(
            "selection_geometry_consensus",
            decision_input.selection_consensus,
            FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
        ),
        _decision_check(
            "output_content_protection",
            decision_input.output_protection,
            FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
        ),
        _decision_check(
            "transform_geometry_integrity",
            decision_input.transform_geometry,
            FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
        ),
    ]
    blocking = [check for check in checks if check.blocks]
    reasons = tuple(
        dict.fromkeys(
            str(check.detail["final_review_reason"])
            for check in blocking
        )
    )
    reason_inputs = tuple(
        {
            "check": check.code,
            "final_review_reason": str(check.detail["final_review_reason"]),
        }
        for check in blocking
    )
    return DecisionGateAssessment(
        passed=not blocking,
        checks=tuple(checks),
        final_review_reasons=reasons,
        reason_inputs=reason_inputs,
    )


def _automatic_processing_state(detection: DetectionCandidate) -> EvidenceState:
    if detection.detail.get("automatic_processing_supported") is False:
        return EvidenceState.CONTRADICTED
    source = str(detection.detail.get("candidate_source", ""))
    if source in {CANDIDATE_SOURCE_HARD_SAFETY, CANDIDATE_SOURCE_REVIEW_ONLY}:
        return EvidenceState.CONTRADICTED
    if detection.detail.get("candidate_contract") == "hard_safety_review_input":
        return EvidenceState.CONTRADICTED
    return EvidenceState.SUPPORTED


def _selection_consensus_state(detection: DetectionCandidate) -> EvidenceState:
    detail = detection.detail.get("selection_geometry_consensus")
    if not isinstance(detail, dict):
        return EvidenceState.NOT_APPLICABLE
    return (
        EvidenceState.CONTRADICTED
        if bool(detail.get("geometry_disagreement", False))
        else EvidenceState.SUPPORTED
    )


def _transform_geometry_state(deskew_detail: dict[str, Any]) -> EvidenceState:
    uncertain = bool(
        deskew_detail.get("geometry_uncertain", False)
        or deskew_detail.get("skipped") == "angle_out_of_range"
    )
    return EvidenceState.CONTRADICTED if uncertain else EvidenceState.SUPPORTED


def apply_decision_gate(
    detection: DetectionCandidate,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    *,
    deskew_detail: dict[str, Any],
    output_protection_plan: OutputProtectionPlan,
) -> FinalDetection:
    working = deepcopy(detection)
    assessment = working.detail.get("candidate_assessment")
    if not isinstance(assessment, dict):
        raise ValueError("decision requires candidate assessment")
    candidate_gate = _required_candidate_gate(assessment)
    partial_edge = assessment.get("partial_edge_safety", {})
    partial_edge = dict(partial_edge) if isinstance(partial_edge, dict) else {}
    preservation = content_preservation_evidence(
        content_detail,
        outer_alignment,
        partial_edge,
    )
    decision_gate = decision_gate_assessment(
        DecisionGateInput(
            candidate_gate=candidate_gate,
            automatic_processing=_automatic_processing_state(working),
            content_preservation=preservation,
            selection_consensus=_selection_consensus_state(working),
            output_protection=(
                EvidenceState.SUPPORTED
                if output_protection_plan.feasible
                else EvidenceState.CONTRADICTED
            ),
            transform_geometry=_transform_geometry_state(deskew_detail),
        )
    )
    evidence = evidence_summary_for(working, content_detail, outer_alignment)
    evidence["content_preservation"] = preservation.report_detail()
    working.detail["decision_summary"] = {
        "decision_gate": decision_gate.report_detail(),
    }
    working.detail["evidence_summary"] = evidence
    return FinalDetection.from_candidate(
        working,
        status="approved_auto" if decision_gate.passed else "needs_review",
        final_review_reasons=list(decision_gate.final_review_reasons),
    )
