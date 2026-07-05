from __future__ import annotations

from dataclasses import dataclass, field

from ...constants import (
    GAP_CONTENT,
    GAP_DETECTED,
    GAP_EDGE_PAIR,
    GAP_ENHANCED_DETECTED,
    GAP_EQUAL,
    GAP_GRID,
)
from ...geometry.detection_parameters import (
    EdgePairParameters,
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
class SeparatorModelGapProposalPolicy:
    detected_geometry_equal_model_enabled: bool = False
    detected_geometry_strip_modes: tuple[str, ...] = ("full",)
    requires_default_count: bool = True
    requires_standard_width_search: bool = True

    def detected_geometry_equal_model_available(
        self,
        *,
        strip_mode: str,
        count: int,
        default_count: int,
        gap_max_width_ratio_override: float | None,
    ) -> bool:
        if not self.detected_geometry_equal_model_enabled:
            return False
        if strip_mode not in self.detected_geometry_strip_modes:
            return False
        if self.requires_default_count and int(count) != int(default_count):
            return False
        if self.requires_standard_width_search and gap_max_width_ratio_override is not None:
            return False
        return True


@dataclass(frozen=True)
class SeparatorWidthProfilePolicy:
    mode: str = "off"
    max_width_ratio: float = 0.060
    confidence_cap: float = 0.995
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
class SeparatorEdgePairPolicy(EdgePairParameters):
    """Format preset type for edge-pair parameters."""


@dataclass(frozen=True)
class SeparatorPolicy:
    gate: SeparatorGatePolicy
    hard_required_all_gaps: bool
    model_gap_proposal: SeparatorModelGapProposalPolicy = field(default_factory=SeparatorModelGapProposalPolicy)
    width_profile: SeparatorWidthProfilePolicy = field(default_factory=SeparatorWidthProfilePolicy)
    width_profile_search: SeparatorWidthProfileSearchParameters = field(default_factory=SeparatorWidthProfileSearchParameters)
    geometry_support_modes: tuple[str, ...] = ()
    geometry_support: SeparatorGeometrySupportPolicy = field(default_factory=SeparatorGeometrySupportPolicy)
    edge_pair: EdgePairParameters = field(default_factory=EdgePairParameters)
    hard_gap_trust: HardGapTrustParameters = field(default_factory=HardGapTrustParameters)
    nearby_correction: NearbySeparatorCorrectionParameters = field(default_factory=NearbySeparatorCorrectionParameters)
    robust_grid: RobustGridParameters = field(default_factory=RobustGridParameters)
    gap_search: GapSearchParameters = field(default_factory=GapSearchParameters)
    enhanced: EnhancedSeparatorParameters = field(default_factory=EnhancedSeparatorParameters)
    profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)
    edge_refine_profile: EdgeRefineProfileParameters = field(default_factory=EdgeRefineProfileParameters)
    hard_methods: tuple[str, ...] = (GAP_DETECTED, GAP_EDGE_PAIR, GAP_ENHANCED_DETECTED)
    model_methods: tuple[str, ...] = (GAP_GRID, GAP_EQUAL, GAP_CONTENT)


__all__ = [
    "LeadingGridFailurePolicy",
    "SeparatorEdgePairPolicy",
    "SeparatorGatePolicy",
    "SeparatorGeometrySupportModePolicy",
    "SeparatorGeometrySupportPolicy",
    "SeparatorModelGapProposalPolicy",
    "SeparatorPolicy",
    "SeparatorWidthProfilePolicy",
]
