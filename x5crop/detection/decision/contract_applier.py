from __future__ import annotations

from typing import Any

import numpy as np

from ...runtime.config import RuntimeConfig
from ...domain import Detection
from ...formats import FormatSpec
from ..detail import candidate_reasons_from_detail
from ..confidence_caps import apply_confidence_cap
from ...policies.decision.contract import decision_contract_for
from .evidence_summary import evidence_summary_for
from .reasons import (
    final_review_reasons,
    normalized_final_review_reasons,
    set_final_review_reasons,
)
from .risk_summary import risk_summary_for


def _detail_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _candidate_reason_inputs_before_decision(detection: Detection) -> dict[str, Any]:
    assessment = detection.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    blockers = [str(reason) for reason in _detail_list(assessment.get("blockers"))]
    diagnostics = [str(reason) for reason in _detail_list(assessment.get("diagnostics"))]
    normalized_candidate_reasons = normalized_final_review_reasons(
        candidate_reasons_from_detail(detection)
    )
    return {
        "blockers": blockers,
        "diagnostics": diagnostics,
        "normalized_candidate_reasons": normalized_candidate_reasons,
        "auto_gate": bool(assessment.get("auto_gate", False)),
        "auto_gate_inputs": assessment.get("auto_gate_inputs", {}),
        "selection_risk_inputs": _detail_list(
            detection.detail.get("selection_risk_inputs")
        ),
    }


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


def apply_decision_contract(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
) -> Detection:
    policy = decision_contract_for(fmt.name, detection.strip_mode)
    evidence = evidence_summary_for(gray, detection, content_detail, outer_alignment, policy)
    risk = risk_summary_for(detection, evidence, policy)
    assessment = detection.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    candidate_auto_gate = assessment.get("auto_gate")
    candidate_auto_gate_failed = candidate_auto_gate is False
    reasons: list[str] = []
    reason_inputs: list[dict[str, Any]] = []

    def add_reason(reason: str, *, bucket: str, signal: str) -> None:
        reasons.append(reason)
        reason_inputs.append(
            {
                "bucket": bucket,
                "signal": signal,
                "final_review_reason": reason,
            }
        )

    if risk["content_only_evidence"]:
        add_reason(
            policy.decision.content_only_evidence_reason,
            bucket="risk",
            signal="content_only_evidence",
        )
    if risk["safety_or_review_only"]:
        add_reason(
            policy.decision.decision_insufficient_reason,
            bucket="risk",
            signal="safety_or_review_only",
        )
    if not bool(evidence["outer"]["ok"]) and policy.risk.review_on_outer_content_mismatch:
        add_reason(
            policy.decision.outer_content_mismatch_reason,
            bucket="outer",
            signal="outer_not_ok",
        )
    if not bool(evidence["separator"]["ok"]):
        add_reason(
            policy.decision.separator_incomplete_reason,
            bucket="separator",
            signal="separator_not_ok",
        )
    if not bool(evidence["geometry"]["ok"]):
        add_reason(
            policy.decision.geometry_unstable_reason,
            bucket="geometry",
            signal="geometry_not_ok",
        )
    if not bool(evidence["content"]["ok"]):
        add_reason(
            policy.decision.content_evidence_insufficient_reason,
            bucket="content",
            signal="content_not_ok",
        )
    if risk["candidate_competition_close"] and policy.risk.review_on_close_competition:
        add_reason(
            policy.decision.candidate_competition_close_reason,
            bucket="risk",
            signal="candidate_competition_close",
        )
    if risk["overlap_risk"] and policy.risk.review_on_overlap_risk:
        add_reason(
            policy.decision.overlap_risk_reason,
            bucket="risk",
            signal="overlap_bleed_risk",
        )
    if risk["lucky_pass_risk"] and policy.risk.review_on_lucky_pass_risk:
        add_reason(
            policy.decision.lucky_pass_risk_reason,
            bucket="risk",
            signal="lucky_pass_risk",
        )
    if risk["partial_edge_uncertain"]:
        add_reason(
            policy.decision.partial_edge_uncertain_reason,
            bucket="partial_edge",
            signal="partial_edge_uncertain",
        )
    if candidate_auto_gate_failed:
        add_reason(
            policy.decision.decision_insufficient_reason,
            bucket="candidate_assessment",
            signal="candidate_auto_gate_failed",
        )
    if detection.confidence < config.confidence_threshold and not reasons:
        add_reason(
            policy.decision.decision_insufficient_reason,
            bucket="confidence",
            signal="below_threshold",
        )

    reasons = normalized_final_review_reasons(reasons)
    final_reasons = list(reasons)
    passed = detection.confidence >= config.confidence_threshold and not final_reasons
    decision_caps = detection.detail.setdefault("decision_confidence_caps", [])
    if not isinstance(decision_caps, list):
        decision_caps = []
        detection.detail["decision_confidence_caps"] = decision_caps
    if not passed:
        detection.confidence, cap_detail = apply_confidence_cap(
            float(detection.confidence),
            policy.decision.review_confidence_cap,
            owner="decision",
            reason="final_review",
        )
        decision_caps.append(cap_detail)
    candidate_reason_inputs = _candidate_reason_inputs_before_decision(detection)
    detection.detail["candidate_reason_inputs_before_decision"] = candidate_reason_inputs
    detection.detail["candidate_blockers_before_decision"] = candidate_reason_inputs["blockers"]
    detection.detail["candidate_diagnostics_before_decision"] = candidate_reason_inputs["diagnostics"]
    set_final_review_reasons(detection, final_reasons)
    final_reasons = final_review_reasons(detection)
    sync_candidate_competition_decision_fields(
        detection,
        "approved_auto" if passed else "needs_review",
    )
    detail = {
        "policy_id": policy.policy_id,
        "schema_version": policy.schema_version,
        "pass": bool(passed),
        "status": "approved_auto" if passed else "needs_review",
        "final_review_reasons_added": reasons,
        "final_review_reasons": final_reasons,
        "decision_reason_inputs": reason_inputs,
        "decision_confidence_caps": decision_caps,
        "candidate_reason_inputs_before_decision": candidate_reason_inputs,
        "evidence_summary": evidence,
        "risk_summary": risk,
        "decision_policy_detail": policy.report_detail(),
    }
    detection.detail["decision_summary"] = detail
    detection.detail["evidence_summary"] = evidence
    detection.detail["risk_summary"] = risk
    detection.detail["decision_reason_inputs"] = reason_inputs
    detection.detail["final_review_reasons"] = final_reasons
    detection.detail["decision_policy_detail"] = policy.report_detail()
    detection.detail["policy_id"] = policy.policy_id
    return detection
