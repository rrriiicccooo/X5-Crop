from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorSupportParameters:
    needed_hard_max: int = 2
    max_equal_gaps_floor: int = 2
    allow_geometry_support: bool = True
    hard_required_all_gaps: bool = True
    edge_pair_min_score_without_broad_width: float = 0.0
    edge_pair_min_score_with_broad_width: float = 0.0
    reliable_gap_min_score: float = 0.28
    min_broad_separator_width_gaps_for_auto: int = 0
    score_min_hard_gaps: int = 2
    score_max_equal_gaps_floor: int = 2
    low_hard_confidence_cap: float = 0.82
    mostly_equal_confidence_cap: float = 0.84
    allow_full_detected_geometry: bool = True

@dataclass(frozen=True)
class LeadingGridFailureParameters:
    enabled: bool = True
    min_expected_gaps: int = 5
    leading_count: int = 3
    low_score: float = 0.35
    very_low_score: float = 0.12
    very_low_count: int = 2
    max_hard_gaps: int = 2

@dataclass(frozen=True)
class SeparatorGeometrySupportParameters:
    detected_geometry_min_hard_ratio: float = 0.60
    detected_geometry_min_joint_score: float = 0.78
    stable_grid_min_hard_ratio: float = 0.35
    stable_grid_min_joint_score: float = 0.65
    max_photo_width_cv: float = 0.040
    max_outer_area_ratio: float = 0.995

@dataclass(frozen=True)
class SeparatorWidthProfileParameters:
    full_enabled: bool = True
    partial_enabled: bool = True
    max_width_ratio: float = 0.060

@dataclass(frozen=True)
class NearbySeparatorRefinementParameters:
    enabled: bool = True
    window_ratio: float = 0.040
    window_min: int = 16
    window_max: int = 320
    exclude_ratio: float = 0.012
    exclude_min: int = 8
    exclude_max: int = 120
    max_width_ratio: float = 0.070
    max_width_min: int = 2
    max_width_max: int = 520
    distance_ratio: float = 0.040
    score_add: float = 0.10
    score_multiplier: float = 1.22
    local_gain_ratio: float = 0.006
    local_gain_min: float = 8.0
    local_gain_max: float = 40.0
    width_cv_slack: float = 0.0015

@dataclass(frozen=True)
class GapSearchParameters:
    radius_ratio: float = 0.16
    radius_min: int = 6
    radius_max: int = 900
    max_width_ratio: float = 0.045
    max_width_min: int = 2
    max_width_max: int = 420
    min_width_ratio: float = 0.001
    min_width_min: int = 1
    min_width_max: int = 12
    guard_ratio: float = 0.035
    guard_min: int = 3
    guard_max: int = 220
    min_score: float = 0.22
    peak_multiplier: float = 0.90
    band_multiplier: float = 0.62
    band_min_score_multiplier: float = 0.86
    weak_prominence_min: float = 0.08
    weak_prominence_mean_override: float = 0.95
    quality_prominence_weight: float = 0.80
    separator_width_min_mean: float = 0.95
    separator_width_min_prominence: float = 0.02

@dataclass(frozen=True)
class SeparatorProfileParameters:
    top_ratio: float = 0.10
    bottom_ratio: float = 0.90
    segments: int = 5
    dark_threshold: int = 30
    light_threshold: int = 225
    consistency_percentile: float = 20.0
    average_weight: float = 0.35
    consistency_weight: float = 0.65
    std_norm: float = 70.0
    dark_soft_mean: float = 54.0
    light_soft_mean: float = 225.0
    light_soft_span: float = 30.0
    soft_weight: float = 0.50
    uniform_base: float = 0.90
    uniform_weight: float = 0.10
    gradient_weight: float = 0.25
    smooth_ratio: float = 0.0015
    smooth_min: int = 3

@dataclass(frozen=True)
class EdgeRefineProfileParameters:
    top_ratio: float = 0.12
    bottom_ratio: float = 0.88
    mean_weight: float = 0.65
    p75_weight: float = 0.35
    smooth_ratio: float = 0.0008
    smooth_min: int = 3
    high_percentile: float = 99.2
    background_dark_threshold: int = 30
    background_light_threshold: int = 225
    y_edge_weight: float = 0.50
    activity_percentile: float = 95.0

@dataclass(frozen=True)
class HardGapTrustParameters:
    guard_ratio: float = 0.020
    guard_min: int = 4
    guard_max: int = 80
    narrow_ratio: float = 0.020
    narrow_min: float = 3.0
    narrow_max: float = 140.0
    model_delta_ratio: float = 0.040
    geometry_width_ratio: float = 0.018
    strong_min_score: float = 0.90
    strong_width_min: float = 0.018
    strong_width_max: float = 0.065
    narrow_ok_score: float = 0.70
    narrow_ok_width_min: float = 0.006
    narrow_ok_width_max: float = 0.018
    model_conflict_score: float = 1.05
    core_content_threshold: int = 235
    core_dark_threshold: int = 55
    dark_mean_max: float = 45.0
    dark_fraction_min: float = 0.45
    dark_activity_max: float = 0.18
    strong_core_content_max: float = 0.08
    weak_mean_min: float = 70.0
    weak_content_min: float = 0.10
    frame_border_width_ratio: float = 0.010
    continuity_min: float = 0.12
    activity_min: float = 0.030

__all__ = [
    'SeparatorSupportParameters',
    'LeadingGridFailureParameters',
    'SeparatorGeometrySupportParameters',
    'SeparatorWidthProfileParameters',
    'NearbySeparatorRefinementParameters',
    'GapSearchParameters',
    'SeparatorProfileParameters',
    'EdgeRefineProfileParameters',
    'HardGapTrustParameters',
]
