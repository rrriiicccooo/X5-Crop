from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_percentile, require_positive, require_unit_interval


@dataclass(frozen=True)
class BoundaryPathParameters:
    edge_reference_percentile: float = 10.0
    change_point_percentile: float = 90.0
    minimum_cross_sections: int = 5
    maximum_section_width_ratio_to_scan_extent: float = 0.5
    minimum_path_support_ratio: float = 0.60
    inner_sample_ratio: float = 0.01
    path_cluster_tolerance_ratio: float = 0.005
    path_cluster_tolerance_min_px: int = 2
    maximum_path_section_gap: int = 1
    strongest_change_points_per_section: int = 24
    maximum_paths_per_axis: int = 32

    def __post_init__(self) -> None:
        require_percentile(
            "canvas-edge reference percentile",
            self.edge_reference_percentile,
        )
        require_percentile(
            "boundary change-point percentile",
            self.change_point_percentile,
        )
        require_positive(
            "boundary minimum cross-section count",
            self.minimum_cross_sections,
        )
        require_unit_interval(
            "boundary maximum section-width ratio",
            self.maximum_section_width_ratio_to_scan_extent,
        )
        if self.maximum_section_width_ratio_to_scan_extent <= 0.0:
            raise ValueError("boundary section-width ratio must be positive")
        require_unit_interval(
            "boundary minimum path support",
            self.minimum_path_support_ratio,
        )
        if self.minimum_path_support_ratio <= 0.0:
            raise ValueError("boundary path support must be positive")
        require_unit_interval("boundary inner sample ratio", self.inner_sample_ratio)
        if self.inner_sample_ratio <= 0.0:
            raise ValueError("boundary inner sample ratio must be positive")
        require_unit_interval(
            "boundary path cluster tolerance",
            self.path_cluster_tolerance_ratio,
        )
        require_positive(
            "boundary path cluster minimum",
            self.path_cluster_tolerance_min_px,
        )
        if self.maximum_path_section_gap < 0:
            raise ValueError("boundary path section gap cannot be negative")
        require_positive(
            "boundary strongest change-point count",
            self.strongest_change_points_per_section,
        )
        require_positive(
            "boundary path budget",
            self.maximum_paths_per_axis,
        )
