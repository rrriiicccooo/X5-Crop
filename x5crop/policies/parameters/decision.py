from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionReviewParameters:
    content_aspect_conflict_cap: float = 0.82
    content_low_confidence_cap: float = 0.84
    outer_mismatch_cap: float = 0.84
    outer_candidate_disagreement_min_spread_ratio: float = 0.20
