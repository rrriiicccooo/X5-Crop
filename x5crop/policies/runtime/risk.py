from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OverlapBleedRiskPolicy:
    enabled: bool = False
    mean_min: float = 55.0
    weak_continuity: float = 0.16
    weak_activity: float = 0.04
    medium_continuity: float = 0.35
    medium_activity: float = 0.08
    strong_continuity: float = 0.70
    strong_activity: float = 0.12


@dataclass(frozen=True)
class LuckyPassRiskPolicy:
    enabled: bool = True
    model_gap_support_min: int = 2
    model_gap_support_weight: float = 0.24
    minor_model_gap_support_weight: float = 0.08
    limited_strong_hard_max: int = 2
    limited_strong_hard_weight: float = 0.20
    very_limited_strong_hard_max: int = 1
    very_limited_strong_hard_weight: float = 0.10
    suspicious_hard_weight: float = 0.20
    strong_overlap_weight: float = 0.20
    combo_weight: float = 0.12
    unstable_photo_width_cv: float = 0.006
    unstable_photo_width_weight: float = 0.16
    mild_photo_width_cv: float = 0.003
    mild_photo_width_weight: float = 0.08
    strong_hard_credit_min: int = 3
    strong_hard_credit: float = -0.15
    stable_photo_width_cv: float = 0.002
    stable_model_gap_min: int = 3
    stable_photo_width_geometry_credit: float = -0.35
    risk_threshold: float = 0.80


@dataclass(frozen=True)
class RuntimeRiskPolicy:
    overlap_bleed: OverlapBleedRiskPolicy = field(default_factory=OverlapBleedRiskPolicy)
    lucky_pass: LuckyPassRiskPolicy = field(default_factory=LuckyPassRiskPolicy)


__all__ = [
    "LuckyPassRiskPolicy",
    "OverlapBleedRiskPolicy",
    "RuntimeRiskPolicy",
]
