from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorGateParameters:
    needed_hard_max: int
    max_equal_gaps_floor: int
    allow_geometry_support: bool
    hard_required_all_gaps: bool
    edge_pair_min_score_without_broad_width: float
    edge_pair_min_score_with_broad_width: float
    min_broad_separator_width_gaps_for_auto: int
    score_min_hard_gaps: int
    score_max_equal_gaps_floor: int
    low_hard_confidence_cap: float
    mostly_equal_confidence_cap: float
    allow_full_detected_geometry: bool

@dataclass(frozen=True)
class LeadingGridFailureParameters:
    enabled: bool
    min_expected_gaps: int
    leading_count: int
    low_score: float
    very_low_score: float
    very_low_count: int
    max_hard_gaps: int

@dataclass(frozen=True)
class SeparatorGeometrySupportParameters:
    detected_geometry_min_hard_ratio: float
    detected_geometry_min_joint_score: float
    stable_grid_min_hard_ratio: float
    stable_grid_min_joint_score: float
    max_width_cv: float
    max_outer_area_ratio: float

@dataclass(frozen=True)
class SeparatorWidthProfileParameters:
    full_enabled: bool
    partial_enabled: bool
    max_width_ratio: float
    confidence_cap: float

@dataclass(frozen=True)
class NearbySeparatorCorrectionParameters:
    enabled: bool
    window_ratio: float
    window_min: int
    window_max: int
    exclude_ratio: float
    exclude_min: int
    exclude_max: int
    max_width_ratio: float
    max_width_min: int
    max_width_max: int
    distance_ratio: float
    score_add: float
    score_multiplier: float
    local_gain_ratio: float
    local_gain_min: float
    local_gain_max: float
    width_cv_slack: float

@dataclass(frozen=True)
class RobustGridParameters:
    constrain_full_shift_ratio: float
    constrain_partial_shift_ratio: float
    constrain_shift_min: float
    constrain_shift_max: float
    reliable_min_score: float
    min_reliable: int
    pitch_min_ratio: float
    pitch_max_ratio: float
    full_tolerance_ratio: float
    partial_tolerance_ratio: float
    tolerance_min: float
    tolerance_max: float
    reject_residual_ratio: float
    full_shift_ratio: float
    partial_shift_ratio: float
    shift_min: float
    shift_max: float
    hard_keep_ratio: float
    hard_keep_min: float
    hard_keep_max: float
    hard_protect_ratio: float
    hard_protect_min: float
    hard_protect_max: float

@dataclass(frozen=True)
class GapSearchParameters:
    radius_ratio: float
    radius_min: int
    radius_max: int
    max_width_ratio: float
    max_width_min: int
    max_width_max: int
    min_width_ratio: float
    min_width_min: int
    min_width_max: int
    guard_ratio: float
    guard_min: int
    guard_max: int
    min_score: float
    peak_multiplier: float
    band_multiplier: float
    separator_width_min_mean: float
    separator_width_min_prominence: float

@dataclass(frozen=True)
class EnhancedSeparatorParameters:
    min_score: float
    max_width_ratio: float
    max_width_min: float
    max_width_max: float
    max_shift_ratio: float
    max_shift_min: float
    max_shift_max: float
    auto_low_score: float

@dataclass(frozen=True)
class SeparatorProfileParameters:
    top_ratio: float
    bottom_ratio: float
    segments: int
    dark_threshold: int
    light_threshold: int
    consistency_percentile: float
    average_weight: float
    consistency_weight: float
    std_norm: float
    dark_soft_mean: float
    light_soft_mean: float
    light_soft_span: float
    soft_weight: float
    uniform_base: float
    uniform_weight: float
    gradient_weight: float
    smooth_ratio: float
    smooth_min: int

@dataclass(frozen=True)
class EdgeRefineProfileParameters:
    top_ratio: float
    bottom_ratio: float
    mean_weight: float
    p75_weight: float
    smooth_ratio: float
    smooth_min: int
    high_percentile: float
    background_dark_threshold: int
    background_light_threshold: int
    y_edge_weight: float
    activity_percentile: float

@dataclass(frozen=True)
class HardGapTrustParameters:
    guard_ratio: float
    guard_min: int
    guard_max: int
    narrow_ratio: float
    narrow_min: float
    narrow_max: float
    model_delta_ratio: float
    geometry_width_ratio: float
    strong_min_score: float
    strong_width_min: float
    strong_width_max: float
    narrow_ok_score: float
    narrow_ok_width_min: float
    narrow_ok_width_max: float
    model_conflict_score: float
    core_content_threshold: int
    core_dark_threshold: int
    dark_mean_max: float
    dark_fraction_min: float
    dark_activity_max: float
    strong_core_content_max: float
    weak_mean_min: float
    weak_content_min: float
    frame_border_width_ratio: float
    continuity_min: float
    activity_min: float

__all__ = [
    'SeparatorGateParameters',
    'LeadingGridFailureParameters',
    'SeparatorGeometrySupportParameters',
    'SeparatorWidthProfileParameters',
    'NearbySeparatorCorrectionParameters',
    'RobustGridParameters',
    'GapSearchParameters',
    'EnhancedSeparatorParameters',
    'SeparatorProfileParameters',
    'EdgeRefineProfileParameters',
    'HardGapTrustParameters',
]
