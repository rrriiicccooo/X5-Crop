from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundaryDetectionParameters:
    min_width_ratio: float = 0.10
    min_height_ratio: float = 0.10
    min_width_px: int = 20
    min_height_px: int = 20
    bw_not_white_threshold: int = 246
    white_run_ratio: float = 0.003
    white_run_min: int = 2
    white_run_max: int = 80
    white_light_threshold: int = 225
    white_holder_cross_axis_min: float = 0.95
    white_margin_ratio: float = 0.002
    white_margin_min: int = 2
    tonal_footprint_min_fraction: float = 0.015
    texture_activity_min: float = 0.040


@dataclass(frozen=True)
class SeparatorContinuityParameters:
    extreme_light_threshold: int = 235
    extreme_dark_threshold: int = 55
    minimum_row_activity: float = 0.030
    minimum_cross_axis_coverage: float = 0.62
    minimum_cross_axis_continuity: float = 0.55


@dataclass(frozen=True)
class SeparatorProfileParameters:
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
    sample_short_axis_max: int = 500
    smooth_ratio: float = 0.0015
    smooth_min: int = 3
