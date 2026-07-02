from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry.detection_parameters import OuterBoxDetectionPolicy, OuterMaskProfilePolicy


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
    dark_band_outer: DarkBandOuterPolicy = field(default_factory=DarkBandOuterPolicy)
    format_geometry_retry: FormatGeometryRetryPolicy = field(default_factory=FormatGeometryRetryPolicy)
    grid_refine: GridOuterRefinePolicy = field(default_factory=GridOuterRefinePolicy)
    short_axis_aspect_retry: ShortAxisAspectRetryPolicy = field(default_factory=ShortAxisAspectRetryPolicy)
    content_alignment: OuterContentAlignmentPolicy = field(default_factory=OuterContentAlignmentPolicy)
    content_floating_outer: ContentFloatingOuterPolicy = field(default_factory=ContentFloatingOuterPolicy)
    edge_anchor_outer: EdgeAnchorOuterPolicy = field(default_factory=EdgeAnchorOuterPolicy)
    base_candidates: OuterBoxDetectionPolicy = field(default_factory=OuterBoxDetectionPolicy)
    separator_outer_band: SeparatorOuterBandPolicy = field(default_factory=SeparatorOuterBandPolicy)
    separator_geometry_outer: SeparatorGeometryOuterPolicy = field(default_factory=SeparatorGeometryOuterPolicy)
    retries: tuple[str, ...] = ()


__all__ = [
    "ContentFloatingOuterPolicy",
    "DarkBandOuterPolicy",
    "EdgeAnchorOuterPolicy",
    "FormatGeometryRetryPolicy",
    "GridOuterRefinePolicy",
    "OuterBoxDetectionPolicy",
    "OuterContentAlignmentPolicy",
    "OuterMaskProfilePolicy",
    "OuterPolicy",
    "SeparatorGeometryOuterPolicy",
    "SeparatorOuterBandPolicy",
    "ShortAxisAspectRetryPolicy",
]
