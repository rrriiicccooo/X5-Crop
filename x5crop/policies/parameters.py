from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Optional

from ..formats import FORMAT_CHOICES


@dataclass(frozen=True)
class EdgePairParams:
    window_ratio: float
    min_gutter_ratio: float
    max_gutter_ratio: float
    min_strength: float
    min_background: float
    min_quality_for_model_gap: float
    min_quality_for_hard_gap: float
    hard_gap_quality_ratio: float
    max_hard_shift_ratio: float


@dataclass(frozen=True)
class OuterMaskProfile:
    name: str
    low: Optional[int]
    high: Optional[int]
    min_row_fraction: float = 0.012
    min_col_fraction: float = 0.012


@dataclass(frozen=True)
class PartialCountParameters:
    offsets: tuple[float, ...]
    include_default_auto: bool


@dataclass(frozen=True)
class PartialEdgeHintParameters:
    window_ratio: float
    window_min: int
    window_max: int


@dataclass(frozen=True)
class SeparatorGateParameters:
    needed_hard_max: int
    max_equal_gaps_floor: int
    allow_geometry_support: bool
    hard_required_all_gaps: bool
    edge_pair_min_score_without_wide: float
    edge_pair_min_score_with_wide: float
    min_wide_gaps_for_auto: int
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
    wide_geometry_min_hard_ratio: float
    wide_geometry_min_joint_score: float
    stable_grid_min_hard_ratio: float
    stable_grid_min_joint_score: float
    max_width_cv: float
    max_outer_area_ratio: float


@dataclass(frozen=True)
class WideRetryParameters:
    full_enabled: bool
    partial_enabled: bool
    max_width_ratio: float
    confidence_cap: float


@dataclass(frozen=True)
class ContentEvidenceParameters:
    percentile: float
    threshold_multiplier: float
    threshold_min: float
    threshold_max: float
    aspect_ok_max: float
    present_mean_min: float
    present_coverage_min: float


@dataclass(frozen=True)
class ContentProfileParameters:
    smooth_ratio: float
    min_run_ratio: float
    threshold_min: float
    threshold_max: float
    p35_weight: float
    p65_multiplier: float


@dataclass(frozen=True)
class ContentMaskParameters:
    p55_weight: float
    p75_multiplier: float
    threshold_min: float
    threshold_max: float
    percentiles: tuple[float, float, float]
    bbox_min_fraction: float
    outer_min_width_ratio: float
    outer_min_height_ratio: float
    outer_min_width_px: int
    outer_min_height_px: int
    outer_expand_ratio: float


@dataclass(frozen=True)
class ContentCandidateParameters:
    expected_width_min_px: float
    coverage_weight: float
    mean_weight: float
    run_weight: float
    aspect_weight: float
    coverage_norm: float
    mean_norm: float
    aspect_norm: float
    weak_coverage: float
    aspect_uncertain: float
    grid_fallback_cap: float
    run_mismatch_cap: float
    runs_incomplete_cap: float
    weak_coverage_cap: float
    aspect_uncertain_cap: float


@dataclass(frozen=True)
class ContentSupportParameters:
    coverage_norm: float
    mean_norm: float
    aspect_norm: float
    coverage_weight: float
    mean_weight: float
    aspect_weight: float
    gate_ok: float
    gate_weak: float
    gate_low_content: float
    gate_aspect_conflict: float
    gate_unknown: float


@dataclass(frozen=True)
class OuterStrategyParameters:
    content_floating_full: bool
    content_floating_partial: bool
    edge_anchor_full_enabled: bool
    edge_anchor_full_mode: str
    edge_anchor_partial_enabled: bool
    edge_anchor_partial_mode: str
    separator_first_full_enabled: bool
    separator_first_full_mode: str
    separator_first_partial_enabled: bool
    separator_first_partial_mode: str
    separator_geometry_full_mode: str
    separator_geometry_partial_mode: str
    separator_gap_search_max_width_ratio: float
    content_aligned_retry: bool
    format_geometry_retry: bool
    short_axis_retry: bool


@dataclass(frozen=True)
class ContentFloatingOuterParameters:
    ratio_extras: tuple[float, ...]
    content_threshold: int
    content_margin_ratio: float
    content_margin_min: int
    content_margin_max: int
    min_width_ratio: float
    max_candidates: int


@dataclass(frozen=True)
class EdgeAnchorOuterParameters:
    partial_center_ratio: float
    ratio_extras: tuple[float, ...]
    content_threshold: int
    content_margin_ratio: float
    content_margin_min: int
    content_margin_max: int
    min_width_ratio: float
    max_candidates: int


@dataclass(frozen=True)
class BaseOuterCandidateParameters:
    white_x_width_multiplier: float
    white_x_extra_ratio: float
    candidate_max_area: float
    mask_expand_ratio: float
    mask_profiles: tuple[OuterMaskProfile, ...]
    min_width_ratio: float
    min_height_ratio: float
    min_width_px: int
    min_height_px: int
    bw_not_white_threshold: int
    bw_dark_threshold: int
    bw_min_fraction: float
    bw_min_width_ratio: float
    bw_min_height_ratio: float
    bw_margin_ratio: float
    bw_margin_min: int
    white_border_ratio: float
    white_run_ratio: float
    white_run_min: int
    white_run_max: int
    white_dark_threshold: int
    white_light_threshold: int
    white_min_width_ratio: float
    white_min_height_ratio: float
    white_margin_ratio: float
    white_margin_min: int


@dataclass(frozen=True)
class SeparatorOuterBandParameters:
    min_score: float
    band_score: float
    min_width_ratio: float
    max_width_ratio: float
    spacing_min_ratio: float
    spacing_max_ratio: float
    frame_error_max: float
    edge_margin_ratio: float
    source_candidate_count: int
    band_candidate_count: int
    pair_candidate_count: int
    max_candidates: int


@dataclass(frozen=True)
class SeparatorGeometryOuterParameters:
    required_count: int
    source_candidate_count: int
    margin_ratios: tuple[float, ...]
    max_candidates: int


@dataclass(frozen=True)
class FormatGeometryRetryParameters:
    enabled: bool
    ratio_tolerance: float
    min_shrink_ratio: float
    max_shrink_ratio: float
    content_margin_ratio: float
    content_margin_min: int
    content_margin_max: int


@dataclass(frozen=True)
class GridOuterRefineParameters:
    shift_ratio: float
    shift_min: int
    shift_max: int
    max_width_change: float


@dataclass(frozen=True)
class ShortAxisAspectRetryParameters:
    enabled: bool
    min_error: float
    target_aspect: float
    margin_ratio: float
    margin_min: int
    margin_max: int


@dataclass(frozen=True)
class OuterContentAlignmentParameters:
    white_edge_long_ratio: float
    white_edge_long_min: int
    white_edge_long_max: int
    long_gate_ratio: float
    long_gate_min: int
    long_gate_max: int
    short_gate_ratio: float
    short_gate_min: int
    short_gate_max: int
    long_excess_ratio: float
    long_gate_excess_ratio: float
    short_excess_ratio: float
    short_requires_hard_anchors: bool
    short_content_height_max: float
    content_width_min: float
    edge_short_ratio: float
    edge_dark_max: float
    border_band_ratio: float
    margin_x_ratio: float
    margin_x_min: int
    margin_x_max: int
    margin_y_ratio: float
    margin_y_min: int
    margin_y_max: int
    long_margin_ratio: float
    long_margin_cap_ratio: float
    long_margin_cap_min: int
    long_margin_cap_max: int
    short_margin_ratio: float
    short_margin_cap_ratio: float
    short_margin_cap_min: int
    short_margin_cap_max: int


@dataclass(frozen=True)
class PartialHolderParameters:
    enabled: bool
    min_count_35mm: int
    min_count_small: int
    min_hard_gaps: int
    min_hard_ratio: float
    max_equal_gaps: int
    max_width_cv: float
    min_joint_score: float
    min_content_score: float
    min_geometry_score: float
    min_wide_like_gaps: int
    wide_like_min_width_ratio: float
    leading_content_check: bool
    leading_content_max_mean: float
    leading_content_max_coverage: float
    leading_content_band_ratio: float
    frame_content_check: bool
    min_frame_mean: float
    min_frame_coverage: float


@dataclass(frozen=True)
class ScoringCalibrationParameters:
    hard_full_confidence_floor: float
    geometry_weight: float
    content_weight: float
    separator_weight: float
    separator_source_bias: float
    no_auto_cap_partial: float
    no_auto_cap_full: float


