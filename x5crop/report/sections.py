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


def candidate_gate_detail(detection: Detection) -> dict[str, Any]:
    assessment = candidate_assessment(detection)
    candidate_gate = assessment.get("candidate_gate")
    return dict(candidate_gate) if isinstance(candidate_gate, dict) else {}


def decision_gate_detail(detection: Detection) -> dict[str, Any]:
    decision_gate = decision_summary(detection).get("decision_gate")
    return dict(decision_gate) if isinstance(decision_gate, dict) else {}


def report_policy_for_detection(detection: Detection) -> ReportPolicy:
    try:
        return get_detection_policy(detection.film_format, detection.strip_mode).report
    except ValueError:
        return ReportPolicy()


__all__ = [
    "candidate_table",
    "candidate_gate_detail",
    "decision_gate_detail",
    "report_policy_for_detection",
    "selected_candidate",
]
