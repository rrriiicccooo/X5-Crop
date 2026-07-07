from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DebugGapOverlayParameters:
    overlap_tolerance_ratio: float
    overlap_tolerance_min: float
    overlap_tolerance_max: float
    tick_length_ratio: float
    tick_length_min: int
    hard_line_width: int
    model_line_width: int
    diagnostic_line_width: int


@dataclass(frozen=True)
class NearbySeparatorDiagnosticsParameters:
    window_ratio: float
    window_min: int
    window_max: int
    exclude_ratio: float
    exclude_min: int
    exclude_max: int
    max_width_ratio: float
    max_width_min: int
    max_width_max: int
    detail_score_add: float
    detail_score_multiplier: float


@dataclass(frozen=True)
class DiagnosticOverlapRiskParameters:
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
    "DebugGapOverlayParameters",
    "NearbySeparatorDiagnosticsParameters",
    "DiagnosticOverlapRiskParameters",
    "LuckyPassRiskParameters",
]
