from __future__ import annotations

from typing import Any

from ..detection.detail import (
    candidate_assessment,
    candidate_competition,
    decision_summary,
)
from ..domain import FinalDetection


def candidate_table(detection: FinalDetection) -> list[dict[str, Any]]:
    candidates = candidate_competition(detection).get("top_candidates", [])
    return list(candidates) if isinstance(candidates, list) else []


def selected_candidate(detection: FinalDetection) -> dict[str, Any]:
    selected = candidate_competition(detection).get("selected_candidate")
    if isinstance(selected, dict):
        return dict(selected)
    return {
        "missing": True,
        "reason": "candidate_competition_missing",
    }


def candidate_gate_detail(detection: FinalDetection) -> dict[str, Any]:
    candidate_gate = candidate_assessment(detection).get("candidate_gate")
    return dict(candidate_gate) if isinstance(candidate_gate, dict) else {}


def decision_gate_detail(detection: FinalDetection) -> dict[str, Any]:
    decision_gate = decision_summary(detection).get("decision_gate")
    return dict(decision_gate) if isinstance(decision_gate, dict) else {}
