from __future__ import annotations

from ...constants import (
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_EVIDENCE_DEPENDENCY_CYCLE_RISK,
    REASON_LUCKY_PASS_RISK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ...domain import Detection


FINAL_REVIEW_REASON_REDUCTION_MAP = {
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK: "separator_evidence_incomplete",
    REASON_CONTENT_EVIDENCE_WEAK: "content_evidence_insufficient",
    REASON_CONTENT_ASPECT_CONFLICT: "outer_content_mismatch",
    REASON_OUTER_CONTENT_BBOX_MISMATCH: "outer_content_mismatch",
    REASON_LUCKY_PASS_RISK: "lucky_pass_risk",
    REASON_EVIDENCE_DEPENDENCY_CYCLE_RISK: "evidence_dependency_cycle_risk",
    "weak_separators": "separator_evidence_incomplete",
    "mostly_equal_split": "separator_evidence_incomplete",
    "separator_below_threshold": "separator_evidence_incomplete",
    "content_only_not_enough_for_auto": "content_only_evidence",
    "content_confidence_low": "content_evidence_insufficient",
    "content_aspect_uncertain": "outer_content_mismatch",
    "content_coverage_weak": "content_evidence_insufficient",
    "outer_box_too_large": "outer_content_mismatch",
    "outer_box_uncertain": "outer_content_mismatch",
    "photo_width_unstable": "geometry_unstable",
    "unstable_frame_width": "geometry_unstable",
    "partial_too_ambiguous": "partial_edge_uncertain",
    "partial_outer_leading_content": "partial_edge_uncertain",
    "partial_frame_content_unstable": "partial_edge_uncertain",
    "holder_edge_disambiguation_weak": "partial_edge_uncertain",
    "needs_manual_review": "evidence_combination_insufficient",
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
