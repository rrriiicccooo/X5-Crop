from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_percentile, require_positive, require_unit_interval


MAX_CROSS_SECTION_MARGIN_RATIO = 0.5


@dataclass(frozen=True)
class BoundaryPathParameters:
    holder_reference_percentile: float = 10.0
    change_point_percentile: float = 90.0
    cross_sections: int = 5
    cross_section_margin_ratio: float = 0.10
    minimum_path_support_ratio: float = 0.60
    inner_sample_ratio: float = 0.01

    def __post_init__(self) -> None:
        require_percentile(
            "holder reference percentile",
            self.holder_reference_percentile,
        )
        require_percentile(
            "boundary change-point percentile",
            self.change_point_percentile,
        )
        require_positive("boundary cross-section count", self.cross_sections)
        require_unit_interval(
            "boundary cross-section margin",
            self.cross_section_margin_ratio,
        )
        if self.cross_section_margin_ratio >= MAX_CROSS_SECTION_MARGIN_RATIO:
            raise ValueError("boundary cross-section margin must leave a sample corridor")
        require_unit_interval(
            "boundary minimum path support",
            self.minimum_path_support_ratio,
        )
        if self.minimum_path_support_ratio <= 0.0:
            raise ValueError("boundary path support must be positive")
        require_unit_interval("boundary inner sample ratio", self.inner_sample_ratio)
        if self.inner_sample_ratio <= 0.0:
            raise ValueError("boundary inner sample ratio must be positive")
