from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .ids import REPORT_SCHEMA_VERSION

if TYPE_CHECKING:
    from ..formats import FormatSpec
    from .parameters import FormatParameters


FULL = "full"
PARTIAL = "partial"


@dataclass(frozen=True)
class DualLanePolicy:
    lane_count: int = 2
    lane_format: str = "135"
    unsupported_partial_reason: str = "parallel_lane_partial_not_supported"


@dataclass(frozen=True)
class FrameFitPolicy:
    name: str
    edge_evidence: bool
    geometry_fallback: bool
    min_edge_samples: int = 2
    nominal_min_ratio: float = 0.72
    nominal_max_ratio: float = 1.10
    inlier_tolerance_ratio: float = 0.035
    min_inlier_tolerance_px: float = 3.0
    geometry_pitch_min_ratio: float = 0.85
    geometry_pitch_max_ratio: float = 1.15
    geometry_noop_width_cv: float = 0.006
    geometry_outer_tolerance_ratio: float = 0.0
    geometry_outer_tolerance_min: float = 1.0
    geometry_outer_tolerance_max: float = 1.0
    edge_candidate_weight_with_edges: float = 0.18
    edge_candidate_weight_without_edges: float = 1.0
    edge_adjust_tolerance_ratio: float = 0.0
    edge_adjust_tolerance_min: float = 1.0
    edge_adjust_tolerance_max: float = 1.0


@dataclass(frozen=True)
class DetectorPolicy:
    kind: str = "standard_strip"
    dual_lane: DualLanePolicy = field(default_factory=DualLanePolicy)


@dataclass(frozen=True)
class CountPolicy:
    """Frame-count and partial-offset policy for one format/mode pair."""

    fixed_count: int | None
    auto_counts: tuple[int, ...]
    partial_offsets: tuple[float, ...] = (0.0,)
    include_default_in_partial_auto: bool = False

    def count_specs(
        self,
        fmt: FormatSpec,
        strip_mode: str,
        requested_count: int,
        count_override: int | None,
    ) -> list[tuple[int, str, tuple[float, ...]]]:
        if strip_mode == FULL:
            count = requested_count if self.fixed_count is None else self.fixed_count
            return [(count, FULL, (0.0,))]
        if strip_mode != PARTIAL:
            raise ValueError(f"Unsupported strip mode: {strip_mode}")
        if count_override is not None:
            return [(requested_count, PARTIAL, self.partial_offsets)]
        counts = [
            count
            for count in self.auto_counts
            if count < fmt.default_count or self.include_default_in_partial_auto
        ]
        return [(count, PARTIAL, self.partial_offsets) for count in counts] or [
            (1, PARTIAL, self.partial_offsets)
        ]


@dataclass(frozen=True)
class ShortAxisAspectRetryPolicy:
    enabled: bool = False
    min_error: float = 0.24
    target_aspect: float = 1.0
    margin_ratio: float = 0.008
    margin_min: int = 12
    margin_max: int = 80


@dataclass(frozen=True)
class FormatGeometryRetryPolicy:
    enabled: bool = True
    ratio_tolerance: float = 0.025
    min_shrink_ratio: float = 0.003
    max_shrink_ratio: float = 0.120
    content_margin_ratio: float = 0.010
    content_margin_min: int = 12
    content_margin_max: int = 80


@dataclass(frozen=True)
class GridOuterRefinePolicy:
    shift_ratio: float = 0.080
    shift_min: int = 8
    shift_max: int = 420
    max_width_change: float = 0.12


