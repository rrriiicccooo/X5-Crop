from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_nonnegative, require_positive, require_unit_interval


@dataclass(frozen=True)
class DeskewParameters:
    min_footprint_width: int = 100
    footprint_min_fraction: float = 0.01
    sample_width_px: int = 350
    min_samples: int = 6
    max_samples: int = 24
    min_col_content: int = 10
    min_col_content_ratio: float = 0.05
    slope_delta_max: float = 0.006
    residual_min: float = 3.0
    residual_height_ratio: float = 0.003
    fit_min_points: int = 4
    fit_tolerance_min: float = 2.0
    fit_tolerance_multiplier: float = 3.0
    span_skip_ratio: float = 0.0005
    span_skip_min: float = 3.0
    span_skip_max: float = 12.0

    def __post_init__(self) -> None:
        for name, value in (
            ("deskew minimum footprint width", self.min_footprint_width),
            ("deskew sample width", self.sample_width_px),
            ("deskew minimum samples", self.min_samples),
            ("deskew maximum samples", self.max_samples),
            ("deskew minimum column content", self.min_col_content),
            ("deskew minimum fit points", self.fit_min_points),
            ("deskew residual floor", self.residual_min),
            ("deskew fit tolerance floor", self.fit_tolerance_min),
            ("deskew fit tolerance multiplier", self.fit_tolerance_multiplier),
            ("deskew span minimum", self.span_skip_min),
            ("deskew span maximum", self.span_skip_max),
        ):
            require_positive(name, value)
        if self.max_samples < self.min_samples:
            raise ValueError("deskew maximum samples must cover minimum samples")
        if self.span_skip_max < self.span_skip_min:
            raise ValueError("deskew maximum span must cover minimum span")
        require_unit_interval(
            "deskew footprint fraction",
            self.footprint_min_fraction,
        )
        require_unit_interval(
            "deskew column-content ratio",
            self.min_col_content_ratio,
        )
        for name, value in (
            ("deskew slope delta", self.slope_delta_max),
            ("deskew residual height ratio", self.residual_height_ratio),
            ("deskew span ratio", self.span_skip_ratio),
        ):
            require_nonnegative(name, value)
