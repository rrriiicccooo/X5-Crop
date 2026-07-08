from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OuterMaskProfileParameters:
    name: str
    low: int | None
    high: int | None
    min_row_fraction: float = 0.012
    min_col_fraction: float = 0.012


@dataclass(frozen=True)
class OuterBoxDetectionParameters:
    white_x_width_multiplier: float = 1.80
    white_x_extra_ratio: float = 0.060
    candidate_max_area: float = 0.94
    mask_expand_ratio: float = 0.002
    mask_profiles: tuple[OuterMaskProfileParameters, ...] = (
        OuterMaskProfileParameters("mask_not_white_246", None, 246),
        OuterMaskProfileParameters("mask_not_white_225", None, 225),
        OuterMaskProfileParameters("mask_mid_8_246", 8, 246),
    )
    min_width_ratio: float = 0.10
    min_height_ratio: float = 0.10
    min_width_px: int = 20
    min_height_px: int = 20
    bw_not_white_threshold: int = 246
    bw_dark_threshold: int = 210
    bw_min_fraction: float = 0.015
    bw_min_width_ratio: float = 0.10
    bw_min_height_ratio: float = 0.10
    bw_margin_ratio: float = 0.002
    bw_margin_min: int = 2
    white_border_ratio: float = 0.985
    white_run_ratio: float = 0.003
    white_run_min: int = 2
    white_run_max: int = 80
    white_dark_threshold: int = 30
    white_light_threshold: int = 225
    white_min_width_ratio: float = 0.10
    white_min_height_ratio: float = 0.10
    white_margin_ratio: float = 0.002
    white_margin_min: int = 2


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
    cross_axis_coverage_min: float = 0.62
    cross_axis_continuity_min: float = 0.55


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
class GapGeometryConstraintParameters:
    shift_ratio: float = 0.045
    shift_min: float = 20.0
    shift_max: float = 520.0


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
class SeparatorWidthProfileSearchParameters:
    threshold_ratio: float = 0.42
    threshold_span_ratio: float = 0.12
    sample_short_axis_max: int = 500
    sample_long_axis_max: int = 2000
    profile_smooth_short_axis_ratio: float = 0.018
    profile_smooth_min: int = 15
    min_width_ratio: float = 0.030
    min_width_min: int = 80
    min_width_max: int = 520
    max_width_ratio: float = 0.48
    max_width_floor: int = 600
    max_width_cap_ratio: float = 0.55
    core_width_cap_ratio: float = 0.20
    edge_margin_ratio: float = 0.18
    edge_margin_min: float = 60.0
    edge_margin_cap_ratio: float = 0.80
    gap_window_ratio: float = 0.28
    gap_window_min: int = 260
    gap_window_floor: int = 300
    gap_window_cap_ratio: float = 0.38
    gap_distance_penalty_weight: float = 0.35
    gap_score_base: float = 1.0


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
class EdgePairParameters:
    window_ratio: float = 0.070
    min_gutter_ratio: float = 0.003
    max_gutter_ratio: float = 0.040
    min_strength: float = 0.45
    min_background: float = 0.64
    min_quality_for_model_gap: float = 1.05
    min_quality_for_hard_gap: float = 0.70
    hard_gap_quality_ratio: float = 0.95
    max_hard_shift_ratio: float = 0.040


__all__ = [
    "EdgePairParameters",
    "EdgeRefineProfileParameters",
    "GapSearchParameters",
    "HardGapTrustParameters",
    "GapGeometryConstraintParameters",
    "NearbySeparatorRefinementParameters",
    "OuterBoxDetectionParameters",
    "OuterMaskProfileParameters",
    "SeparatorProfileParameters",
    "SeparatorWidthProfileSearchParameters",
]
