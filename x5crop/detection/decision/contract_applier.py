from __future__ import annotations

from typing import Any

import numpy as np

from ...constants import CANDIDATE_SOURCE_REVIEW_ONLY
from ...runtime.config import RuntimeConfig
from ...domain import Detection
from ..confidence_caps import apply_confidence_cap
from ...policies.decision.contract import DetectionDecisionContract
from .decision_gate import DecisionAssessmentInput, decision_gate_assessment
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


def _decision_status_for(
    detection: Detection,
    confidence_threshold: float,
    final_reasons: list[str],
) -> str:
    if detection.confidence >= confidence_threshold and not final_reasons:
        return "approved_auto"
    return "needs_review"


def _apply_decision_confidence_caps(
    detection: Detection,
    config: RuntimeConfig,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    policy: DetectionDecisionContract,
) -> list[dict[str, Any]]:
    decision_caps = detection.detail.setdefault("decision_confidence_caps", [])
    if not isinstance(decision_caps, list):
        decision_caps = []
        detection.detail["decision_confidence_caps"] = decision_caps

    review_only_mode = detection.detail.get("candidate_source") == CANDIDATE_SOURCE_REVIEW_ONLY
    support = str(content_detail.get("support", ""))
    if not review_only_mode:
        if support == "aspect_conflict" and detection.confidence >= config.confidence_threshold:
            detection.confidence, cap_detail = apply_confidence_cap(
                float(detection.confidence),
                policy.decision.content_aspect_conflict_cap,
                owner="decision",
                reason="content_aspect_conflict",
            )
            decision_caps.append(cap_detail)
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence, cap_detail = apply_confidence_cap(
                float(detection.confidence),
                policy.decision.content_low_confidence_cap,
                owner="decision",
                reason="content_low_confidence",
            )
            decision_caps.append(cap_detail)

    outer_correction_detail = detection.detail.get("outer_correction", {})
    suppress_outer_mismatch = bool(
        isinstance(outer_correction_detail, dict)
        and outer_correction_detail.get("suppress_outer_mismatch", False)
    )
    if (
        not review_only_mode
        and not suppress_outer_mismatch
        and bool(outer_alignment.get("used", False))
        and not bool(outer_alignment.get("ok", True))
    ):
        detection.confidence, cap_detail = apply_confidence_cap(
            float(detection.confidence),
            policy.decision.outer_mismatch_cap,
            owner="decision",
            reason="outer_content_mismatch",
        )
        decision_caps.append(cap_detail)
    return decision_caps


def apply_decision_contract(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    *,
    policy: DetectionDecisionContract,
    deskew_detail: dict[str, Any] | None = None,
) -> Detection:
    evidence = evidence_summary_for(gray, detection, content_detail, outer_alignment, policy)
    decision_signals = decision_signals_for(detection, evidence, policy)
    assessment = detection.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    candidate_gate = assessment.get("candidate_gate")
    candidate_gate = dict(candidate_gate) if isinstance(candidate_gate, dict) else {}
    decision_caps = _apply_decision_confidence_caps(
        detection=detection,
        policy=policy,
        config=config,
        content_detail=content_detail,
        outer_alignment=outer_alignment,
    )
    decision_gate = decision_gate_assessment(
        DecisionAssessmentInput(
            detection=detection,
            confidence_threshold=config.confidence_threshold,
            decision_signals=decision_signals,
            policy=policy,
            candidate_gate=candidate_gate,
            deskew_detail=deskew_detail or {},
            confidence_caps=decision_caps,
        )
    )
    final_reasons = _unique_reasons(decision_gate.final_review_reasons)
    if detection.confidence < config.confidence_threshold or final_reasons:
        detection.confidence, cap_detail = apply_confidence_cap(
            float(detection.confidence),
            policy.decision.review_confidence_cap,
            owner="decision",
            reason="final_review",
        )
        decision_caps.append(cap_detail)
    decision_gate = decision_gate.with_confidence_caps(decision_caps)
    status = _decision_status_for(detection, config.confidence_threshold, final_reasons)
    candidate_gate_input = _candidate_gate_input(detection)
    detection.detail["candidate_gate_input"] = candidate_gate_input
    set_final_review_reasons(detection, final_reasons)
    final_reasons = final_review_reasons(detection)
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
