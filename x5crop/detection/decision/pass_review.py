from __future__ import annotations

from typing import Any

import numpy as np

from ...runtime.config import RuntimeConfig
from ...domain import Detection
from ...formats import FormatSpec
from ...policies.decision.contract import decision_contract_for
from .evidence_summary import evidence_summary_for
from .reasons import normalized_review_reasons
from .risk_summary import risk_summary_for


def apply_final_decision_policy(
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
    reasons: list[str] = []
    if risk["content_only_evidence"] or risk["safety_or_review_only"]:
        reasons.append(policy.decision.content_only_evidence_reason)
    if not bool(evidence["outer"]["ok"]) and policy.risk.review_on_outer_content_mismatch:
        reasons.append(policy.decision.outer_content_mismatch_reason)
    if not bool(evidence["separator"]["ok"]):
        reasons.append(policy.decision.separator_incomplete_reason)
    if not bool(evidence["geometry"]["ok"]):
        reasons.append(policy.decision.geometry_unstable_reason)
    if not bool(evidence["content"]["ok"]):
        reasons.append(policy.decision.content_only_evidence_reason)
    if risk["candidate_competition_close"] and policy.risk.review_on_close_competition:
        reasons.append(policy.decision.candidate_competition_close_reason)
    if risk["overlap_risk"] and (
        policy.risk.review_on_overlap_risk or policy.risk.review_on_lucky_pass_risk
    ):
        reasons.append(policy.decision.overlap_risk_reason)
    if risk["partial_edge_uncertain"]:
        reasons.append(policy.decision.partial_edge_uncertain_reason)
    if detection.confidence < config.confidence_threshold and not reasons:
        reasons.append(policy.decision.decision_insufficient_reason)

    reasons = normalized_review_reasons(reasons)
    existing_reasons = normalized_review_reasons(list(detection.review_reasons))
    if bool(evidence["outer"]["ok"]):
        existing_reasons = [
            reason for reason in existing_reasons if reason != policy.decision.outer_content_mismatch_reason
        ]
    if bool(evidence["content"]["ok"]):
        existing_reasons = [
            reason for reason in existing_reasons if reason != policy.decision.content_only_evidence_reason
        ]
    final_reasons = sorted(set(existing_reasons + reasons))
    passed = detection.confidence >= config.confidence_threshold and not final_reasons
    if not passed:
        detection.confidence = min(float(detection.confidence), policy.decision.review_confidence_cap)
    detection.review_reasons = final_reasons
    competition = detection.detail.get("candidate_competition")
    if isinstance(competition, dict):
        selected = competition.get("selected_candidate")
        if isinstance(selected, dict):
            selected["confidence"] = float(detection.confidence)
            selected["review_reasons"] = list(detection.review_reasons)
            selected["decision_status"] = "approved_auto" if passed else "needs_review"
        top = competition.get("top_candidates")
        if isinstance(top, list):
            for candidate in top:
                if isinstance(candidate, dict) and bool(candidate.get("selected", False)):
                    candidate["confidence"] = float(detection.confidence)
                    candidate["review_reasons"] = list(detection.review_reasons)
                    candidate["decision_status"] = "approved_auto" if passed else "needs_review"
    detail = {
        "policy_id": policy.policy_id,
        "schema_version": policy.schema_version,
        "pass": bool(passed),
        "status": "approved_auto" if passed else "needs_review",
        "review_reasons_added": reasons,
        "evidence_summary": evidence,
        "risk_summary": risk,
        "decision_policy_detail": policy.report_detail(),
    }
    detection.detail["decision_summary"] = detail
    detection.detail["evidence_summary"] = evidence
    detection.detail["risk_summary"] = risk
    detection.detail["decision_policy_detail"] = policy.report_detail()
    detection.detail["policy_id"] = policy.policy_id
    return detection
