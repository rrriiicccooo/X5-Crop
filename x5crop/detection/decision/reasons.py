from __future__ import annotations

from ...constants import (
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_EVIDENCE_DEPENDENCY_CYCLE_RISK,
    REASON_LUCKY_PASS_RISK,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ...domain import Detection


FINAL_REVIEW_REASON_REDUCTION_MAP = {
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK: "separator_evidence_incomplete",
    REASON_CONTENT_EVIDENCE_WEAK: "content_evidence_insufficient",
    REASON_CONTENT_ASPECT_CONFLICT: "outer_content_mismatch",
    REASON_LUCKY_PASS_RISK: "lucky_pass_risk",
    REASON_EVIDENCE_DEPENDENCY_CYCLE_RISK: "evidence_dependency_cycle_risk",
}


def normalized_final_review_reasons(reasons: list[str]) -> list[str]:
    normalized = [
        FINAL_REVIEW_REASON_REDUCTION_MAP.get(str(reason), str(reason))
        for reason in reasons
    ]
    return sorted(set(reason for reason in normalized if reason))


def final_review_reasons(detection: Detection) -> list[str]:
    return list(detection.review_reasons)


def set_final_review_reasons(detection: Detection, reasons: list[str]) -> None:
    detection.review_reasons = normalized_final_review_reasons(reasons)


__all__ = [
    "FINAL_REVIEW_REASON_REDUCTION_MAP",
    "final_review_reasons",
    "normalized_final_review_reasons",
    "set_final_review_reasons",
]
