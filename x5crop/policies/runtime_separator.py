from __future__ import annotations

from dataclasses import dataclass, field


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
class SeparatorGatePolicy:
    """Separator auto-gate profile with explicit behavior parameters."""

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
    leading_grid_failure: LeadingGridFailurePolicy = field(default_factory=LeadingGridFailurePolicy)


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


__all__ = [
    "EdgeRefineProfilePolicy",
    "EnhancedSeparatorPolicy",
    "GapSearchPolicy",
    "HardGapTrustPolicy",
    "LeadingGridFailurePolicy",
    "NearbySeparatorCorrectionPolicy",
    "RobustGridPolicy",
    "SeparatorEdgePairPolicy",
    "SeparatorGatePolicy",
    "SeparatorGeometrySupportModePolicy",
    "SeparatorGeometrySupportPolicy",
    "SeparatorPolicy",
    "SeparatorProfilePolicy",
]
