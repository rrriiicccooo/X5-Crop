from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import BoundaryDetectionParameters

@dataclass(frozen=True)
class SequenceContentAlignmentParameters:
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


@dataclass(frozen=True)
class SequenceParameters:
    boundary_detection: BoundaryDetectionParameters = field(
        default_factory=BoundaryDetectionParameters
    )
    content_alignment: SequenceContentAlignmentParameters = field(
        default_factory=SequenceContentAlignmentParameters
    )
