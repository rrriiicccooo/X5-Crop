from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OuterMaskProfile:
    name: str
    low: Optional[int]
    high: Optional[int]
    min_row_fraction: float = 0.012
    min_col_fraction: float = 0.012

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

__all__ = [
    'OuterMaskProfile',
    'OuterStrategyParameters',
    'ContentFloatingOuterParameters',
    'EdgeAnchorOuterParameters',
    'BaseOuterCandidateParameters',
    'SeparatorOuterBandParameters',
    'SeparatorGeometryOuterParameters',
    'FormatGeometryRetryParameters',
    'GridOuterRefineParameters',
    'ShortAxisAspectRetryParameters',
    'OuterContentAlignmentParameters',
]
