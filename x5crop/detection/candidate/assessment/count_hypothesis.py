from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....domain import DetectionCandidate
from ..plan.count_hypotheses import CountHypothesis


def _candidate_passes_gate(candidate: DetectionCandidate) -> bool:
    assessment = candidate.detail.get("candidate_assessment")
    if not isinstance(assessment, dict):
        return False
    gate = assessment.get("candidate_gate")
    return bool(isinstance(gate, dict) and gate.get("passed", False))


@dataclass(frozen=True)
class CountHypothesisEvaluation:
    hypothesis: CountHypothesis
    candidates: tuple[DetectionCandidate, ...]
    search_satisfied: bool
    supporting_offsets: tuple[float, ...]

    def report_detail(self) -> dict[str, Any]:
        confidences = [float(candidate.confidence) for candidate in self.candidates]
        return {
            **self.hypothesis.report_detail(),
            "candidate_count": len(self.candidates),
            "candidate_gate_pass_count": sum(
                1 for candidate in self.candidates if _candidate_passes_gate(candidate)
            ),
            "max_confidence": max(confidences) if confidences else None,
            "search_satisfied": bool(self.search_satisfied),
            "supporting_offsets": [float(offset) for offset in self.supporting_offsets],
        }


__all__ = ["CountHypothesisEvaluation"]
