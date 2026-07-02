from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry.detection_parameters import (
    EdgeRefineProfilePolicy,
    EnhancedSeparatorPolicy,
    GapSearchPolicy,
    HardGapTrustPolicy,
    NearbySeparatorCorrectionPolicy,
    RobustGridPolicy,
    SeparatorProfilePolicy,
)


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
