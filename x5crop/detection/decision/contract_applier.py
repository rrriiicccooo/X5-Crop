from __future__ import annotations

from typing import Any

import numpy as np

from ...runtime.config import RuntimeConfig
from ...domain import Detection
from ...formats import FormatSpec
from ..confidence_caps import apply_confidence_cap
from ...policies.decision.contract import decision_contract_for
from .decision_gate import decision_gate_assessment
from .decision_signals import decision_signals_for
from .evidence_summary import evidence_summary_for
from .reasons import (
    final_review_reasons,
    set_final_review_reasons,
)


def _detail_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _candidate_gate_input(detection: Detection) -> dict[str, Any]:
    assessment = detection.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    blockers = [str(reason) for reason in _detail_list(assessment.get("blockers"))]
    diagnostics = [str(reason) for reason in _detail_list(assessment.get("diagnostics"))]
    gate = assessment.get("candidate_gate")
    gate = dict(gate) if isinstance(gate, dict) else {}
    return {
        "blockers": blockers,
        "diagnostics": diagnostics,
        "candidate_gate_passed": bool(
            gate.get("passed", assessment.get("candidate_gate_passed", False))
        ),
        "candidate_gate": gate,
        "selection_uncertainty_inputs": _detail_list(
            detection.detail.get("selection_uncertainty_inputs")
        ),
    }


def _unique_reasons(reasons: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        reason = str(reason)
        if reason and reason not in seen:
            unique.append(reason)
            seen.add(reason)
    return unique


def sync_candidate_competition_decision_fields(detection: Detection, status: str) -> None:
    competition = detection.detail.get("candidate_competition")
    if not isinstance(competition, dict):
        return
    final_reasons = final_review_reasons(detection)
    selected = competition.get("selected_candidate")
    if isinstance(selected, dict):
        selected["final_confidence"] = float(detection.confidence)
        selected["final_review_reasons"] = list(final_reasons)
        selected["decision_status"] = status
    top = competition.get("top_candidates")
    if isinstance(top, list):
        for candidate in top:
            if isinstance(candidate, dict) and bool(candidate.get("selected", False)):
                candidate["final_confidence"] = float(detection.confidence)
                candidate["final_review_reasons"] = list(final_reasons)
                candidate["decision_status"] = status


def _decision_status_for(
    detection: Detection,
    confidence_threshold: float,
    final_reasons: list[str],
) -> str:
    if detection.confidence >= confidence_threshold and not final_reasons:
        return "approved_auto"
    return "needs_review"


def apply_decision_contract(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    deskew_detail: dict[str, Any] | None = None,
) -> Detection:
    policy = decision_contract_for(fmt.name, detection.strip_mode)
    evidence = evidence_summary_for(gray, detection, content_detail, outer_alignment, policy)
    decision_signals = decision_signals_for(detection, evidence, policy)
    assessment = detection.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    candidate_gate = assessment.get("candidate_gate")
    candidate_gate = dict(candidate_gate) if isinstance(candidate_gate, dict) else {}
    candidate_gate_passed = bool(
        candidate_gate.get("passed", assessment.get("candidate_gate_passed", False))
    )
    decision_gate = decision_gate_assessment(
        detection=detection,
        confidence_threshold=config.confidence_threshold,
        evidence=evidence,
        decision_signals=decision_signals,
        policy=policy,
        candidate_gate_passed=candidate_gate_passed,
        deskew_detail={},
        include_low_confidence_context=False,
    )
    reasons = _unique_reasons(decision_gate.final_review_reasons)
    final_reasons = list(reasons)
    base_passed = detection.confidence >= config.confidence_threshold and not final_reasons
    decision_caps = detection.detail.setdefault("decision_confidence_caps", [])
    if not isinstance(decision_caps, list):
        decision_caps = []
        detection.detail["decision_confidence_caps"] = decision_caps
    if not base_passed:
        detection.confidence, cap_detail = apply_confidence_cap(
            float(detection.confidence),
            policy.decision.review_confidence_cap,
            owner="decision",
            reason="final_review",
        )
        decision_caps.append(cap_detail)
    decision_gate = decision_gate_assessment(
        detection=detection,
        confidence_threshold=config.confidence_threshold,
        evidence=evidence,
        decision_signals=decision_signals,
        policy=policy,
        candidate_gate_passed=candidate_gate_passed,
        deskew_detail=deskew_detail or {},
        include_low_confidence_context=True,
        confidence_caps=decision_caps,
    )
    reasons = _unique_reasons(decision_gate.final_review_reasons)
    decision_gate = decision_gate.with_final_review_reasons(reasons)
    final_reasons = list(reasons)
    status = _decision_status_for(detection, config.confidence_threshold, final_reasons)
    candidate_gate_input = _candidate_gate_input(detection)
    detection.detail["candidate_gate_input"] = candidate_gate_input
    set_final_review_reasons(detection, final_reasons)
    final_reasons = final_review_reasons(detection)
    sync_candidate_competition_decision_fields(detection, status)
    detail = {
        "policy_id": policy.policy_id,
        "schema_version": policy.schema_version,
        "pass": status == "approved_auto",
        "status": status,
        "final_review_reasons": final_reasons,
        "decision_reason_inputs": decision_gate.reason_inputs,
        "decision_confidence_caps": decision_caps,
        "decision_gate": decision_gate.report_detail(),
        "candidate_gate_input": candidate_gate_input,
        "evidence_summary": evidence,
        "decision_signals": decision_signals,
        "decision_policy_detail": policy.report_detail(),
    }
    detection.detail["decision_summary"] = detail
    detection.detail["evidence_summary"] = evidence
    detection.detail["decision_signals"] = decision_signals
    detection.detail["decision_reason_inputs"] = decision_gate.reason_inputs
    detection.detail["final_review_reasons"] = final_reasons
    detection.detail["decision_policy_detail"] = policy.report_detail()
    detection.detail["policy_id"] = policy.policy_id
    return detection
