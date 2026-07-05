from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import (
    EdgeRefineProfileParameters,
    EnhancedSeparatorParameters,
    GapSearchParameters,
    HardGapTrustParameters,
    NearbySeparatorCorrectionParameters,
    RobustGridParameters,
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
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
    edge_pair_min_score_without_broad_width: float = 0.0
    edge_pair_min_score_with_broad_width: float = 0.0
    min_broad_separator_width_gaps_for_auto: int = 0
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
    detected_geometry: SeparatorGeometrySupportModePolicy = field(default_factory=SeparatorGeometrySupportModePolicy)
    stable_grid: SeparatorGeometrySupportModePolicy = field(default_factory=SeparatorGeometrySupportModePolicy)

    def mode_policy(self, mode: str) -> SeparatorGeometrySupportModePolicy:
        if mode == "detected_geometry":
            return self.detected_geometry
        if mode == "stable_grid":
            return self.stable_grid
        return SeparatorGeometrySupportModePolicy()


@dataclass(frozen=True)
class SeparatorWidthProfilePolicy(SeparatorWidthProfileSearchParameters):
    mode: str = "off"
    required_count: int = 0
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
    separator_width_profile_enabled: bool
    separator_width_profile_max_width_ratio: float
    separator_width_profile_confidence_cap: float = 0.995
    width_profile: SeparatorWidthProfilePolicy = field(default_factory=SeparatorWidthProfilePolicy)
    geometry_support_modes: tuple[str, ...] = ()
    geometry_support: SeparatorGeometrySupportPolicy = field(default_factory=SeparatorGeometrySupportPolicy)
    edge_pair: SeparatorEdgePairPolicy = field(default_factory=SeparatorEdgePairPolicy)
    hard_gap_trust: HardGapTrustParameters = field(default_factory=HardGapTrustParameters)
    nearby_correction: NearbySeparatorCorrectionParameters = field(default_factory=NearbySeparatorCorrectionParameters)
    robust_grid: RobustGridParameters = field(default_factory=RobustGridParameters)
    gap_search: GapSearchParameters = field(default_factory=GapSearchParameters)
    enhanced: EnhancedSeparatorParameters = field(default_factory=EnhancedSeparatorParameters)
    profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)
    edge_refine_profile: EdgeRefineProfileParameters = field(default_factory=EdgeRefineProfileParameters)
    hard_methods: tuple[str, ...] = ("detected", "edge_pair", "enhanced_detected")
    model_methods: tuple[str, ...] = ("grid", "equal", "content")


__all__ = [
    "LeadingGridFailurePolicy",
    "SeparatorEdgePairPolicy",
    "SeparatorGatePolicy",
    "SeparatorGeometrySupportModePolicy",
    "SeparatorGeometrySupportPolicy",
    "SeparatorPolicy",
    "SeparatorWidthProfilePolicy",
]
