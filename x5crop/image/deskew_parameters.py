from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeskewParameters:
    min_outer_width: int
    outer_dark_threshold: int
    outer_min_fraction: float
    sample_width_px: int
    min_samples: int
    max_samples: int
    min_col_content: int
    min_col_content_ratio: float
    slope_delta_max: float
    residual_min: float
    residual_height_ratio: float
    auto_quality_ok: float
    fallback_quality_gain: float
    fit_min_points: int
    fit_tolerance_min: float
    fit_tolerance_multiplier: float
    span_skip_ratio: float
    span_skip_min: float
    span_skip_max: float


__all__ = [
    "DeskewParameters",
]
