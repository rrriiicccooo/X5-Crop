from __future__ import annotations

from typing import Any

from ....domain import Detection
from ....policies.runtime.policy import DetectionPolicy
from ..reasons import candidate_reasons


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
    gate = assessment.get("gate")
    gate = dict(gate) if isinstance(gate, dict) else {}
    candidate_gate_passed = bool(
        gate.get("passed", assessment.get("candidate_gate_passed", False))
    )
    raw_hard_separator_ok = bool(separator_detail.get("ok", False))
    source_ok = (not budget.requires_separator_source) or source == "separator"
    candidate_gate_ok = (not budget.requires_candidate_gate) or candidate_gate_passed
    hard_separator_requirement_ok = (not budget.requires_hard_separator_ok) or raw_hard_separator_ok
    content_ok = (
        not budget.requires_content_support
        or content_support == budget.requires_content_support
    )
    confidence_ok = float(detection.confidence) >= required_confidence
    reasons = candidate_reasons(detection)
    candidate_reasons_ok = (
        not budget.requires_no_candidate_reasons
    ) or not reasons
    reliable = all(
        (
            source_ok,
            candidate_gate_ok,
            hard_separator_requirement_ok,
            content_ok,
            confidence_ok,
            candidate_reasons_ok,
        )
    )
    return {
        "reliable": bool(reliable),
        "confidence": float(detection.confidence),
        "required_confidence": float(required_confidence),
        "source": source,
        "source_ok": bool(source_ok),
        "candidate_gate_passed": bool(candidate_gate_passed),
        "candidate_gate_ok": bool(candidate_gate_ok),
        "hard_separator_ok": bool(raw_hard_separator_ok),
        "hard_separator_requirement_ok": bool(hard_separator_requirement_ok),
        "content_support": content_support,
        "content_ok": bool(content_ok),
        "candidate_reasons": reasons,
        "candidate_reasons_ok": bool(candidate_reasons_ok),
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
