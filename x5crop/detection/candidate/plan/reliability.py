from __future__ import annotations

from typing import Any

from ....domain import Detection
from ....policies.runtime.policy import DetectionPolicy


def candidate_reliability_detail(
    detection: Detection,
    threshold: float,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    budget = policy.candidate_plan.execution_budget
    assessment = detection.detail.get("candidate_assessment", {})
    if not isinstance(assessment, dict):
        assessment = {}
    separator_detail = assessment.get("separator_hard_evidence", {})
    if not isinstance(separator_detail, dict):
        separator_detail = {}
    source = str(assessment.get("source", ""))
    content_support = str(assessment.get("content_support", ""))
    required_confidence = min(1.0, float(threshold) + float(budget.reliable_confidence_margin))
    auto_gate = bool(assessment.get("auto_gate", False))
    raw_hard_separator_ok = bool(separator_detail.get("ok", False))
    source_ok = (not budget.requires_separator_source) or source == "separator"
    auto_gate_ok = (not budget.requires_auto_gate) or auto_gate
    hard_separator_requirement_ok = (not budget.requires_hard_separator_ok) or raw_hard_separator_ok
    content_ok = (
        not budget.requires_content_support
        or content_support == budget.requires_content_support
    )
    confidence_ok = float(detection.confidence) >= required_confidence
    review_reasons_ok = (not budget.requires_no_review_reasons) or not detection.review_reasons
    reliable = all(
        (
            source_ok,
            auto_gate_ok,
            hard_separator_requirement_ok,
            content_ok,
            confidence_ok,
            review_reasons_ok,
        )
    )
    return {
        "reliable": bool(reliable),
        "confidence": float(detection.confidence),
        "required_confidence": float(required_confidence),
        "source": source,
        "source_ok": bool(source_ok),
        "auto_gate": bool(auto_gate),
        "auto_gate_ok": bool(auto_gate_ok),
        "hard_separator_ok": bool(raw_hard_separator_ok),
        "hard_separator_requirement_ok": bool(hard_separator_requirement_ok),
        "content_support": content_support,
        "content_ok": bool(content_ok),
        "review_reasons": list(detection.review_reasons),
        "review_reasons_ok": bool(review_reasons_ok),
    }


def candidate_is_reliable_for_execution_budget(
    detection: Detection,
    threshold: float,
    policy: DetectionPolicy,
) -> bool:
    if not policy.candidate_plan.execution_budget.stop_after_reliable_primary:
        return False
    return bool(candidate_reliability_detail(detection, threshold, policy).get("reliable", False))


__all__ = [
    "candidate_is_reliable_for_execution_budget",
    "candidate_reliability_detail",
]
