from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverlapBleedRiskParameters:
    mean_min: float
    weak_continuity: float
    weak_activity: float
    medium_continuity: float
    medium_activity: float
    strong_continuity: float
    strong_activity: float


@dataclass(frozen=True)
class LuckyPassRiskParameters:
    enabled: bool
    model_gap_support_min: int
    model_gap_support_weight: float
    minor_model_gap_support_weight: float
    limited_strong_hard_max: int
    limited_strong_hard_weight: float
    very_limited_strong_hard_max: int
    very_limited_strong_hard_weight: float
    suspicious_hard_weight: float
    strong_overlap_weight: float
    combo_weight: float
    unstable_photo_width_cv: float
    unstable_photo_width_weight: float
    mild_photo_width_cv: float
    mild_photo_width_weight: float
    strong_hard_credit_min: int
    strong_hard_credit: float
    stable_photo_width_cv: float
    stable_model_gap_min: int
    stable_photo_width_geometry_credit: float
    risk_threshold: float


__all__ = [
    "LuckyPassRiskParameters",
    "OverlapBleedRiskParameters",
]
