from __future__ import annotations

from dataclasses import dataclass, field

from ...units import PhysicalLength

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
class SeparatorOuterBandParameters:
    min_score: float = 0.58
    band_score: float = 0.36
    min_width_ratio: float = 0.006
    max_width_ratio: float = 0.120
    spacing_min_ratio: float = 0.82
    spacing_max_ratio: float = 1.24
    frame_error_max: float = 0.18
    edge_margin: PhysicalLength = field(
        default_factory=lambda: PhysicalLength(None, 0.18, 60, 2000)
    )
    source_candidate_count: int = 2
    band_candidate_count: int = 10
    pair_candidate_count: int = 4
    max_candidates: int = 12
    sequence_pair_score_weight: float = 0.02
    photo_width_cv_rank_weight: float = 0.50
    prominence_min: float = 0.02
    high_mean_prominence_bypass: float = 0.88
    prominence_score_weight: float = 0.8
    band_to_peak_ratio: float = 0.58
    pair_candidate_expansion: int = 3
    oversized_band_max_short_axis_ratio: float = 0.45
    oversized_band_score_penalty: float = 0.08

@dataclass(frozen=True)
class FullWidthSeparatorOuterParameters:
    source_candidate_count: int = 3
    margin_ratios: tuple[float, ...] = (0.00, 0.018, 0.035)
    max_candidates: int = 8

@dataclass(frozen=True)
class LongAxisGeometryCorrectionParameters:
    min_shrink_ratio: float = 0.003
    max_shrink_ratio: float = 0.120
    content_margin_ratio: float = 0.010
    content_margin_min: int = 12
    content_margin_max: int = 80

@dataclass(frozen=True)
class ShortAxisGeometryCorrectionParameters:
    min_error: float = 0.24
    max_expand_ratio: float = 0.60
    margin_ratio: float = 0.008
    margin_min: int = 12
    margin_max: int = 80

@dataclass(frozen=True)
class ContentContainmentCorrectionParameters:
    long_margin_ratio: float = 0.012
    long_margin_cap_min: int = 80
    long_margin_cap_max: int = 160
    short_margin_ratio: float = 0.010
    short_margin_cap_min: int = 40
    short_margin_cap_max: int = 80

@dataclass(frozen=True)
class OuterAlignmentEvidenceParameters:
    content_bbox_thresholds: tuple[int, ...] = (225, 210, 190)
    undercrop_confirmation_min_measurements: int = 2
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
