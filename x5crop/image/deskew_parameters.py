from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeskewParameters:
    min_outer_width: int = 100
    outer_dark_threshold: int = 245
    outer_min_fraction: float = 0.01
    sample_width_px: int = 350
    min_samples: int = 6
    max_samples: int = 24
    min_col_content: int = 10
    min_col_content_ratio: float = 0.05
    slope_delta_max: float = 0.006
    residual_min: float = 3.0
    residual_height_ratio: float = 0.003
    auto_quality_ok: float = 8.0
    fallback_quality_gain: float = 3.0
    fit_min_points: int = 4
    fit_tolerance_min: float = 2.0
    fit_tolerance_multiplier: float = 3.0
    span_skip_ratio: float = 0.0005
    span_skip_min: float = 3.0
    span_skip_max: float = 12.0


__all__ = [
    "DeskewParameters",
]
