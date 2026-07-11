from __future__ import annotations

from typing import Any

from ..detection.detail import (
    candidate_assessment,
    decision_summary,
    selection_geometry_consensus,
)
from ..domain import FinalDetection


def candidate_table(detection: FinalDetection) -> list[dict[str, Any]]:
    candidates = selection_geometry_consensus(detection).get("top_candidates", [])
    if not isinstance(candidates, list):
        return []
    return [
        {
            key: value
            for key, value in dict(candidate).items()
            if key != "candidate_assessment"
        }
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


def candidate_gate_detail(detection: FinalDetection) -> dict[str, Any]:
    candidate_gate = candidate_assessment(detection).get("candidate_gate")
    return dict(candidate_gate) if isinstance(candidate_gate, dict) else {}


def decision_gate_detail(detection: FinalDetection) -> dict[str, Any]:
    decision_gate = decision_summary(detection).get("decision_gate")
    return dict(decision_gate) if isinstance(decision_gate, dict) else {}
