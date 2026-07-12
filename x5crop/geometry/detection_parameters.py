from __future__ import annotations

from dataclasses import dataclass

from ..utils import (
    require_nonnegative,
    require_percentile,
    require_positive,
    require_unit_interval,
)


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

    def __post_init__(self) -> None:
        require_unit_interval("separator profile top ratio", self.top_ratio)
        require_unit_interval("separator profile bottom ratio", self.bottom_ratio)
        if self.bottom_ratio <= self.top_ratio:
            raise ValueError("separator profile bottom must follow top")
        require_positive("separator profile segment count", self.segments)
        require_percentile(
            "separator consistency percentile",
            self.consistency_percentile,
        )
        require_positive("separator short-axis sample limit", self.sample_short_axis_max)
        require_nonnegative("separator smoothing ratio", self.smooth_ratio)
        require_positive("separator minimum smoothing width", self.smooth_min)
        require_positive("separator numerical floor", self.numerical_floor)
