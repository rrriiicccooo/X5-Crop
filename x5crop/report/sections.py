from __future__ import annotations

from typing import Any

from ..detection.detail import (
    candidate_assessment,
    candidate_competition,
    decision_summary,
    final_review_reasons_from_detail,
)
from ..domain import Detection
from ..policies.registry import get_detection_policy
from ..policies.runtime.report import ReportPolicy


def candidate_table(detection: Detection) -> list[dict[str, Any]]:
    candidates = candidate_competition(detection).get("top_candidates", [])
    return list(candidates) if isinstance(candidates, list) else []


def selected_candidate(detection: Detection) -> dict[str, Any]:
    competition = candidate_competition(detection)
    selected = competition.get("selected_candidate")
    if isinstance(selected, dict):
        return dict(selected)
    return {
        "format": detection.film_format,
        "count": int(detection.count),
        "strip_mode": detection.strip_mode,
        "final_confidence": float(detection.confidence),
        "final_review_reasons": final_review_reasons_from_detail(detection),
        "candidate_assessment": candidate_assessment(detection),
        "candidate_plan": detection.detail.get("candidate_plan", {}),
        "gap_search_profile": detection.detail.get("gap_search_profile", {}),
    }


def gate_records(detection: Detection) -> list[dict[str, Any]]:
    assessment = candidate_assessment(detection)
    gates: list[dict[str, Any]] = []
    hard = assessment.get("separator_hard_evidence", {})
    if isinstance(hard, dict):
        gates.append(
            {
                "name": "separator_gate",
                "ok": bool(hard.get("ok", False)),
                "reason": str(hard.get("reason", "")),
                "detail": hard,
            }
        )
    partial = assessment.get("partial_safe_extra_frames", {})
    if isinstance(partial, dict) and bool(partial.get("used", False)):
        gates.append(
            {
                "name": "partial_safe_extra_frames_gate",
                "ok": bool(partial.get("ok", False)),
                "reason": str(partial.get("reason", "")),
                "detail": partial,
            }
        )
    candidate_gate = assessment.get("gate")
    if isinstance(candidate_gate, dict):
        gates.append(
            {
                "name": "candidate_gate",
                "ok": bool(candidate_gate.get("passed", False)),
                "reason": (
                    "candidate_gate_passed"
                    if candidate_gate.get("passed", False)
                    else "candidate_gate_failed"
                ),
                "detail": candidate_gate,
            }
        )
    decision_gate = decision_summary(detection).get("decision_gate")
    if isinstance(decision_gate, dict):
        gates.append(
            {
                "name": "decision_gate",
                "ok": bool(decision_gate.get("passed", False)),
                "reason": (
                    "decision_gate_passed"
                    if decision_gate.get("passed", False)
                    else "decision_gate_failed"
                ),
                "detail": decision_gate,
            }
        )
    return gates


def report_policy_for_detection(detection: Detection) -> ReportPolicy:
    try:
        return get_detection_policy(detection.film_format, detection.strip_mode).report
    except ValueError:
        return ReportPolicy()


__all__ = [
    "candidate_table",
    "gate_records",
    "report_policy_for_detection",
    "selected_candidate",
]