@dataclass(frozen=True)
class BaseDetectionScoreParameters:
    width_cv_norm: float
    gap_weight: float
    width_weight: float
    outer_weight: float
    contrast_weight: float
    outer_min_area: float
    outer_max_area: float
    outer_too_large: float
    outer_uncertain_confidence: float
    contrast_min: float
    contrast_floor: float
    full_width_cv: float
    geometry_floor_tight_cv: float
    geometry_floor_high: float
    geometry_floor_low: float
    unstable_width_cv: float
    full_outer_min_area: float
    low_confidence_floor: float
    partial_one_cap: float
    partial_two_35mm_cap: float
    partial_general_cap: float
    outer_too_large_cap: float


@dataclass(frozen=True)
class SeparatorSupportScoreParameters:
    model_grid_credit: float
    model_equal_credit: float
    hard_weight: float
    model_weight: float
    no_expected_confidence_threshold: float
    no_expected_confidence_cap: float


@dataclass(frozen=True)
class GeometrySupportScoreParameters:
    width_cv_norm: float
    outer_min_area: float
    outer_max_area: float
    outer_uncertain_score: float
    aspect_norm: float
    no_aspect_score: float
    width_weight: float
    outer_weight: float
    aspect_weight: float
    count_weight: float


@dataclass(frozen=True)
class CandidateCompetitionParameters:
    top_n: int
    close_margin: float
    confidence_cap: float


@dataclass(frozen=True)
class PostprocessParameters:
    retry_uncertain_outer: bool
    content_aspect_conflict_cap: float
    content_low_confidence_cap: float
    outer_mismatch_cap: float
    lucky_pass_risk_cap: float


@dataclass(frozen=True)
class ApprovedGeometryAdjustmentParameters:
    long_limit_ratio: float
    long_limit_min: int
    long_limit_max: int
    min_ext_ratio: float
    min_ext_min: int
    min_ext_max: int


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
    wide_min_mean: float
    wide_min_prominence: float


@dataclass(frozen=True)
class EnhancedSeparatorParameters:
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
class DiagnosticOverlapRiskParameters:
    mean_min: float
    weak_continuity: float
    weak_activity: float
    medium_continuity: float
    medium_activity: float
    strong_continuity: float
    strong_activity: float


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
    unstable_width_cv: float
    unstable_width_weight: float
    mild_width_cv: float
    mild_width_weight: float
    strong_hard_credit_min: int
    strong_hard_credit: float
    stable_width_cv: float
    stable_model_gap_min: int
    stable_geometry_credit: float
    risk_threshold: float


