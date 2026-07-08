from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeDecisionPolicy:
    align_outer_to_content: bool = True
    outer_alignment_disabled_reason: str = "disabled_by_policy"
    outer_candidate_disagreement_review_reason: str = "outer_candidate_disagreement"
    deskew_uncertain_review_reason: str = "deskew_uncertain"
    content_aspect_conflict_cap: float = 0.82
    content_low_confidence_cap: float = 0.84
    outer_mismatch_cap: float = 0.84


__all__ = [
    "RuntimeDecisionPolicy",
]
