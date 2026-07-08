from __future__ import annotations

from typing import Any

from ..detection.detail import (
    candidate_assessment,
    candidate_competition,
    decision_summary,
    final_review_reasons_from_detail,
)
from ..domain import Detection


def candidate_table(detection: Detection) -> list[dict[str, Any]]:
    candidates = candidate_competition(detection).get("top_candidates", [])
    return list(candidates) if isinstance(candidates, list) else []


def selected_candidate(detection: Detection) -> dict[str, Any]:
    competition = candidate_competition(detection)
    selected = competition.get("selected_candidate")
    if isinstance(selected, dict):
        detail = dict(selected)
        decision = decision_summary(detection)
        detail["final_confidence"] = float(detection.confidence)
        detail["final_review_reasons"] = final_review_reasons_from_detail(detection)
        detail["decision_status"] = str(decision.get("status", "unknown"))
        return detail
    return {
        "missing": True,
        "reason": "candidate_competition_missing",
    }


def candidate_gate_detail(detection: Detection) -> dict[str, Any]:
    assessment = candidate_assessment(detection)
    candidate_gate = assessment.get("candidate_gate")
    return dict(candidate_gate) if isinstance(candidate_gate, dict) else {}


def decision_gate_detail(detection: Detection) -> dict[str, Any]:
    decision_gate = decision_summary(detection).get("decision_gate")
    return dict(decision_gate) if isinstance(decision_gate, dict) else {}


__all__ = [
    "candidate_table",
    "candidate_gate_detail",
    "decision_gate_detail",
    "selected_candidate",
]