@dataclass(frozen=True)
class OuterContentAlignmentPolicy:
    white_edge_long_ratio: float = 0.0190
    white_edge_long_min: int = 90
    white_edge_long_max: int = 180
    long_gate_ratio: float = 0.0340
    long_gate_min: int = 160
    long_gate_max: int = 320
    short_gate_ratio: float = 0.0060
    short_gate_min: int = 28
    short_gate_max: int = 80
    long_excess_ratio: float = 0.050
    long_gate_excess_ratio: float = 0.035
    short_excess_ratio: float = 0.035
    short_requires_hard_anchors: bool = False
    short_content_height_max: float = 1.0
    content_width_min: float = 0.985
    edge_short_ratio: float = 0.015
    edge_dark_max: float = 0.02
    border_band_ratio: float = 0.018
    margin_x_ratio: float = 0.0030
    margin_x_min: int = 15
    margin_x_max: int = 30
    margin_y_ratio: float = 0.0030
    margin_y_min: int = 10
    margin_y_max: int = 20
    long_margin_ratio: float = 0.012
    long_margin_cap_ratio: float = 0.0170
    long_margin_cap_min: int = 80
    long_margin_cap_max: int = 160
    short_margin_ratio: float = 0.010
    short_margin_cap_ratio: float = 0.010
    short_margin_cap_min: int = 40
    short_margin_cap_max: int = 80


@dataclass(frozen=True)
class ContentFloatingOuterPolicy:
    enabled: bool = False
    ratio_extras: tuple[float, ...] = (0.06, 0.10)
    content_threshold: int = 225
    content_margin_ratio: float = 0.012
    content_margin_min: int = 12
    content_margin_max: int = 80
    min_width_ratio: float = 0.30
    max_candidates: int = 12


@dataclass(frozen=True)
class EdgeAnchorOuterPolicy:
    mode: str = "off"
    partial_center_ratio: float = 0.35
    ratio_extras: tuple[float, ...] = (0.06, 0.10)
    content_threshold: int = 225
    content_margin_ratio: float = 0.012
    content_margin_min: int = 12
    content_margin_max: int = 80
    min_width_ratio: float = 0.30
    max_candidates: int = 8


@dataclass(frozen=True)
class OuterMaskProfilePolicy:
    name: str
    low: int | None
    high: int | None
    min_row_fraction: float = 0.012
    min_col_fraction: float = 0.012


