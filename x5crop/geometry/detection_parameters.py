from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorProfileParameters:
    top_ratio: float = 0.10
    bottom_ratio: float = 0.90
    segments: int = 5
    consistency_percentile: float = 20.0
    sample_short_axis_max: int = 500
    smooth_ratio: float = 0.0015
    smooth_min: int = 3
    numerical_floor: float = 1e-6
