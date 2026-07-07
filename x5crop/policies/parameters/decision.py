from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionReviewParameters:
    content_aspect_conflict_cap: float
    content_low_confidence_cap: float
    outer_mismatch_cap: float
    lucky_pass_risk_cap: float


__all__ = [
    "DecisionReviewParameters",
]