@dataclass(frozen=True)
class OuterCandidateDetectionPolicy:
    white_x_width_multiplier: float = 1.80
    white_x_extra_ratio: float = 0.060
    candidate_max_area: float = 0.94
    mask_expand_ratio: float = 0.002
    mask_profiles: tuple[OuterMaskProfilePolicy, ...] = (
        OuterMaskProfilePolicy("mask_not_white_246", None, 246),
        OuterMaskProfilePolicy("mask_not_white_225", None, 225),
        OuterMaskProfilePolicy("mask_mid_8_246", 8, 246),
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
class SeparatorOuterBandPolicy:
    min_score: float = 0.58
    band_score: float = 0.36
    min_width_ratio: float = 0.006
    max_width_ratio: float = 0.120
    spacing_min_ratio: float = 0.82
    spacing_max_ratio: float = 1.24
    frame_error_max: float = 0.18
    edge_margin_ratio: float = 0.18
    source_candidate_count: int = 2
    band_candidate_count: int = 10
    pair_candidate_count: int = 4
    max_candidates: int = 12


@dataclass(frozen=True)
class SeparatorGeometryOuterPolicy:
    required_count: int = 0
    source_candidate_count: int = 3
    margin_ratios: tuple[float, ...] = (0.00, 0.018, 0.035)
    max_candidates: int = 8


@dataclass(frozen=True)
class OuterPolicy:
    base_outer: bool = True
    content_floating: bool = False
    edge_anchor: str = "off"
    separator_first: str = "off"
    separator_geometry: str = "off"
    separator_outer_allow_oversized_band: bool = False
    separator_outer_oversized_band_max_ratio: float = 0.45
    separator_outer_oversized_band_score_penalty: float = 0.08
    separator_gap_search_max_width_ratio: float = 0.095
    dark_band: str = "off"
    dark_band_outer: "DarkBandOuterPolicy" = field(default_factory=lambda: DarkBandOuterPolicy())
    format_geometry_retry: FormatGeometryRetryPolicy = field(default_factory=FormatGeometryRetryPolicy)
    grid_refine: GridOuterRefinePolicy = field(default_factory=GridOuterRefinePolicy)
    short_axis_aspect_retry: ShortAxisAspectRetryPolicy = field(default_factory=ShortAxisAspectRetryPolicy)
    content_alignment: OuterContentAlignmentPolicy = field(default_factory=OuterContentAlignmentPolicy)
    content_floating_outer: ContentFloatingOuterPolicy = field(default_factory=ContentFloatingOuterPolicy)
    edge_anchor_outer: EdgeAnchorOuterPolicy = field(default_factory=EdgeAnchorOuterPolicy)
    base_candidates: OuterCandidateDetectionPolicy = field(default_factory=OuterCandidateDetectionPolicy)
    separator_outer_band: SeparatorOuterBandPolicy = field(default_factory=SeparatorOuterBandPolicy)
    separator_geometry_outer: SeparatorGeometryOuterPolicy = field(default_factory=SeparatorGeometryOuterPolicy)
    retries: tuple[str, ...] = ()


@dataclass(frozen=True)
class DarkBandOuterPolicy:
    mode: str = "off"
    required_count: int = 3
    threshold_ratio: float = 0.42
    threshold_span_ratio: float = 0.12
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
    spacing_min_ratio: float = 0.82
    spacing_max_ratio: float = 1.18
    sequence_score_weight: float = 0.04
    source_candidate_count: int = 2
    band_candidate_count: int = 10
    sequence_candidate_count: int = 4
    max_candidates: int = 4
    full_selection_enabled: bool = False
    full_selection_strip_modes: tuple[str, ...] = ("full",)
    full_selection_requires_required_count: bool = True
    full_selection_requires_help: bool = True
    full_selection_required_support: str = "ok"
    full_selection_allow_equal_gaps: bool = False
    full_selection_help_supports: tuple[str, ...] = ("aspect_conflict", "low_content")
    full_selection_help_reasons: tuple[str, ...] = (
        "content_aspect_conflict",
        "separator_hard_evidence_weak",
    )


@dataclass(frozen=True)
class SeparatorGatePolicy:
    """Separator auto-gate profile with explicit behavior parameters.

    Detection code reads this semantic surface instead of branching on format names.
    """

    profile: str
    needed_hard_max: int = 2
    max_equal_gaps_floor: int = 2
    allow_geometry_support: bool = False
    hard_required_all_gaps: bool = True
    edge_pair_min_score_without_wide: float = 0.0
    edge_pair_min_score_with_wide: float = 0.0
    min_wide_gaps_for_auto: int = 0
    score_min_hard_gaps: int = 2
    score_max_equal_gaps_floor: int = 2
    low_hard_confidence_cap: float = 0.82
    mostly_equal_confidence_cap: float = 0.84
    allow_full_detected_geometry: bool = True
    leading_grid_failure: "LeadingGridFailurePolicy" = field(default_factory=lambda: LeadingGridFailurePolicy())


@dataclass(frozen=True)
class LeadingGridFailurePolicy:
    enabled: bool = True
    min_expected_gaps: int = 5
    leading_count: int = 3
    low_score: float = 0.35
    very_low_score: float = 0.12
    very_low_count: int = 2
    max_hard_gaps: int = 2


@dataclass(frozen=True)
class SeparatorGeometrySupportModePolicy:
    enabled: bool = False
    min_hard_ratio: float = 0.0
    min_joint_score: float = 1.0
    allow_grid: bool = True
    max_equal_gaps: int = 0
    max_width_cv: float = 0.040
    required_content_support: str = "ok"
    max_outer_area_ratio: float = 0.995


@dataclass(frozen=True)
class SeparatorGeometrySupportPolicy:
    wide_geometry: SeparatorGeometrySupportModePolicy = field(default_factory=SeparatorGeometrySupportModePolicy)
    stable_grid: SeparatorGeometrySupportModePolicy = field(default_factory=SeparatorGeometrySupportModePolicy)

    def mode_policy(self, mode: str) -> SeparatorGeometrySupportModePolicy:
        if mode == "wide_geometry":
            return self.wide_geometry
        if mode == "stable_grid":
            return self.stable_grid
        return SeparatorGeometrySupportModePolicy()


@dataclass(frozen=True)
class SeparatorEdgePairPolicy:
    window_ratio: float = 0.070
    min_gutter_ratio: float = 0.003
    max_gutter_ratio: float = 0.040
    min_strength: float = 0.45
    min_background: float = 0.64
    min_quality_for_model_gap: float = 1.05
    min_quality_for_hard_gap: float = 0.70
    hard_gap_quality_ratio: float = 0.95
    max_hard_shift_ratio: float = 0.040


@dataclass(frozen=True)
class HardGapTrustPolicy:
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


@dataclass(frozen=True)
class NearbySeparatorCorrectionPolicy:
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
class RobustGridPolicy:
    constrain_full_shift_ratio: float = 0.045
    constrain_partial_shift_ratio: float = 0.12
    constrain_shift_min: float = 20.0
    constrain_shift_max: float = 520.0
    reliable_min_score: float = 0.28
    min_reliable: int = 2
    pitch_min_ratio: float = 0.70
    pitch_max_ratio: float = 1.30
    full_tolerance_ratio: float = 0.040
    partial_tolerance_ratio: float = 0.090
    tolerance_min: float = 4.0
    tolerance_max: float = 520.0
    reject_residual_ratio: float = 0.045
    full_shift_ratio: float = 0.035
    partial_shift_ratio: float = 0.10
    shift_min: float = 20.0
    shift_max: float = 520.0
    hard_keep_ratio: float = 0.025
    hard_keep_min: float = 3.0
    hard_keep_max: float = 180.0
    hard_protect_ratio: float = 0.006
    hard_protect_min: float = 12.0
    hard_protect_max: float = 40.0


@dataclass(frozen=True)
class GapSearchPolicy:
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
    wide_min_mean: float = 0.95
    wide_min_prominence: float = 0.02


@dataclass(frozen=True)
class EnhancedSeparatorPolicy:
    min_score: float = 0.34
    max_width_ratio: float = 0.040
    max_width_min: float = 3.0
    max_width_max: float = 420.0
    max_shift_ratio: float = 0.035
    max_shift_min: float = 4.0
    max_shift_max: float = 420.0
    auto_low_score: float = 0.34


@dataclass(frozen=True)
class SeparatorProfilePolicy:
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
class EdgeRefineProfilePolicy:
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
class SeparatorPolicy:
    gate: SeparatorGatePolicy
    hard_required_all_gaps: bool
    wide_retry: bool
    wide_retry_max_width_ratio: float
    wide_separator_confidence_cap: float = 0.995
    geometry_support_modes: tuple[str, ...] = ()
    geometry_support: SeparatorGeometrySupportPolicy = field(default_factory=SeparatorGeometrySupportPolicy)
    edge_pair: SeparatorEdgePairPolicy = field(default_factory=SeparatorEdgePairPolicy)
    hard_gap_trust: HardGapTrustPolicy = field(default_factory=HardGapTrustPolicy)
    nearby_correction: NearbySeparatorCorrectionPolicy = field(default_factory=NearbySeparatorCorrectionPolicy)
    robust_grid: RobustGridPolicy = field(default_factory=RobustGridPolicy)
    gap_search: GapSearchPolicy = field(default_factory=GapSearchPolicy)
    enhanced: EnhancedSeparatorPolicy = field(default_factory=EnhancedSeparatorPolicy)
    profile: SeparatorProfilePolicy = field(default_factory=SeparatorProfilePolicy)
    edge_refine_profile: EdgeRefineProfilePolicy = field(default_factory=EdgeRefineProfilePolicy)
    hard_methods: tuple[str, ...] = ("detected", "edge_pair", "enhanced_detected", "wide_separator")
    model_methods: tuple[str, ...] = ("grid", "equal", "content")


@dataclass(frozen=True)
class ContentEvidencePolicy:
    percentile: float = 70.0
    threshold_multiplier: float = 0.70
    threshold_min: float = 0.08
    threshold_max: float = 0.45
    aspect_ok_max: float = 0.22
    present_mean_min: float = 0.075
    present_coverage_min: float = 0.18


@dataclass(frozen=True)
class ContentProfilePolicy:
    smooth_ratio: float = 0.010
    min_run_ratio: float = 0.20
    threshold_min: float = 0.035
    threshold_max: float = 0.40
    p35_weight: float = 0.38
    p65_multiplier: float = 0.82


@dataclass(frozen=True)
class ContentMaskPolicy:
    p55_weight: float = 0.34
    p75_multiplier: float = 0.78
    threshold_min: float = 0.045
    threshold_max: float = 0.45
    percentiles: tuple[float, float, float] = (55.0, 75.0, 92.0)
    bbox_min_fraction: float = 0.008
    outer_min_width_ratio: float = 0.08
    outer_min_height_ratio: float = 0.08
    outer_min_width_px: int = 60
    outer_min_height_px: int = 30
    outer_expand_ratio: float = 0.002


@dataclass(frozen=True)
class ContentCandidatePolicy:
    expected_width_min_px: float = 8.0
    coverage_weight: float = 0.38
    mean_weight: float = 0.30
    run_weight: float = 0.22
    aspect_weight: float = 0.10
    coverage_norm: float = 0.22
    mean_norm: float = 0.16
    aspect_norm: float = 0.18
    weak_coverage: float = 0.14
    aspect_uncertain: float = 0.18
    grid_fallback_cap: float = 0.82
    run_mismatch_cap: float = 0.84
    runs_incomplete_cap: float = 0.84
    weak_coverage_cap: float = 0.82
    aspect_uncertain_cap: float = 0.82


@dataclass(frozen=True)
class ContentPolicy:
    can_auto_pass_alone: bool
    required_support_for_auto: str = "ok"
    validates_candidates: bool = True
    evidence: ContentEvidencePolicy = field(default_factory=ContentEvidencePolicy)
    profile: ContentProfilePolicy = field(default_factory=ContentProfilePolicy)
    mask: ContentMaskPolicy = field(default_factory=ContentMaskPolicy)
    candidate: ContentCandidatePolicy = field(default_factory=ContentCandidatePolicy)
    support_coverage_norm: float = 0.22
    support_mean_norm: float = 0.16
    support_aspect_norm: float = 0.22
    support_coverage_weight: float = 0.42
    support_mean_weight: float = 0.40
    support_aspect_weight: float = 0.18
    support_gate_ok: float = 1.0
    support_gate_weak: float = 0.72
    support_gate_low_content: float = 0.58
    support_gate_aspect_conflict: float = 0.35
    support_gate_unknown: float = 0.50


@dataclass(frozen=True)
class GatePolicy:
    ordered_gates: tuple[str, ...]
    hard_review_reasons_block_auto: bool = True


@dataclass(frozen=True)
class PartialHolderPolicy:
    safe_extra_frames: bool = False
    safe_extra_frames_strip_modes: tuple[str, ...] = ("partial",)
    requires_wide_like_gaps: int = 0
    checks_leading_content: bool = False
    checks_frame_content: bool = False
    min_count_35mm: int = 2
    min_count_small: int = 2
    min_hard_gaps: int = 1
    min_hard_ratio: float = 0.15
    max_equal_gaps: int = 0
    max_width_cv: float = 0.055
    min_joint_score: float = 0.65
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    wide_like_min_width_ratio: float = 0.033
    leading_content_max_mean: float = 0.20
    leading_content_max_coverage: float = 0.34
    leading_content_band_ratio: float = 0.04
    min_frame_mean: float = 0.055
    min_frame_coverage: float = 0.10
    max_frame_aspect_error: float = 0.22


@dataclass(frozen=True)
class PartialEdgeHintPolicy:
    window_ratio: float = 0.18
    window_min: int = 8
    window_max: int = 900


@dataclass(frozen=True)
class GeometrySupportScorePolicy:
    width_cv_norm: float = 0.040
    outer_min_area: float = 0.35
    outer_max_area: float = 0.94
    outer_uncertain_score: float = 0.55
    aspect_norm: float = 0.22
    no_aspect_score: float = 0.80
    width_weight: float = 0.34
    outer_weight: float = 0.24
    aspect_weight: float = 0.26
    count_weight: float = 0.16


@dataclass(frozen=True)
class BaseDetectionScorePolicy:
    width_cv_norm: float = 0.030
    gap_weight: float = 0.40
    width_weight: float = 0.30
    outer_weight: float = 0.20
    contrast_weight: float = 0.10
    outer_min_area: float = 0.35
    outer_max_area: float = 0.995
    outer_too_large: float = 0.94
    outer_uncertain_confidence: float = 0.45
    contrast_min: float = 35.0
    contrast_floor: float = 0.35
    full_width_cv: float = 0.040
    geometry_floor_tight_cv: float = 0.006
    geometry_floor_high: float = 0.92
    geometry_floor_low: float = 0.88
    unstable_width_cv: float = 0.030
    full_outer_min_area: float = 0.40
    low_confidence_floor: float = 0.85
    partial_one_cap: float = 0.78
    partial_two_35mm_cap: float = 0.82
    partial_general_cap: float = 0.84
    outer_too_large_cap: float = 0.82
    family_separator_uncertain_reason: str = "separator_evidence_incomplete"


@dataclass(frozen=True)
class SeparatorSupportScorePolicy:
    model_grid_credit: float = 0.35
    model_equal_credit: float = 0.12
    hard_weight: float = 0.78
    model_weight: float = 0.22
    no_expected_confidence_threshold: float = 0.85
    no_expected_confidence_cap: float = 0.75


@dataclass(frozen=True)
class ScoringPolicy:
    confidence_threshold_default: float = 0.85
    hard_full_confidence_floor: float = 0.0
    geometry_weight: float = 0.34
    content_weight: float = 0.33
    separator_weight: float = 0.33
    separator_source_bias: float = 0.0
    no_auto_cap_full: float = 0.84
    no_auto_cap_partial: float = 0.82
    competition_top_n: int = 8
    competition_close_margin: float = 0.04
    base_detection: BaseDetectionScorePolicy = field(default_factory=BaseDetectionScorePolicy)
    geometry_support: GeometrySupportScorePolicy = field(default_factory=GeometrySupportScorePolicy)
    separator_support: SeparatorSupportScorePolicy = field(default_factory=SeparatorSupportScorePolicy)


@dataclass(frozen=True)
class ContentMismatchReviewSelectionPolicy:
    enabled: bool = False
    strip_modes: tuple[str, ...] = ("full",)
    require_default_count: bool = True
    required_best_source: str = "content"
    required_review_reason: str = "content_run_count_mismatch"
    candidate_source: str = "separator"
    min_hard_ratio: float = 0.50
    max_equal_gaps: int = 0
    required_content_support: str = "ok"
    override_reason: str = "content_candidate_mismatch_prefers_separator_review"


@dataclass(frozen=True)
class SelectionPolicy:
    top_n: int = 8
    close_margin: float = 0.04
    confidence_cap: float = 0.84
    content_mismatch_review: ContentMismatchReviewSelectionPolicy = field(default_factory=ContentMismatchReviewSelectionPolicy)


@dataclass(frozen=True)
class FallbackPolicy:
    use_outer_proposals: bool = True
    strategies: tuple[str, ...] = (
        "separator_outer",
        "edge_anchor_outer",
        "separator_geometry_outer",
    )


@dataclass(frozen=True)
class PartialStopPolicy:
    stop_after_safe_auto: bool = True
    skip_content_after_safe_auto: bool = True
    skip_content_after_safe_auto_strip_modes: tuple[str, ...] = ("partial",)
    skip_content_after_safe_auto_reason: str = "partial_safe_separator_auto_gate_passed"


@dataclass(frozen=True)
class SeparatorGeometryCompetitionPolicy:
    enabled: bool = True
    content_outer_max_median_aspect_strategies: tuple[str, ...] = ("content_outer",)
    content_outer_max_median_aspect_strip_modes: tuple[str, ...] = ("partial",)
    content_outer_max_median_aspect: float = 1.045
    general_min_median_aspect: float = 1.090


@dataclass(frozen=True)
class DarkBandCandidateRunPolicy:
    try_full_default_count: bool = True
    full_retry_strip_modes: tuple[str, ...] = ("full",)
    full_retry_requires_default_count: bool = True
    partial_retry_strip_modes: tuple[str, ...] = ("partial",)
    try_partial_when_no_safe_wide_like_candidate: bool = True
    partial_retry_on_equal_gaps: bool = True
    partial_retry_on_insufficient_wide_like_gaps: bool = True


@dataclass(frozen=True)
class ContentCandidateRunPolicy:
    enabled: bool = True
    skip_after_separator_auto: bool = True
    separator_auto_skip_strip_modes: tuple[str, ...] = ("full",)
    separator_auto_skip_reason: str = "separator_auto_gate_passed"
    disabled_skip_reason: str = "disabled_by_policy"


@dataclass(frozen=True)
class EqualFirstWideRetryPolicy:
    enabled: bool = True
    requires_wide_geometry_support: bool = True
    strip_modes: tuple[str, ...] = ("full",)
    requires_default_count: bool = True


@dataclass(frozen=True)
class CandidateRunPolicy:
    equal_first_before_wide_retry: EqualFirstWideRetryPolicy = field(
        default_factory=EqualFirstWideRetryPolicy
    )
    content_candidate: ContentCandidateRunPolicy = field(default_factory=ContentCandidateRunPolicy)
    fallback: FallbackPolicy = field(default_factory=FallbackPolicy)
    partial_stop: PartialStopPolicy = field(default_factory=PartialStopPolicy)
    separator_geometry_competition: SeparatorGeometryCompetitionPolicy = field(
        default_factory=SeparatorGeometryCompetitionPolicy
    )
    dark_band_retry: DarkBandCandidateRunPolicy = field(default_factory=DarkBandCandidateRunPolicy)


@dataclass(frozen=True)
class ApprovedGeometryAdjustmentPolicy:
    long_limit_ratio: float = 0.018
    long_limit_min: int = 20
    long_limit_max: int = 60
    min_ext_ratio: float = 0.0100
    min_ext_min: int = 50
    min_ext_max: int = 120


@dataclass(frozen=True)
class PostprocessPolicy:
    align_outer_to_content: bool = True
    retry_uncertain_outer: bool = True
    apply_output_bleed: bool = True
    apply_approved_geometry_adjustment: bool = True
    approved_geometry_adjustment: ApprovedGeometryAdjustmentPolicy = field(default_factory=ApprovedGeometryAdjustmentPolicy)
    outer_alignment_disabled_reason: str = "disabled_by_policy"
    likely_partial_review_reason: str = "likely_partial_strip"
    outer_candidate_disagreement_review_reason: str = "outer_candidate_disagreement"
    deskew_uncertain_review_reason: str = "deskew_uncertain"
    content_aspect_conflict_cap: float = 0.82
    content_low_confidence_cap: float = 0.84
    outer_mismatch_cap: float = 0.84
    lucky_pass_risk_cap: float = 0.84


@dataclass(frozen=True)
class EdgeBleedProtectionPolicy:
    enabled: bool = True
    guard_ratio: float = 0.0150
    guard_min: float = 70.0
    guard_max: float = 120.0


@dataclass(frozen=True)
class OutputPolicy:
    detection_long_axis_bleed: int = 0
    detection_short_axis_bleed: int = 0
    output_long_axis_bleed_default: int = 20
    output_short_axis_bleed_default: int = 10
    overlap_risk_long_axis_bleed: int = 50
    edge_bleed_protection: EdgeBleedProtectionPolicy = field(default_factory=EdgeBleedProtectionPolicy)


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
class DebugGapOverlayPolicy:
    overlap_tolerance_ratio: float = 0.012
    overlap_tolerance_min: float = 4.0
    overlap_tolerance_max: float = 80.0
    tick_length_ratio: float = 0.12
    tick_length_min: int = 20
    hard_line_width: int = 2
    model_line_width: int = 2
    diagnostic_line_width: int = 3


@dataclass(frozen=True)
class NearbySeparatorDiagnosticsPolicy:
    window_ratio: float = 0.040
    window_min: int = 16
    window_max: int = 320
    exclude_ratio: float = 0.012
    exclude_min: int = 8
    exclude_max: int = 120
    max_width_ratio: float = 0.070
    max_width_min: int = 2
    max_width_max: int = 520
    detail_score_add: float = 0.08
    detail_score_multiplier: float = 1.18


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
    unstable_width_cv: float = 0.006
    unstable_width_weight: float = 0.16
    mild_width_cv: float = 0.003
    mild_width_weight: float = 0.08
    strong_hard_credit_min: int = 3
    strong_hard_credit: float = -0.15
    stable_width_cv: float = 0.002
    stable_model_gap_min: int = 3
    stable_geometry_credit: float = -0.35
    risk_threshold: float = 0.80


@dataclass(frozen=True)
class DebugPanelPolicy:
    panel_id: str
    title: str


@dataclass(frozen=True)
class RuntimeDiagnosticsPolicy:
    attach_read_only_when_requested: bool = True
    overlap_bleed_risk: OverlapBleedRiskPolicy = field(default_factory=OverlapBleedRiskPolicy)
    debug_gap_overlay: DebugGapOverlayPolicy = field(default_factory=DebugGapOverlayPolicy)
    nearby_separator: NearbySeparatorDiagnosticsPolicy = field(default_factory=NearbySeparatorDiagnosticsPolicy)
    lucky_pass_risk: LuckyPassRiskPolicy = field(default_factory=LuckyPassRiskPolicy)
    debug_panels: tuple[str, ...] = (
        "original_gray",
        "debug_boxes",
        "separator_evidence",
    )
    debug_panel_titles: tuple[DebugPanelPolicy, ...] = (
        DebugPanelPolicy("original_gray", "Original gray context"),
        DebugPanelPolicy("debug_boxes", "Debug boxes"),
        DebugPanelPolicy("separator_evidence", "Separator evidence"),
        DebugPanelPolicy("frame_geometry", "Frame geometry"),
        DebugPanelPolicy("outer_candidates", "Outer candidates"),
        DebugPanelPolicy("selected_candidate", "Selected candidate"),
        DebugPanelPolicy("risk_review", "Risk / review overlay"),
    )

    def debug_panel_title(self, panel_id: str) -> str:
        for panel in self.debug_panel_titles:
            if panel.panel_id == panel_id:
                return panel.title
        return panel_id.replace("_", " ").title()


@dataclass(frozen=True)
class ReportPolicy:
    schema_version: str = REPORT_SCHEMA_VERSION
    sections: tuple[str, ...] = (
        "version",
        "format",
        "result",
        "selected_candidate",
        "evidence_summary",
        "risk_summary",
        "decision_policy_detail",
        "policy_id",
        "candidate_table",
        "output",
    )


@dataclass(frozen=True)
class DetectionPolicy:
    policy_id: str
    format_id: str
    strip_mode: str
    family: str
    role: str
    detector: DetectorPolicy
    source_parameters: FormatParameters
    counts: CountPolicy
    outer: OuterPolicy
    separator: SeparatorPolicy
    content: ContentPolicy
    partial_holder: PartialHolderPolicy
    partial_edge_hint: PartialEdgeHintPolicy
    frame_fit: FrameFitPolicy
    gates: GatePolicy
    scoring: ScoringPolicy
    candidate_selection: SelectionPolicy
    candidate_run: CandidateRunPolicy
    postprocess: PostprocessPolicy
    output: OutputPolicy = field(default_factory=OutputPolicy)
    diagnostics: RuntimeDiagnosticsPolicy = field(default_factory=RuntimeDiagnosticsPolicy)
    report: ReportPolicy = field(default_factory=ReportPolicy)
    notes: tuple[str, ...] = ()

    def report_detail(self) -> dict[str, Any]:
        from .reporting import detection_policy_report_detail

        return detection_policy_report_detail(self)
