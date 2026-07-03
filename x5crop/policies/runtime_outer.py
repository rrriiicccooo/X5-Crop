from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry.detection_parameters import OuterBoxDetectionParameters, OuterMaskProfileParameters


@dataclass(frozen=True)
class ShortAxisGeometryCorrectionPolicy:
    enabled: bool = False
    min_error: float = 0.24
    target_aspect: float = 1.0
    margin_ratio: float = 0.008
    margin_min: int = 12
    margin_max: int = 80


@dataclass(frozen=True)
class LongAxisGeometryCorrectionPolicy:
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
class ContentContainmentCorrectionPolicy:
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
class FloatingContentPositionPolicy:
    enabled: bool = False
    ratio_extras: tuple[float, ...] = (0.06, 0.10)
    content_threshold: int = 225
    content_margin_ratio: float = 0.012
    content_margin_min: int = 12
    content_margin_max: int = 80
    min_width_ratio: float = 0.30
    max_candidates: int = 12


@dataclass(frozen=True)
class EdgeAnchoredContentPositionPolicy:
    enabled: bool = False
    partial_center_ratio: float = 0.35
    ratio_extras: tuple[float, ...] = (0.06, 0.10)
    content_threshold: int = 225
    content_margin_ratio: float = 0.012
    content_margin_min: int = 12
    content_margin_max: int = 80
    min_width_ratio: float = 0.30
    max_candidates: int = 8


@dataclass(frozen=True)
class PartialPlacementGeometryPolicy:
    enabled: bool = False
    position_order: tuple[str, ...] = ("edge_anchor", "floating")
    skip_floating_when_edge_trusted: bool = True
    edge_trust_min_candidates: int = 2
    floating: FloatingContentPositionPolicy = field(default_factory=FloatingContentPositionPolicy)
    edge_anchor: EdgeAnchoredContentPositionPolicy = field(default_factory=EdgeAnchoredContentPositionPolicy)


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
class FullWidthSeparatorOuterPolicy:
    required_count: int = 0
    source_candidate_count: int = 3
    margin_ratios: tuple[float, ...] = (0.00, 0.018, 0.035)
    max_candidates: int = 8


@dataclass(frozen=True)
class WideSeparatorOuterPolicy:
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
class BaseOuterProposalPolicy:
    enabled: bool = True
    candidates: OuterBoxDetectionParameters = field(default_factory=OuterBoxDetectionParameters)


@dataclass(frozen=True)
class SeparatorGeometryProposalPolicy:
    local: str = "off"
    full_width: str = "off"
    separator_outer_allow_oversized_band: bool = False
    separator_outer_oversized_band_max_ratio: float = 0.45
    separator_outer_oversized_band_score_penalty: float = 0.08
    separator_gap_search_max_width_ratio: float = 0.095
    band: SeparatorOuterBandPolicy = field(default_factory=SeparatorOuterBandPolicy)
    full_width_outer: FullWidthSeparatorOuterPolicy = field(default_factory=FullWidthSeparatorOuterPolicy)
    wide_mode: str = "off"
    wide_outer: WideSeparatorOuterPolicy = field(default_factory=WideSeparatorOuterPolicy)


@dataclass(frozen=True)
class GeometryOuterProposalPolicy:
    partial_placement: PartialPlacementGeometryPolicy = field(default_factory=PartialPlacementGeometryPolicy)
    separator: SeparatorGeometryProposalPolicy = field(default_factory=SeparatorGeometryProposalPolicy)
    grid_refine: GridOuterRefinePolicy = field(default_factory=GridOuterRefinePolicy)


@dataclass(frozen=True)
class OuterProposalPolicy:
    base: BaseOuterProposalPolicy = field(default_factory=BaseOuterProposalPolicy)
    geometry: GeometryOuterProposalPolicy = field(default_factory=GeometryOuterProposalPolicy)


@dataclass(frozen=True)
class GeometryConsistencyCorrectionPolicy:
    long_axis: LongAxisGeometryCorrectionPolicy = field(default_factory=LongAxisGeometryCorrectionPolicy)
    short_axis: ShortAxisGeometryCorrectionPolicy = field(default_factory=ShortAxisGeometryCorrectionPolicy)


@dataclass(frozen=True)
class OuterCorrectionPolicy:
    order: tuple[str, ...] = ("geometry_consistency", "content_containment")
    geometry_consistency: GeometryConsistencyCorrectionPolicy = field(default_factory=GeometryConsistencyCorrectionPolicy)
    content_containment: ContentContainmentCorrectionPolicy = field(default_factory=ContentContainmentCorrectionPolicy)


@dataclass(frozen=True)
class OuterPolicy:
    proposal: OuterProposalPolicy = field(default_factory=OuterProposalPolicy)
    correction: OuterCorrectionPolicy = field(default_factory=OuterCorrectionPolicy)


__all__ = [
    "BaseOuterProposalPolicy",
    "ContentContainmentCorrectionPolicy",
    "EdgeAnchoredContentPositionPolicy",
    "FloatingContentPositionPolicy",
    "FullWidthSeparatorOuterPolicy",
    "GeometryConsistencyCorrectionPolicy",
    "GeometryOuterProposalPolicy",
    "GridOuterRefinePolicy",
    "LongAxisGeometryCorrectionPolicy",
    "OuterCorrectionPolicy",
    "OuterPolicy",
    "OuterProposalPolicy",
    "PartialPlacementGeometryPolicy",
    "SeparatorOuterBandPolicy",
    "SeparatorGeometryProposalPolicy",
    "ShortAxisGeometryCorrectionPolicy",
    "WideSeparatorOuterPolicy",
]
