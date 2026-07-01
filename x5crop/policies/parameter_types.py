from __future__ import annotations

from dataclasses import dataclass
from typing import Optional



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
class FinalizationParameters:
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

__all__ = [
    "EdgePairParams",
    "OuterMaskProfile",
    "PartialCountParameters",
    "PartialEdgeHintParameters",
    "SeparatorGateParameters",
    "LeadingGridFailureParameters",
    "SeparatorGeometrySupportParameters",
    "WideRetryParameters",
    "ContentEvidenceParameters",
    "ContentProfileParameters",
    "ContentMaskParameters",
    "ContentCandidateParameters",
    "ContentSupportParameters",
    "OuterStrategyParameters",
    "ContentFloatingOuterParameters",
    "EdgeAnchorOuterParameters",
    "BaseOuterCandidateParameters",
    "SeparatorOuterBandParameters",
    "SeparatorGeometryOuterParameters",
    "FormatGeometryRetryParameters",
    "GridOuterRefineParameters",
    "ShortAxisAspectRetryParameters",
    "OuterContentAlignmentParameters",
    "PartialHolderParameters",
    "ScoringCalibrationParameters",
    "BaseDetectionScoreParameters",
    "SeparatorSupportScoreParameters",
    "GeometrySupportScoreParameters",
    "CandidateCompetitionParameters",
    "FinalizationParameters",
    "ApprovedGeometryAdjustmentParameters",
    "DebugGapOverlayParameters",
    "NearbySeparatorDiagnosticsParameters",
    "NearbySeparatorCorrectionParameters",
    "RobustGridParameters",
    "GapSearchParameters",
    "EnhancedSeparatorParameters",
    "SeparatorProfileParameters",
    "EdgeRefineProfileParameters",
    "DiagnosticOverlapRiskParameters",
    "HardGapTrustParameters",
    "LuckyPassRiskParameters",
]