@dataclass(frozen=True)
class FormatParameters:
    name: str
    outer_white_x_width_multiplier: float = 1.80
    outer_white_x_extra_ratio: float = 0.060
    outer_candidate_max_area: float = 0.94
    outer_mask_expand_ratio: float = 0.002
    outer_mask_profiles: tuple[OuterMaskProfile, ...] = (
        OuterMaskProfile("mask_not_white_246", None, 246),
        OuterMaskProfile("mask_not_white_225", None, 225),
        OuterMaskProfile("mask_mid_8_246", 8, 246),
    )
    outer_min_width_ratio: float = 0.10
    outer_min_height_ratio: float = 0.10
    outer_min_width_px: int = 20
    outer_min_height_px: int = 20
    outer_bw_not_white_threshold: int = 246
    outer_bw_dark_threshold: int = 210
    outer_bw_min_fraction: float = 0.015
    outer_bw_min_width_ratio: float = 0.10
    outer_bw_min_height_ratio: float = 0.10
    outer_bw_margin_ratio: float = 0.002
    outer_bw_margin_min: int = 2
    outer_white_border_ratio: float = 0.985
    outer_white_run_ratio: float = 0.003
    outer_white_run_min: int = 2
    outer_white_run_max: int = 80
    outer_white_dark_threshold: int = 30
    outer_white_light_threshold: int = 225
    outer_white_min_width_ratio: float = 0.10
    outer_white_min_height_ratio: float = 0.10
    outer_white_margin_ratio: float = 0.002
    outer_white_margin_min: int = 2
    content_profile_smooth_ratio: float = 0.010
    content_profile_min_run_ratio: float = 0.20
    content_profile_threshold_min: float = 0.035
    content_profile_threshold_max: float = 0.40
    content_profile_p35_weight: float = 0.38
    content_profile_p65_multiplier: float = 0.82
    content_mask_p55_weight: float = 0.34
    content_mask_p75_multiplier: float = 0.78
    content_mask_min: float = 0.045
    content_mask_max: float = 0.45
    content_mask_percentiles: tuple[float, float, float] = (55.0, 75.0, 92.0)
    content_bbox_min_fraction: float = 0.008
    content_outer_min_width_ratio: float = 0.08
    content_outer_min_height_ratio: float = 0.08
    content_outer_min_width_px: int = 60
    content_outer_min_height_px: int = 30
    content_expected_width_min_px: float = 8.0
    content_candidate_coverage_weight: float = 0.38
    content_candidate_mean_weight: float = 0.30
    content_candidate_run_weight: float = 0.22
    content_candidate_aspect_weight: float = 0.10
    content_conf_coverage_norm: float = 0.22
    content_conf_mean_norm: float = 0.16
    content_conf_aspect_norm: float = 0.18
    content_weak_coverage: float = 0.14
    content_aspect_uncertain: float = 0.18
    content_evidence_percentile: float = 70.0
    content_evidence_threshold_multiplier: float = 0.70
    content_evidence_threshold_min: float = 0.08
    content_evidence_threshold_max: float = 0.45
    content_evidence_aspect_ok_max: float = 0.22
    content_evidence_present_mean_min: float = 0.075
    content_evidence_present_coverage_min: float = 0.18
    content_grid_fallback_cap: float = 0.82
    content_run_mismatch_cap: float = 0.84
    content_runs_incomplete_cap: float = 0.84
    content_weak_coverage_cap: float = 0.82
    content_aspect_uncertain_cap: float = 0.82
    post_content_aspect_conflict_cap: float = 0.82
    post_content_low_confidence_cap: float = 0.84
    post_outer_mismatch_cap: float = 0.84
    post_lucky_pass_risk_cap: float = 0.84
    gap_radius_ratio: float = 0.16
    gap_radius_min: int = 6
    gap_radius_max: int = 900
    gap_max_width_ratio: float = 0.045
    gap_max_width_min: int = 2
    gap_max_width_max: int = 420
    wide_gap_retry_enabled: bool = True
    wide_gap_retry_max_width_ratio: float = 0.060
    wide_gap_min_mean: float = 0.95
    wide_gap_min_prominence: float = 0.02
    wide_gap_confidence_cap: float = 0.995
    gap_min_width_ratio: float = 0.001
    gap_min_width_min: int = 1
    gap_min_width_max: int = 12
    gap_guard_ratio: float = 0.035
    gap_guard_min: int = 3
    gap_guard_max: int = 220
    gap_min_score: float = 0.22
    gap_peak_multiplier: float = 0.90
    gap_band_multiplier: float = 0.62
    constrain_full_shift_ratio: float = 0.045
    constrain_partial_shift_ratio: float = 0.12
    constrain_shift_min: float = 20.0
    constrain_shift_max: float = 520.0
    nearby_window_ratio: float = 0.040
    nearby_window_min: int = 16
    nearby_window_max: int = 320
    nearby_exclude_ratio: float = 0.012
    nearby_exclude_min: int = 8
    nearby_exclude_max: int = 120
    nearby_max_width_ratio: float = 0.070
    nearby_max_width_min: int = 2
    nearby_max_width_max: int = 520
    nearby_distance_ratio: float = 0.040
    nearby_score_add: float = 0.10
    nearby_score_multiplier: float = 1.22
    nearby_detail_score_add: float = 0.08
    nearby_detail_score_multiplier: float = 1.18
    nearby_local_gain_ratio: float = 0.006
    nearby_local_gain_min: float = 8.0
    nearby_local_gain_max: float = 40.0
    nearby_active_correction: bool = True
    robust_reliable_min_score: float = 0.28
    robust_min_reliable: int = 2
    robust_pitch_min_ratio: float = 0.70
    robust_pitch_max_ratio: float = 1.30
    robust_full_tolerance_ratio: float = 0.040
    robust_partial_tolerance_ratio: float = 0.090
    robust_tolerance_min: float = 4.0
    robust_tolerance_max: float = 520.0
    robust_reject_residual_ratio: float = 0.045
    robust_full_shift_ratio: float = 0.035
    robust_partial_shift_ratio: float = 0.10
    robust_shift_min: float = 20.0
    robust_shift_max: float = 520.0
    robust_hard_keep_ratio: float = 0.025
    robust_hard_keep_min: float = 3.0
    robust_hard_keep_max: float = 180.0
    robust_hard_protect_ratio: float = 0.006
    robust_hard_protect_min: float = 12.0
    robust_hard_protect_max: float = 40.0
    enhanced_max_width_ratio: float = 0.040
    enhanced_max_width_min: float = 3.0
    enhanced_max_width_max: float = 420.0
    enhanced_shift_ratio: float = 0.035
    enhanced_shift_min: float = 4.0
    enhanced_shift_max: float = 420.0
    enhanced_auto_low_score: float = 0.34
    separator_profile_top_ratio: float = 0.10
    separator_profile_bottom_ratio: float = 0.90
    separator_profile_segments: int = 5
    separator_profile_dark_threshold: int = 30
    separator_profile_light_threshold: int = 225
    separator_profile_consistency_percentile: float = 20.0
    separator_profile_average_weight: float = 0.35
    separator_profile_consistency_weight: float = 0.65
    separator_profile_std_norm: float = 70.0
    separator_profile_dark_soft_mean: float = 54.0
    separator_profile_light_soft_mean: float = 225.0
    separator_profile_light_soft_span: float = 30.0
    separator_profile_soft_weight: float = 0.50
    separator_profile_uniform_base: float = 0.90
    separator_profile_uniform_weight: float = 0.10
    separator_profile_gradient_weight: float = 0.25
    separator_profile_smooth_ratio: float = 0.0015
    separator_profile_smooth_min: int = 3
    edge_refine_top_ratio: float = 0.12
    edge_refine_bottom_ratio: float = 0.88
    edge_refine_mean_weight: float = 0.65
    edge_refine_p75_weight: float = 0.35
    edge_refine_smooth_ratio: float = 0.0008
    edge_refine_smooth_min: int = 3
    edge_refine_high_percentile: float = 99.2
    edge_refine_background_dark_threshold: int = 30
    edge_refine_background_light_threshold: int = 225
    edge_refine_y_edge_weight: float = 0.50
    edge_refine_activity_percentile: float = 95.0
    hard_trust_guard_ratio: float = 0.020
    hard_trust_guard_min: int = 4
    hard_trust_guard_max: int = 80
    hard_trust_narrow_ratio: float = 0.020
    hard_trust_narrow_min: float = 3.0
    hard_trust_narrow_max: float = 140.0
    hard_trust_model_delta_ratio: float = 0.040
    hard_trust_geometry_width_ratio: float = 0.018
    hard_trust_strong_min_score: float = 0.90
    hard_trust_strong_width_min: float = 0.018
    hard_trust_strong_width_max: float = 0.065
    hard_trust_narrow_ok_score: float = 0.70
    hard_trust_narrow_ok_width_min: float = 0.006
    hard_trust_narrow_ok_width_max: float = 0.018
    hard_trust_model_conflict_score: float = 1.05
    hard_trust_core_content_threshold: int = 235
    hard_trust_core_dark_threshold: int = 55
    hard_trust_dark_mean_max: float = 45.0
    hard_trust_dark_fraction_min: float = 0.45
    hard_trust_dark_activity_max: float = 0.18
    hard_trust_strong_core_content_max: float = 0.08
    hard_trust_weak_mean_min: float = 70.0
    hard_trust_weak_content_min: float = 0.10
    hard_trust_frame_border_width_ratio: float = 0.010
    hard_trust_continuity_min: float = 0.12
    hard_trust_activity_min: float = 0.030
    diagnostic_overlap_mean_min: float = 55.0
    diagnostic_overlap_weak_continuity: float = 0.16
    diagnostic_overlap_weak_activity: float = 0.04
    diagnostic_overlap_medium_continuity: float = 0.35
    diagnostic_overlap_medium_activity: float = 0.08
    diagnostic_overlap_strong_continuity: float = 0.70
    diagnostic_overlap_strong_activity: float = 0.12
    debug_gap_overlap_tolerance_ratio: float = 0.012
    debug_gap_overlap_tolerance_min: float = 4.0
    debug_gap_overlap_tolerance_max: float = 80.0
    debug_gap_tick_length_ratio: float = 0.12
    debug_gap_tick_length_min: int = 20
    debug_gap_hard_line_width: int = 2
    debug_gap_model_line_width: int = 2
    debug_gap_diagnostic_line_width: int = 3
    outer_align_white_edge_long_ratio: float = 0.0190
    outer_align_white_edge_long_min: int = 90
    outer_align_white_edge_long_max: int = 180
    outer_align_long_gate_ratio: float = 0.0340
    outer_align_long_gate_min: int = 160
    outer_align_long_gate_max: int = 320
    outer_align_short_gate_ratio: float = 0.0060
    outer_align_short_gate_min: int = 28
    outer_align_short_gate_max: int = 80
    outer_align_long_excess_ratio: float = 0.050
    outer_align_long_gate_excess_ratio: float = 0.035
    outer_align_short_excess_ratio: float = 0.035
    outer_align_short_requires_hard_anchors: bool = False
    outer_align_short_content_height_max: float = 1.0
    outer_align_content_width_min: float = 0.985
    outer_align_edge_short_ratio: float = 0.015
    outer_align_edge_dark_max: float = 0.02
    outer_align_border_band_ratio: float = 0.018
    outer_align_margin_x_ratio: float = 0.0030
    outer_align_margin_x_min: int = 15
    outer_align_margin_x_max: int = 30
    outer_align_margin_y_ratio: float = 0.0030
    outer_align_margin_y_min: int = 10
    outer_align_margin_y_max: int = 20
    outer_align_long_margin_ratio: float = 0.012
    outer_align_long_margin_cap_ratio: float = 0.0170
    outer_align_long_margin_cap_min: int = 80
    outer_align_long_margin_cap_max: int = 160
    outer_align_short_margin_ratio: float = 0.010
    outer_align_short_margin_cap_ratio: float = 0.010
    outer_align_short_margin_cap_min: int = 40
    outer_align_short_margin_cap_max: int = 80
    score_width_cv_norm: float = 0.030
    score_gap_weight: float = 0.40
    score_width_weight: float = 0.30
    score_outer_weight: float = 0.20
    score_contrast_weight: float = 0.10
    score_outer_min_area: float = 0.35
    score_outer_max_area: float = 0.995
    score_outer_too_large: float = 0.94
    score_outer_uncertain_confidence: float = 0.45
    score_contrast_min: float = 35.0
    score_contrast_floor: float = 0.35
    score_full_width_cv: float = 0.040
    score_geometry_floor_tight_cv: float = 0.006
    score_geometry_floor_high: float = 0.92
    score_geometry_floor_low: float = 0.88
    score_unstable_width_cv: float = 0.030
    score_full_outer_min_area: float = 0.40
    score_gate_min_hard_gaps: int = 2
    score_gate_max_equal_gaps_floor: int = 2
    score_gate_low_hard_confidence_cap: float = 0.82
    score_gate_mostly_equal_confidence_cap: float = 0.84
    score_partial_one_cap: float = 0.78
    score_partial_two_35mm_cap: float = 0.82
    score_partial_general_cap: float = 0.84
    score_outer_too_large_cap: float = 0.82
    score_low_confidence_floor: float = 0.85
    score_gate_allow_full_detected_geometry: bool = True
    score_gate_allow_geometry_support: bool = True
    calibrate_hard_full_confidence_floor: float = 0.0
    separator_model_grid_credit: float = 0.35
    separator_model_equal_credit: float = 0.12
    separator_gate_profile: str = "min_hard_with_equal_cap"
    separator_gate_needed_hard_max: int = 2
    separator_gate_max_equal_gaps_floor: int = 2
    separator_allow_geometry_support: bool = True
    separator_wide_geometry_min_hard_ratio: float = 0.60
    separator_wide_geometry_min_joint_score: float = 0.78
    separator_stable_grid_min_hard_ratio: float = 0.35
    separator_stable_grid_min_joint_score: float = 0.65
    separator_hard_required_all_gaps: bool = True
    separator_gate_edge_pair_min_score_without_wide: float = 0.0
    separator_gate_edge_pair_min_score_with_wide: float = 0.0
    separator_gate_min_wide_gaps_for_auto: int = 0
    leading_grid_failure_enabled: bool = True
    leading_grid_failure_min_count: int = 5
    leading_grid_failure_leading_count: int = 3
    leading_grid_failure_low_score: float = 0.35
    leading_grid_failure_very_low_score: float = 0.12
    leading_grid_failure_very_low_count: int = 2
    leading_grid_failure_max_hard: int = 2
    geometry_width_cv_norm: float = 0.040
    content_support_aspect_norm: float = 0.22
    content_support_coverage_weight: float = 0.42
    content_support_mean_weight: float = 0.40
    content_support_aspect_weight: float = 0.18
    content_support_gate_ok: float = 1.0
    content_support_gate_weak: float = 0.72
    content_support_gate_low_content: float = 0.58
    content_support_gate_aspect_conflict: float = 0.35
    content_support_gate_unknown: float = 0.50
    geometry_support_width_weight: float = 0.34
    geometry_support_outer_weight: float = 0.24
    geometry_support_aspect_weight: float = 0.26
    geometry_support_count_weight: float = 0.16
    geometry_support_outer_uncertain: float = 0.55
    geometry_support_no_aspect_score: float = 0.80
    separator_support_hard_weight: float = 0.78
    separator_support_model_weight: float = 0.22
    calibrate_geometry_weight: float = 0.34
    calibrate_content_weight: float = 0.33
    calibrate_separator_weight: float = 0.33
    calibrate_separator_source_bias: float = 0.03
    calibrate_partial_no_auto_cap: float = 0.82
    calibrate_full_no_auto_cap: float = 0.84
    candidate_competition_top_n: int = 8
    candidate_competition_close_margin: float = 0.04
    candidate_competition_confidence_cap: float = 0.84
    grid_outer_refine_shift_ratio: float = 0.080
    grid_outer_refine_shift_min: int = 8
    grid_outer_refine_shift_max: int = 420
    grid_outer_refine_max_width_change: float = 0.12
    deskew_min_outer_width: int = 100
    deskew_outer_dark_threshold: int = 245
    deskew_outer_min_fraction: float = 0.01
    deskew_sample_width_px: int = 350
    deskew_min_samples: int = 6
    deskew_max_samples: int = 24
    deskew_min_col_content: int = 10
    deskew_min_col_content_ratio: float = 0.05
    deskew_slope_delta_max: float = 0.006
    deskew_residual_min: float = 3.0
    deskew_residual_height_ratio: float = 0.003
    deskew_auto_quality_ok: float = 8.0
    deskew_enhanced_quality_gain: float = 3.0
    deskew_fit_min_points: int = 4
    deskew_fit_tolerance_min: float = 2.0
    deskew_fit_tolerance_multiplier: float = 3.0
    deskew_span_skip_ratio: float = 0.0005
    deskew_span_skip_min: float = 3.0
    deskew_span_skip_max: float = 12.0
    partial_offsets: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    partial_edge_hint_window_ratio: float = 0.18
    partial_edge_hint_window_min: int = 8
    partial_edge_hint_window_max: int = 900
    partial_auto_include_default_count: bool = False
    partial_safe_extra_frames_enabled: bool = True
    partial_safe_extra_frames_min_count_35mm: int = 2
    partial_safe_extra_frames_min_count_small: int = 2
    partial_safe_extra_frames_min_hard_gaps: int = 1
    partial_safe_extra_frames_min_hard_ratio: float = 0.15
    partial_safe_extra_frames_max_equal_gaps: int = 0
    partial_safe_extra_frames_max_width_cv: float = 0.055
    partial_safe_extra_frames_min_joint_score: float = 0.65
    partial_safe_extra_frames_min_content_score: float = 0.72
    partial_safe_extra_frames_min_geometry_score: float = 0.72
    partial_safe_extra_frames_min_wide_like_gaps: int = 0
    partial_safe_extra_frames_wide_like_min_width_ratio: float = 0.033
    partial_safe_extra_frames_leading_content_check: bool = False
    partial_safe_extra_frames_leading_content_max_mean: float = 0.20
    partial_safe_extra_frames_leading_content_max_coverage: float = 0.34
    partial_safe_extra_frames_leading_content_band_ratio: float = 0.04
    partial_safe_extra_frames_frame_content_check: bool = False
    partial_safe_extra_frames_min_frame_mean: float = 0.055
    partial_safe_extra_frames_min_frame_coverage: float = 0.10
    lucky_pass_risk_enabled: bool = True
    lucky_model_gap_support_min: int = 2
    lucky_model_gap_support_weight: float = 0.24
    lucky_minor_model_gap_support_weight: float = 0.08
    lucky_limited_strong_hard_max: int = 2
    lucky_limited_strong_hard_weight: float = 0.20
    lucky_very_limited_strong_hard_max: int = 1
    lucky_very_limited_strong_hard_weight: float = 0.10
    lucky_suspicious_hard_weight: float = 0.20
    lucky_strong_overlap_weight: float = 0.20
    lucky_combo_weight: float = 0.12
    lucky_unstable_width_cv: float = 0.006
    lucky_unstable_width_weight: float = 0.16
    lucky_mild_width_cv: float = 0.003
    lucky_mild_width_weight: float = 0.08
    lucky_strong_hard_credit_min: int = 3
    lucky_strong_hard_credit: float = -0.15
    lucky_stable_width_cv: float = 0.002
    lucky_stable_model_gap_min: int = 3
    lucky_stable_geometry_credit: float = -0.35
    lucky_risk_threshold: float = 0.80
    approved_adjust_long_limit_ratio: float = 0.018
    approved_adjust_long_limit_min: int = 20
    approved_adjust_long_limit_max: int = 60
    approved_adjust_min_ext_ratio: float = 0.0100
    approved_adjust_min_ext_min: int = 50
    approved_adjust_min_ext_max: int = 120
    separator_geometry_outer_full_mode: str = "off"
    separator_geometry_outer_partial_mode: str = "off"
    separator_geometry_outer_count: int = 0
    separator_geometry_outer_max_candidates: int = 8
    separator_geometry_outer_margin_ratios: tuple[float, ...] = (0.00, 0.018, 0.035)
    separator_geometry_outer_source_candidates: int = 3
    outer_retry_enabled: bool = True
    short_axis_aspect_retry_enabled: bool = False
    short_axis_aspect_retry_min_error: float = 0.24
    short_axis_aspect_retry_target_aspect: float = 1.0
    short_axis_aspect_retry_margin_ratio: float = 0.008
    short_axis_aspect_retry_margin_min: int = 12
    short_axis_aspect_retry_margin_max: int = 80
    format_geometry_outer_retry_enabled: bool = True
    format_geometry_outer_retry_ratio_tolerance: float = 0.025
    format_geometry_outer_retry_min_shrink_ratio: float = 0.003
    format_geometry_outer_retry_max_shrink_ratio: float = 0.120
    format_geometry_outer_retry_content_margin_ratio: float = 0.010
    format_geometry_outer_retry_content_margin_min: int = 12
    format_geometry_outer_retry_content_margin_max: int = 80
    floating_outer_full_enabled: bool = False
    floating_outer_partial_enabled: bool = True
    floating_outer_ratio_extras: tuple[float, ...] = (0.06, 0.10)
    floating_outer_content_threshold: int = 225
    floating_outer_content_margin_ratio: float = 0.012
    floating_outer_content_margin_min: int = 12
    floating_outer_content_margin_max: int = 80
    floating_outer_min_width_ratio: float = 0.30
    floating_outer_max_candidates: int = 12
    long_axis_edge_anchor_outer_enabled: bool = False
    long_axis_edge_anchor_outer_mode: str = "fallback"
    long_axis_edge_anchor_partial_enabled: bool = True
    long_axis_edge_anchor_partial_mode: str = "fallback"
    long_axis_edge_anchor_partial_center_ratio: float = 0.35
    long_axis_edge_anchor_ratio_extras: tuple[float, ...] = (0.06, 0.10)
    long_axis_edge_anchor_content_threshold: int = 225
    long_axis_edge_anchor_content_margin_ratio: float = 0.012
    long_axis_edge_anchor_content_margin_min: int = 12
    long_axis_edge_anchor_content_margin_max: int = 80
    long_axis_edge_anchor_min_width_ratio: float = 0.30
    long_axis_edge_anchor_max_candidates: int = 8
    separator_first_outer_enabled: bool = False
    separator_first_outer_mode: str = "fallback"
    separator_first_partial_enabled: bool = True
    separator_first_partial_mode: str = "fallback"
    separator_first_outer_min_score: float = 0.58
    separator_first_outer_band_score: float = 0.36
    separator_first_outer_min_width_ratio: float = 0.006
    separator_first_outer_max_width_ratio: float = 0.120
    separator_first_outer_spacing_min_ratio: float = 0.82
    separator_first_outer_spacing_max_ratio: float = 1.24
    separator_first_outer_frame_error_max: float = 0.18
    separator_first_outer_edge_margin_ratio: float = 0.18
    separator_first_outer_gap_max_width_ratio: float = 0.095
    separator_first_outer_source_candidates: int = 2
    separator_first_outer_band_candidates: int = 10
    separator_first_outer_pair_candidates: int = 4
    separator_first_outer_max_candidates: int = 12
    wide_gap_retry_partial_enabled: bool = True

    @property
    def partial_counts(self) -> PartialCountParameters:
        return PartialCountParameters(
            offsets=self.partial_offsets,
            include_default_auto=self.partial_auto_include_default_count,
        )

    @property
    def partial_edge_hint(self) -> PartialEdgeHintParameters:
        return PartialEdgeHintParameters(
            window_ratio=self.partial_edge_hint_window_ratio,
            window_min=self.partial_edge_hint_window_min,
            window_max=self.partial_edge_hint_window_max,
        )

    @property
    def separator_gate(self) -> SeparatorGateParameters:
        return SeparatorGateParameters(
            needed_hard_max=self.separator_gate_needed_hard_max,
            max_equal_gaps_floor=self.separator_gate_max_equal_gaps_floor,
            allow_geometry_support=self.separator_allow_geometry_support,
            hard_required_all_gaps=self.separator_hard_required_all_gaps,
            edge_pair_min_score_without_wide=self.separator_gate_edge_pair_min_score_without_wide,
            edge_pair_min_score_with_wide=self.separator_gate_edge_pair_min_score_with_wide,
            min_wide_gaps_for_auto=self.separator_gate_min_wide_gaps_for_auto,
            score_min_hard_gaps=self.score_gate_min_hard_gaps,
            score_max_equal_gaps_floor=self.score_gate_max_equal_gaps_floor,
            low_hard_confidence_cap=self.score_gate_low_hard_confidence_cap,
            mostly_equal_confidence_cap=self.score_gate_mostly_equal_confidence_cap,
            allow_full_detected_geometry=self.score_gate_allow_full_detected_geometry,
        )

    @property
    def leading_grid_failure(self) -> LeadingGridFailureParameters:
        return LeadingGridFailureParameters(
            enabled=self.leading_grid_failure_enabled,
            min_expected_gaps=self.leading_grid_failure_min_count,
            leading_count=self.leading_grid_failure_leading_count,
            low_score=self.leading_grid_failure_low_score,
            very_low_score=self.leading_grid_failure_very_low_score,
            very_low_count=self.leading_grid_failure_very_low_count,
            max_hard_gaps=self.leading_grid_failure_max_hard,
        )

    @property
    def separator_geometry_support(self) -> SeparatorGeometrySupportParameters:
        return SeparatorGeometrySupportParameters(
            wide_geometry_min_hard_ratio=self.separator_wide_geometry_min_hard_ratio,
            wide_geometry_min_joint_score=self.separator_wide_geometry_min_joint_score,
            stable_grid_min_hard_ratio=self.separator_stable_grid_min_hard_ratio,
            stable_grid_min_joint_score=self.separator_stable_grid_min_joint_score,
            max_width_cv=self.score_full_width_cv,
            max_outer_area_ratio=self.score_outer_max_area,
        )

    @property
    def wide_retry(self) -> WideRetryParameters:
        return WideRetryParameters(
            full_enabled=self.wide_gap_retry_enabled,
            partial_enabled=self.wide_gap_retry_partial_enabled,
            max_width_ratio=self.wide_gap_retry_max_width_ratio,
            confidence_cap=self.wide_gap_confidence_cap,
        )

    @property
    def content_evidence(self) -> ContentEvidenceParameters:
        return ContentEvidenceParameters(
            percentile=self.content_evidence_percentile,
            threshold_multiplier=self.content_evidence_threshold_multiplier,
            threshold_min=self.content_evidence_threshold_min,
            threshold_max=self.content_evidence_threshold_max,
            aspect_ok_max=self.content_evidence_aspect_ok_max,
            present_mean_min=self.content_evidence_present_mean_min,
            present_coverage_min=self.content_evidence_present_coverage_min,
        )

    @property
    def content_profile(self) -> ContentProfileParameters:
        return ContentProfileParameters(
            smooth_ratio=self.content_profile_smooth_ratio,
            min_run_ratio=self.content_profile_min_run_ratio,
            threshold_min=self.content_profile_threshold_min,
            threshold_max=self.content_profile_threshold_max,
            p35_weight=self.content_profile_p35_weight,
            p65_multiplier=self.content_profile_p65_multiplier,
        )

    @property
    def content_mask(self) -> ContentMaskParameters:
        return ContentMaskParameters(
            p55_weight=self.content_mask_p55_weight,
            p75_multiplier=self.content_mask_p75_multiplier,
            threshold_min=self.content_mask_min,
            threshold_max=self.content_mask_max,
            percentiles=self.content_mask_percentiles,
            bbox_min_fraction=self.content_bbox_min_fraction,
            outer_min_width_ratio=self.content_outer_min_width_ratio,
            outer_min_height_ratio=self.content_outer_min_height_ratio,
            outer_min_width_px=self.content_outer_min_width_px,
            outer_min_height_px=self.content_outer_min_height_px,
            outer_expand_ratio=self.outer_mask_expand_ratio,
        )

    @property
    def content_candidate(self) -> ContentCandidateParameters:
        return ContentCandidateParameters(
            expected_width_min_px=self.content_expected_width_min_px,
            coverage_weight=self.content_candidate_coverage_weight,
            mean_weight=self.content_candidate_mean_weight,
            run_weight=self.content_candidate_run_weight,
            aspect_weight=self.content_candidate_aspect_weight,
            coverage_norm=self.content_conf_coverage_norm,
            mean_norm=self.content_conf_mean_norm,
            aspect_norm=self.content_conf_aspect_norm,
            weak_coverage=self.content_weak_coverage,
            aspect_uncertain=self.content_aspect_uncertain,
            grid_fallback_cap=self.content_grid_fallback_cap,
            run_mismatch_cap=self.content_run_mismatch_cap,
            runs_incomplete_cap=self.content_runs_incomplete_cap,
            weak_coverage_cap=self.content_weak_coverage_cap,
            aspect_uncertain_cap=self.content_aspect_uncertain_cap,
        )

    @property
    def content_support(self) -> ContentSupportParameters:
        return ContentSupportParameters(
            coverage_norm=self.content_conf_coverage_norm,
            mean_norm=self.content_conf_mean_norm,
            aspect_norm=self.content_support_aspect_norm,
            coverage_weight=self.content_support_coverage_weight,
            mean_weight=self.content_support_mean_weight,
            aspect_weight=self.content_support_aspect_weight,
            gate_ok=self.content_support_gate_ok,
            gate_weak=self.content_support_gate_weak,
            gate_low_content=self.content_support_gate_low_content,
            gate_aspect_conflict=self.content_support_gate_aspect_conflict,
            gate_unknown=self.content_support_gate_unknown,
        )

    @property
    def outer_strategy(self) -> OuterStrategyParameters:
        return OuterStrategyParameters(
            content_floating_full=self.floating_outer_full_enabled,
            content_floating_partial=self.floating_outer_partial_enabled,
            edge_anchor_full_enabled=self.long_axis_edge_anchor_outer_enabled,
            edge_anchor_full_mode=self.long_axis_edge_anchor_outer_mode,
            edge_anchor_partial_enabled=self.long_axis_edge_anchor_partial_enabled,
            edge_anchor_partial_mode=self.long_axis_edge_anchor_partial_mode,
            separator_first_full_enabled=self.separator_first_outer_enabled,
            separator_first_full_mode=self.separator_first_outer_mode,
            separator_first_partial_enabled=self.separator_first_partial_enabled,
            separator_first_partial_mode=self.separator_first_partial_mode,
            separator_geometry_full_mode=self.separator_geometry_outer_full_mode,
            separator_geometry_partial_mode=self.separator_geometry_outer_partial_mode,
            separator_gap_search_max_width_ratio=self.separator_first_outer_gap_max_width_ratio,
            content_aligned_retry=self.outer_retry_enabled,
            format_geometry_retry=self.format_geometry_outer_retry_enabled,
            short_axis_retry=self.short_axis_aspect_retry_enabled,
        )

    @property
    def content_floating_outer(self) -> ContentFloatingOuterParameters:
        return ContentFloatingOuterParameters(
            ratio_extras=self.floating_outer_ratio_extras,
            content_threshold=self.floating_outer_content_threshold,
            content_margin_ratio=self.floating_outer_content_margin_ratio,
            content_margin_min=self.floating_outer_content_margin_min,
            content_margin_max=self.floating_outer_content_margin_max,
            min_width_ratio=self.floating_outer_min_width_ratio,
            max_candidates=self.floating_outer_max_candidates,
        )

    @property
    def edge_anchor_outer(self) -> EdgeAnchorOuterParameters:
        return EdgeAnchorOuterParameters(
            partial_center_ratio=self.long_axis_edge_anchor_partial_center_ratio,
            ratio_extras=self.long_axis_edge_anchor_ratio_extras,
            content_threshold=self.long_axis_edge_anchor_content_threshold,
            content_margin_ratio=self.long_axis_edge_anchor_content_margin_ratio,
            content_margin_min=self.long_axis_edge_anchor_content_margin_min,
            content_margin_max=self.long_axis_edge_anchor_content_margin_max,
            min_width_ratio=self.long_axis_edge_anchor_min_width_ratio,
            max_candidates=self.long_axis_edge_anchor_max_candidates,
        )

    @property
    def base_outer_candidates(self) -> BaseOuterCandidateParameters:
        return BaseOuterCandidateParameters(
            white_x_width_multiplier=self.outer_white_x_width_multiplier,
            white_x_extra_ratio=self.outer_white_x_extra_ratio,
            candidate_max_area=self.outer_candidate_max_area,
            mask_expand_ratio=self.outer_mask_expand_ratio,
            mask_profiles=self.outer_mask_profiles,
            min_width_ratio=self.outer_min_width_ratio,
            min_height_ratio=self.outer_min_height_ratio,
            min_width_px=self.outer_min_width_px,
            min_height_px=self.outer_min_height_px,
            bw_not_white_threshold=self.outer_bw_not_white_threshold,
            bw_dark_threshold=self.outer_bw_dark_threshold,
            bw_min_fraction=self.outer_bw_min_fraction,
            bw_min_width_ratio=self.outer_bw_min_width_ratio,
            bw_min_height_ratio=self.outer_bw_min_height_ratio,
            bw_margin_ratio=self.outer_bw_margin_ratio,
            bw_margin_min=self.outer_bw_margin_min,
            white_border_ratio=self.outer_white_border_ratio,
            white_run_ratio=self.outer_white_run_ratio,
            white_run_min=self.outer_white_run_min,
            white_run_max=self.outer_white_run_max,
            white_dark_threshold=self.outer_white_dark_threshold,
            white_light_threshold=self.outer_white_light_threshold,
            white_min_width_ratio=self.outer_white_min_width_ratio,
            white_min_height_ratio=self.outer_white_min_height_ratio,
            white_margin_ratio=self.outer_white_margin_ratio,
            white_margin_min=self.outer_white_margin_min,
        )

    @property
    def separator_outer_band(self) -> SeparatorOuterBandParameters:
        return SeparatorOuterBandParameters(
            min_score=self.separator_first_outer_min_score,
            band_score=self.separator_first_outer_band_score,
            min_width_ratio=self.separator_first_outer_min_width_ratio,
            max_width_ratio=self.separator_first_outer_max_width_ratio,
            spacing_min_ratio=self.separator_first_outer_spacing_min_ratio,
            spacing_max_ratio=self.separator_first_outer_spacing_max_ratio,
            frame_error_max=self.separator_first_outer_frame_error_max,
            edge_margin_ratio=self.separator_first_outer_edge_margin_ratio,
            source_candidate_count=self.separator_first_outer_source_candidates,
            band_candidate_count=self.separator_first_outer_band_candidates,
            pair_candidate_count=self.separator_first_outer_pair_candidates,
            max_candidates=self.separator_first_outer_max_candidates,
        )

    @property
    def separator_geometry_outer(self) -> SeparatorGeometryOuterParameters:
        return SeparatorGeometryOuterParameters(
            required_count=self.separator_geometry_outer_count,
            source_candidate_count=self.separator_geometry_outer_source_candidates,
            margin_ratios=self.separator_geometry_outer_margin_ratios,
            max_candidates=self.separator_geometry_outer_max_candidates,
        )

    @property
    def short_axis_aspect_retry(self) -> ShortAxisAspectRetryParameters:
        return ShortAxisAspectRetryParameters(
            enabled=self.short_axis_aspect_retry_enabled,
            min_error=self.short_axis_aspect_retry_min_error,
            target_aspect=self.short_axis_aspect_retry_target_aspect,
            margin_ratio=self.short_axis_aspect_retry_margin_ratio,
            margin_min=self.short_axis_aspect_retry_margin_min,
            margin_max=self.short_axis_aspect_retry_margin_max,
        )

    @property
    def format_geometry_retry(self) -> FormatGeometryRetryParameters:
        return FormatGeometryRetryParameters(
            enabled=self.format_geometry_outer_retry_enabled,
            ratio_tolerance=self.format_geometry_outer_retry_ratio_tolerance,
            min_shrink_ratio=self.format_geometry_outer_retry_min_shrink_ratio,
            max_shrink_ratio=self.format_geometry_outer_retry_max_shrink_ratio,
            content_margin_ratio=self.format_geometry_outer_retry_content_margin_ratio,
            content_margin_min=self.format_geometry_outer_retry_content_margin_min,
            content_margin_max=self.format_geometry_outer_retry_content_margin_max,
        )

    @property
    def grid_outer_refine(self) -> GridOuterRefineParameters:
        return GridOuterRefineParameters(
            shift_ratio=self.grid_outer_refine_shift_ratio,
            shift_min=self.grid_outer_refine_shift_min,
            shift_max=self.grid_outer_refine_shift_max,
            max_width_change=self.grid_outer_refine_max_width_change,
        )

    @property
    def outer_content_alignment(self) -> OuterContentAlignmentParameters:
        return OuterContentAlignmentParameters(
            white_edge_long_ratio=self.outer_align_white_edge_long_ratio,
            white_edge_long_min=self.outer_align_white_edge_long_min,
            white_edge_long_max=self.outer_align_white_edge_long_max,
            long_gate_ratio=self.outer_align_long_gate_ratio,
            long_gate_min=self.outer_align_long_gate_min,
            long_gate_max=self.outer_align_long_gate_max,
            short_gate_ratio=self.outer_align_short_gate_ratio,
            short_gate_min=self.outer_align_short_gate_min,
            short_gate_max=self.outer_align_short_gate_max,
            long_excess_ratio=self.outer_align_long_excess_ratio,
            long_gate_excess_ratio=self.outer_align_long_gate_excess_ratio,
            short_excess_ratio=self.outer_align_short_excess_ratio,
            short_requires_hard_anchors=self.outer_align_short_requires_hard_anchors,
            short_content_height_max=self.outer_align_short_content_height_max,
            content_width_min=self.outer_align_content_width_min,
            edge_short_ratio=self.outer_align_edge_short_ratio,
            edge_dark_max=self.outer_align_edge_dark_max,
            border_band_ratio=self.outer_align_border_band_ratio,
            margin_x_ratio=self.outer_align_margin_x_ratio,
            margin_x_min=self.outer_align_margin_x_min,
            margin_x_max=self.outer_align_margin_x_max,
            margin_y_ratio=self.outer_align_margin_y_ratio,
            margin_y_min=self.outer_align_margin_y_min,
            margin_y_max=self.outer_align_margin_y_max,
            long_margin_ratio=self.outer_align_long_margin_ratio,
            long_margin_cap_ratio=self.outer_align_long_margin_cap_ratio,
            long_margin_cap_min=self.outer_align_long_margin_cap_min,
            long_margin_cap_max=self.outer_align_long_margin_cap_max,
            short_margin_ratio=self.outer_align_short_margin_ratio,
            short_margin_cap_ratio=self.outer_align_short_margin_cap_ratio,
            short_margin_cap_min=self.outer_align_short_margin_cap_min,
            short_margin_cap_max=self.outer_align_short_margin_cap_max,
        )

    @property
    def partial_holder(self) -> PartialHolderParameters:
        return PartialHolderParameters(
            enabled=self.partial_safe_extra_frames_enabled,
            min_count_35mm=self.partial_safe_extra_frames_min_count_35mm,
            min_count_small=self.partial_safe_extra_frames_min_count_small,
            min_hard_gaps=self.partial_safe_extra_frames_min_hard_gaps,
            min_hard_ratio=self.partial_safe_extra_frames_min_hard_ratio,
            max_equal_gaps=self.partial_safe_extra_frames_max_equal_gaps,
            max_width_cv=self.partial_safe_extra_frames_max_width_cv,
            min_joint_score=self.partial_safe_extra_frames_min_joint_score,
            min_content_score=self.partial_safe_extra_frames_min_content_score,
            min_geometry_score=self.partial_safe_extra_frames_min_geometry_score,
            min_wide_like_gaps=self.partial_safe_extra_frames_min_wide_like_gaps,
            wide_like_min_width_ratio=self.partial_safe_extra_frames_wide_like_min_width_ratio,
            leading_content_check=self.partial_safe_extra_frames_leading_content_check,
            leading_content_max_mean=self.partial_safe_extra_frames_leading_content_max_mean,
            leading_content_max_coverage=self.partial_safe_extra_frames_leading_content_max_coverage,
            leading_content_band_ratio=self.partial_safe_extra_frames_leading_content_band_ratio,
            frame_content_check=self.partial_safe_extra_frames_frame_content_check,
            min_frame_mean=self.partial_safe_extra_frames_min_frame_mean,
            min_frame_coverage=self.partial_safe_extra_frames_min_frame_coverage,
        )

    @property
    def scoring_calibration(self) -> ScoringCalibrationParameters:
        return ScoringCalibrationParameters(
            hard_full_confidence_floor=self.calibrate_hard_full_confidence_floor,
            geometry_weight=self.calibrate_geometry_weight,
            content_weight=self.calibrate_content_weight,
            separator_weight=self.calibrate_separator_weight,
            separator_source_bias=self.calibrate_separator_source_bias,
            no_auto_cap_partial=self.calibrate_partial_no_auto_cap,
            no_auto_cap_full=self.calibrate_full_no_auto_cap,
        )

    @property
    def base_detection_score(self) -> BaseDetectionScoreParameters:
        return BaseDetectionScoreParameters(
            width_cv_norm=self.score_width_cv_norm,
            gap_weight=self.score_gap_weight,
            width_weight=self.score_width_weight,
            outer_weight=self.score_outer_weight,
            contrast_weight=self.score_contrast_weight,
            outer_min_area=self.score_outer_min_area,
            outer_max_area=self.score_outer_max_area,
            outer_too_large=self.score_outer_too_large,
            outer_uncertain_confidence=self.score_outer_uncertain_confidence,
            contrast_min=self.score_contrast_min,
            contrast_floor=self.score_contrast_floor,
            full_width_cv=self.score_full_width_cv,
            geometry_floor_tight_cv=self.score_geometry_floor_tight_cv,
            geometry_floor_high=self.score_geometry_floor_high,
            geometry_floor_low=self.score_geometry_floor_low,
            unstable_width_cv=self.score_unstable_width_cv,
            full_outer_min_area=self.score_full_outer_min_area,
            low_confidence_floor=self.score_low_confidence_floor,
            partial_one_cap=self.score_partial_one_cap,
            partial_two_35mm_cap=self.score_partial_two_35mm_cap,
            partial_general_cap=self.score_partial_general_cap,
            outer_too_large_cap=self.score_outer_too_large_cap,
        )

    @property
    def separator_support_score(self) -> SeparatorSupportScoreParameters:
        return SeparatorSupportScoreParameters(
            model_grid_credit=self.separator_model_grid_credit,
            model_equal_credit=self.separator_model_equal_credit,
            hard_weight=self.separator_support_hard_weight,
            model_weight=self.separator_support_model_weight,
            no_expected_confidence_threshold=self.score_low_confidence_floor,
            no_expected_confidence_cap=0.75,
        )

    @property
    def geometry_support_score(self) -> GeometrySupportScoreParameters:
        return GeometrySupportScoreParameters(
            width_cv_norm=self.geometry_width_cv_norm,
            outer_min_area=self.score_outer_min_area,
            outer_max_area=self.score_outer_too_large,
            outer_uncertain_score=self.geometry_support_outer_uncertain,
            aspect_norm=self.content_support_aspect_norm,
            no_aspect_score=self.geometry_support_no_aspect_score,
            width_weight=self.geometry_support_width_weight,
            outer_weight=self.geometry_support_outer_weight,
            aspect_weight=self.geometry_support_aspect_weight,
            count_weight=self.geometry_support_count_weight,
        )

    @property
    def enhanced_separator(self) -> EnhancedSeparatorParameters:
        return EnhancedSeparatorParameters(
            max_width_ratio=self.enhanced_max_width_ratio,
            max_width_min=self.enhanced_max_width_min,
            max_width_max=self.enhanced_max_width_max,
            max_shift_ratio=self.enhanced_shift_ratio,
            max_shift_min=self.enhanced_shift_min,
            max_shift_max=self.enhanced_shift_max,
            auto_low_score=self.enhanced_auto_low_score,
        )

    @property
    def separator_profile(self) -> SeparatorProfileParameters:
        return SeparatorProfileParameters(
            top_ratio=self.separator_profile_top_ratio,
            bottom_ratio=self.separator_profile_bottom_ratio,
            segments=self.separator_profile_segments,
            dark_threshold=self.separator_profile_dark_threshold,
            light_threshold=self.separator_profile_light_threshold,
            consistency_percentile=self.separator_profile_consistency_percentile,
            average_weight=self.separator_profile_average_weight,
            consistency_weight=self.separator_profile_consistency_weight,
            std_norm=self.separator_profile_std_norm,
            dark_soft_mean=self.separator_profile_dark_soft_mean,
            light_soft_mean=self.separator_profile_light_soft_mean,
            light_soft_span=self.separator_profile_light_soft_span,
            soft_weight=self.separator_profile_soft_weight,
            uniform_base=self.separator_profile_uniform_base,
            uniform_weight=self.separator_profile_uniform_weight,
            gradient_weight=self.separator_profile_gradient_weight,
            smooth_ratio=self.separator_profile_smooth_ratio,
            smooth_min=self.separator_profile_smooth_min,
        )

    @property
    def edge_refine_profile(self) -> EdgeRefineProfileParameters:
        return EdgeRefineProfileParameters(
            top_ratio=self.edge_refine_top_ratio,
            bottom_ratio=self.edge_refine_bottom_ratio,
            mean_weight=self.edge_refine_mean_weight,
            p75_weight=self.edge_refine_p75_weight,
            smooth_ratio=self.edge_refine_smooth_ratio,
            smooth_min=self.edge_refine_smooth_min,
            high_percentile=self.edge_refine_high_percentile,
            background_dark_threshold=self.edge_refine_background_dark_threshold,
            background_light_threshold=self.edge_refine_background_light_threshold,
            y_edge_weight=self.edge_refine_y_edge_weight,
            activity_percentile=self.edge_refine_activity_percentile,
        )

    @property
    def candidate_competition(self) -> CandidateCompetitionParameters:
        return CandidateCompetitionParameters(
            top_n=self.candidate_competition_top_n,
            close_margin=self.candidate_competition_close_margin,
            confidence_cap=self.candidate_competition_confidence_cap,
        )

    @property
    def postprocess(self) -> PostprocessParameters:
        return PostprocessParameters(
            retry_uncertain_outer=self.outer_retry_enabled,
            content_aspect_conflict_cap=self.post_content_aspect_conflict_cap,
            content_low_confidence_cap=self.post_content_low_confidence_cap,
            outer_mismatch_cap=self.post_outer_mismatch_cap,
            lucky_pass_risk_cap=self.post_lucky_pass_risk_cap,
        )

    @property
    def approved_geometry_adjustment(self) -> ApprovedGeometryAdjustmentParameters:
        return ApprovedGeometryAdjustmentParameters(
            long_limit_ratio=self.approved_adjust_long_limit_ratio,
            long_limit_min=self.approved_adjust_long_limit_min,
            long_limit_max=self.approved_adjust_long_limit_max,
            min_ext_ratio=self.approved_adjust_min_ext_ratio,
            min_ext_min=self.approved_adjust_min_ext_min,
            min_ext_max=self.approved_adjust_min_ext_max,
        )

    @property
    def debug_gap_overlay(self) -> DebugGapOverlayParameters:
        return DebugGapOverlayParameters(
            overlap_tolerance_ratio=self.debug_gap_overlap_tolerance_ratio,
            overlap_tolerance_min=self.debug_gap_overlap_tolerance_min,
            overlap_tolerance_max=self.debug_gap_overlap_tolerance_max,
            tick_length_ratio=self.debug_gap_tick_length_ratio,
            tick_length_min=self.debug_gap_tick_length_min,
            hard_line_width=self.debug_gap_hard_line_width,
            model_line_width=self.debug_gap_model_line_width,
            diagnostic_line_width=self.debug_gap_diagnostic_line_width,
        )

    @property
    def nearby_separator_diagnostics(self) -> NearbySeparatorDiagnosticsParameters:
        return NearbySeparatorDiagnosticsParameters(
            window_ratio=self.nearby_window_ratio,
            window_min=self.nearby_window_min,
            window_max=self.nearby_window_max,
            exclude_ratio=self.nearby_exclude_ratio,
            exclude_min=self.nearby_exclude_min,
            exclude_max=self.nearby_exclude_max,
            max_width_ratio=self.nearby_max_width_ratio,
            max_width_min=self.nearby_max_width_min,
            max_width_max=self.nearby_max_width_max,
            detail_score_add=self.nearby_detail_score_add,
            detail_score_multiplier=self.nearby_detail_score_multiplier,
        )

    @property
    def nearby_separator_correction(self) -> NearbySeparatorCorrectionParameters:
        return NearbySeparatorCorrectionParameters(
            enabled=self.nearby_active_correction,
            window_ratio=self.nearby_window_ratio,
            window_min=self.nearby_window_min,
            window_max=self.nearby_window_max,
            exclude_ratio=self.nearby_exclude_ratio,
            exclude_min=self.nearby_exclude_min,
            exclude_max=self.nearby_exclude_max,
            max_width_ratio=self.nearby_max_width_ratio,
            max_width_min=self.nearby_max_width_min,
            max_width_max=self.nearby_max_width_max,
            distance_ratio=self.nearby_distance_ratio,
            score_add=self.nearby_score_add,
            score_multiplier=self.nearby_score_multiplier,
            local_gain_ratio=self.nearby_local_gain_ratio,
            local_gain_min=self.nearby_local_gain_min,
            local_gain_max=self.nearby_local_gain_max,
        )

    @property
    def robust_grid(self) -> RobustGridParameters:
        return RobustGridParameters(
            constrain_full_shift_ratio=self.constrain_full_shift_ratio,
            constrain_partial_shift_ratio=self.constrain_partial_shift_ratio,
            constrain_shift_min=self.constrain_shift_min,
            constrain_shift_max=self.constrain_shift_max,
            reliable_min_score=self.robust_reliable_min_score,
            min_reliable=self.robust_min_reliable,
            pitch_min_ratio=self.robust_pitch_min_ratio,
            pitch_max_ratio=self.robust_pitch_max_ratio,
            full_tolerance_ratio=self.robust_full_tolerance_ratio,
            partial_tolerance_ratio=self.robust_partial_tolerance_ratio,
            tolerance_min=self.robust_tolerance_min,
            tolerance_max=self.robust_tolerance_max,
            reject_residual_ratio=self.robust_reject_residual_ratio,
            full_shift_ratio=self.robust_full_shift_ratio,
            partial_shift_ratio=self.robust_partial_shift_ratio,
            shift_min=self.robust_shift_min,
            shift_max=self.robust_shift_max,
            hard_keep_ratio=self.robust_hard_keep_ratio,
            hard_keep_min=self.robust_hard_keep_min,
            hard_keep_max=self.robust_hard_keep_max,
            hard_protect_ratio=self.robust_hard_protect_ratio,
            hard_protect_min=self.robust_hard_protect_min,
            hard_protect_max=self.robust_hard_protect_max,
        )

    @property
    def gap_search(self) -> GapSearchParameters:
        return GapSearchParameters(
            radius_ratio=self.gap_radius_ratio,
            radius_min=self.gap_radius_min,
            radius_max=self.gap_radius_max,
            max_width_ratio=self.gap_max_width_ratio,
            max_width_min=self.gap_max_width_min,
            max_width_max=self.gap_max_width_max,
            min_width_ratio=self.gap_min_width_ratio,
            min_width_min=self.gap_min_width_min,
            min_width_max=self.gap_min_width_max,
            guard_ratio=self.gap_guard_ratio,
            guard_min=self.gap_guard_min,
            guard_max=self.gap_guard_max,
            min_score=self.gap_min_score,
            peak_multiplier=self.gap_peak_multiplier,
            band_multiplier=self.gap_band_multiplier,
            wide_min_mean=self.wide_gap_min_mean,
            wide_min_prominence=self.wide_gap_min_prominence,
        )

    @property
    def diagnostic_overlap_risk(self) -> DiagnosticOverlapRiskParameters:
        return DiagnosticOverlapRiskParameters(
            mean_min=self.diagnostic_overlap_mean_min,
            weak_continuity=self.diagnostic_overlap_weak_continuity,
            weak_activity=self.diagnostic_overlap_weak_activity,
            medium_continuity=self.diagnostic_overlap_medium_continuity,
            medium_activity=self.diagnostic_overlap_medium_activity,
            strong_continuity=self.diagnostic_overlap_strong_continuity,
            strong_activity=self.diagnostic_overlap_strong_activity,
        )

    @property
    def hard_gap_trust(self) -> HardGapTrustParameters:
        return HardGapTrustParameters(
            guard_ratio=self.hard_trust_guard_ratio,
            guard_min=self.hard_trust_guard_min,
            guard_max=self.hard_trust_guard_max,
            narrow_ratio=self.hard_trust_narrow_ratio,
            narrow_min=self.hard_trust_narrow_min,
            narrow_max=self.hard_trust_narrow_max,
            model_delta_ratio=self.hard_trust_model_delta_ratio,
            geometry_width_ratio=self.hard_trust_geometry_width_ratio,
            strong_min_score=self.hard_trust_strong_min_score,
            strong_width_min=self.hard_trust_strong_width_min,
            strong_width_max=self.hard_trust_strong_width_max,
            narrow_ok_score=self.hard_trust_narrow_ok_score,
            narrow_ok_width_min=self.hard_trust_narrow_ok_width_min,
            narrow_ok_width_max=self.hard_trust_narrow_ok_width_max,
            model_conflict_score=self.hard_trust_model_conflict_score,
            core_content_threshold=self.hard_trust_core_content_threshold,
            core_dark_threshold=self.hard_trust_core_dark_threshold,
            dark_mean_max=self.hard_trust_dark_mean_max,
            dark_fraction_min=self.hard_trust_dark_fraction_min,
            dark_activity_max=self.hard_trust_dark_activity_max,
            strong_core_content_max=self.hard_trust_strong_core_content_max,
            weak_mean_min=self.hard_trust_weak_mean_min,
            weak_content_min=self.hard_trust_weak_content_min,
            frame_border_width_ratio=self.hard_trust_frame_border_width_ratio,
            continuity_min=self.hard_trust_continuity_min,
            activity_min=self.hard_trust_activity_min,
        )

    @property
    def lucky_pass_risk(self) -> LuckyPassRiskParameters:
        return LuckyPassRiskParameters(
            enabled=self.lucky_pass_risk_enabled,
            model_gap_support_min=self.lucky_model_gap_support_min,
            model_gap_support_weight=self.lucky_model_gap_support_weight,
            minor_model_gap_support_weight=self.lucky_minor_model_gap_support_weight,
            limited_strong_hard_max=self.lucky_limited_strong_hard_max,
            limited_strong_hard_weight=self.lucky_limited_strong_hard_weight,
            very_limited_strong_hard_max=self.lucky_very_limited_strong_hard_max,
            very_limited_strong_hard_weight=self.lucky_very_limited_strong_hard_weight,
            suspicious_hard_weight=self.lucky_suspicious_hard_weight,
            strong_overlap_weight=self.lucky_strong_overlap_weight,
            combo_weight=self.lucky_combo_weight,
            unstable_width_cv=self.lucky_unstable_width_cv,
            unstable_width_weight=self.lucky_unstable_width_weight,
            mild_width_cv=self.lucky_mild_width_cv,
            mild_width_weight=self.lucky_mild_width_weight,
            strong_hard_credit_min=self.lucky_strong_hard_credit_min,
            strong_hard_credit=self.lucky_strong_hard_credit,
            stable_width_cv=self.lucky_stable_width_cv,
            stable_model_gap_min=self.lucky_stable_model_gap_min,
            stable_geometry_credit=self.lucky_stable_geometry_credit,
            risk_threshold=self.lucky_risk_threshold,
        )


def base_medium_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    params: dict[str, Any] = {
        "score_full_width_cv": 0.012,
        "content_profile_min_run_ratio": 0.18,
        "separator_model_grid_credit": 0.18,
        "separator_model_equal_credit": 0.04,
        "separator_gate_profile": "all_internal_gaps_hard",
        "nearby_score_multiplier": 1.28,
        "calibrate_separator_weight": 0.36,
        "calibrate_geometry_weight": 0.32,
        "calibrate_content_weight": 0.32,
        "wide_gap_retry_enabled": False,
        "nearby_active_correction": False,
        "lucky_pass_risk_enabled": False,
        "leading_grid_failure_enabled": False,
    }
    params.update(overrides)
    return FormatParameters(format_name, **params)


def format_parameters(format_name: str) -> FormatParameters:
    if format_name not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format parameters: {format_name}")
    module = import_module(f"{__package__}.format_{format_name.replace('-', '_')}")
    return module.parameters()
