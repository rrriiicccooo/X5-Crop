from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
from ....policies.runtime.policy import DetectionPolicy
from ..signals import candidate_signals


def candidate_reliability_detail(
    detection: DetectionCandidate,
    threshold: float,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    budget = policy.candidate_plan.execution_budget
    assessment = detection.detail.get("candidate_assessment", {})
    if not isinstance(assessment, dict):
        assessment = {}
    separator_detail = assessment.get("separator_support", {})
    if not isinstance(separator_detail, dict):
        separator_detail = {}
    source = str(assessment.get("source", ""))
    content_support = str(assessment.get("content_support", ""))
    required_confidence = min(1.0, float(threshold) + float(budget.reliable_confidence_margin))
    gate = assessment.get("candidate_gate")
    gate = dict(gate) if isinstance(gate, dict) else {}
    candidate_gate_allows_auto = bool(gate.get("passed", False))
    raw_hard_separator_ok = bool(separator_detail.get("ok", False))
    source_ok = (not budget.requires_separator_source) or source == "separator"
    candidate_gate_requirement_satisfied = (
        not budget.requires_candidate_gate
    ) or candidate_gate_allows_auto
    hard_separator_requirement_ok = (not budget.requires_hard_separator_ok) or raw_hard_separator_ok
    content_ok = (
        not budget.requires_content_support
        or content_support == budget.requires_content_support
    )
    confidence_ok = float(detection.confidence) >= required_confidence
    signals = candidate_signals(detection)
    candidate_signals_ok = (
        not budget.requires_no_candidate_signals
    ) or not signals
    reliable = all(
        (
            source_ok,
            candidate_gate_requirement_satisfied,
            hard_separator_requirement_ok,
            content_ok,
            confidence_ok,
            candidate_signals_ok,
        )
    )
    return {
        "reliable": bool(reliable),
        "confidence": float(detection.confidence),
        "required_confidence": float(required_confidence),
        "source": source,
        "source_ok": bool(source_ok),
        "candidate_gate": {
            "required": bool(budget.requires_candidate_gate),
            "passed": bool(candidate_gate_allows_auto),
        },
        "candidate_gate_requirement_satisfied": bool(candidate_gate_requirement_satisfied),
        "hard_separator_ok": bool(raw_hard_separator_ok),
        "hard_separator_requirement_ok": bool(hard_separator_requirement_ok),
        "content_support": content_support,
        "content_ok": bool(content_ok),
        "candidate_signals": signals,
        "candidate_signals_ok": bool(candidate_signals_ok),
    }


def candidate_is_reliable_for_execution_budget(
    detection: DetectionCandidate,
    threshold: float,
    policy: DetectionPolicy,
) -> bool:
    if not policy.candidate_plan.execution_budget.stop_after_reliable_primary:
        return False
    return bool(candidate_reliability_detail(detection, threshold, policy).get("reliable", False))
