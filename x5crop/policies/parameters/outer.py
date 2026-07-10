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
    separator_gap_search_max_width_ratio: float = 0.095

@dataclass(frozen=True)
class FloatingContentPositionParameters:
    ratio_extras: tuple[float, ...] = (0.06, 0.10)
    content_threshold: int = 225
    content_margin_ratio: float = 0.012
    content_margin_min: int = 12
    content_margin_max: int = 80
    min_width_ratio: float = 0.30
    content_bbox_min_fraction: float = 0.010
    min_short_axis_px: int = 40
    min_short_axis_ratio: float = 0.65
    min_width_px: int = 80
    max_candidates: int = 12

@dataclass(frozen=True)
class EdgeAnchoredContentPositionParameters:
    partial_center_ratio: float = 0.35
    ratio_extras: tuple[float, ...] = (0.06, 0.10)
    content_threshold: int = 225
    content_margin_ratio: float = 0.012
    content_margin_min: int = 12
    content_margin_max: int = 80
    min_width_ratio: float = 0.30
    content_bbox_min_fraction: float = 0.010
    min_short_axis_px: int = 40
    min_short_axis_ratio: float = 0.65
    min_width_px: int = 80
    max_candidates: int = 8

@dataclass(frozen=True)
class BaseOuterCandidateParameters:
    white_x_width_multiplier: float = 1.80
    white_x_extra_ratio: float = 0.060
    candidate_max_area: float = 0.94
    mask_expand_ratio: float = 0.002
    mask_profiles: tuple[OuterMaskProfile, ...] = (
        OuterMaskProfile("mask_not_white_246", None, 246),
        OuterMaskProfile("mask_not_white_225", None, 225),
        OuterMaskProfile("mask_mid_8_246", 8, 246),
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
class SeparatorOuterBandParameters:
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
    sequence_pair_score_weight: float = 0.02
    edge_margin_min_px: float = 60.0
    edge_margin_max_short_axis_ratio: float = 0.80
    prominence_min: float = 0.02
    high_mean_prominence_bypass: float = 0.88
    prominence_score_weight: float = 0.8
    band_to_peak_ratio: float = 0.58
    pair_candidate_expansion: int = 3

@dataclass(frozen=True)
class FullWidthSeparatorOuterParameters:
    required_count: int = 0
    source_candidate_count: int = 3
    margin_ratios: tuple[float, ...] = (0.00, 0.018, 0.035)
    max_candidates: int = 8

@dataclass(frozen=True)
class LongAxisGeometryCorrectionParameters:
    ratio_tolerance: float = 0.025
    min_shrink_ratio: float = 0.003
    max_shrink_ratio: float = 0.120
    content_margin_ratio: float = 0.010
    content_margin_min: int = 12
    content_margin_max: int = 80
    min_corrected_width_ratio: float = 0.80
    min_corrected_width_px: int = 80

@dataclass(frozen=True)
class GridOuterRefineParameters:
    shift_ratio: float = 0.080
    shift_min: int = 8
    shift_max: int = 420
    max_width_change: float = 0.12

@dataclass(frozen=True)
class ShortAxisGeometryCorrectionParameters:
    min_error: float = 0.24
    target_aspect: float = 0.0
    margin_ratio: float = 0.008
    margin_min: int = 12
    margin_max: int = 80

@dataclass(frozen=True)
class ContentContainmentCorrectionParameters:
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
    min_corrected_size_ratio: float = 0.80
    min_corrected_width_px: int = 80
    min_corrected_height_px: int = 40

@dataclass(frozen=True)
class OuterAlignmentEvidenceParameters:
    content_bbox_thresholds: tuple[int, ...] = (225, 210, 190)
    content_bbox_min_row_fraction: float = 0.015
    content_bbox_min_col_fraction: float = 0.015
    border_dark_threshold: int = 245
    border_band_min_px: int = 4
    border_band_max_px: int = 80
    edge_short_min_px: int = 24
    white_edge_long_ratio: float = 0.0190
    white_edge_long_min: int = 90
    white_edge_long_max: int = 180
    long_threshold_ratio: float = 0.0340
    long_threshold_min: int = 160
    long_threshold_max: int = 320
    short_threshold_ratio: float = 0.0060
    short_threshold_min: int = 28
    short_threshold_max: int = 80
    long_excess_ratio: float = 0.050
    long_excess_threshold_ratio: float = 0.035
    short_excess_ratio: float = 0.035
    short_requires_hard_anchors: bool = False
    short_content_height_max: float = 1.0
    content_width_min: float = 0.985
    edge_short_ratio: float = 0.015
    edge_dark_max: float = 0.02
    border_band_ratio: float = 0.018
