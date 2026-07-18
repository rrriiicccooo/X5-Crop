from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_percentile, require_positive, require_unit_interval


@dataclass(frozen=True)
class BoundaryPathParameters:
    edge_reference_mad_multiplier: float = 3.0
    change_point_percentile: float = 90.0
    minimum_cross_sections: int = 5
    maximum_section_width_ratio_to_scan_extent: float = 0.5
    minimum_path_support_ratio: float = 0.60
    local_measurement_window_ratio: float = 0.01
    minimum_local_measurement_window_px: int = 3
    edge_transition_persistence_ratio: float = 0.80
    path_cluster_tolerance_ratio: float = 0.005
    path_cluster_tolerance_min_px: int = 2
    path_inlier_mad_multiplier: float = 3.0
    maximum_path_fit_residual_ratio: float = 0.06
    maximum_path_section_gap: int = 1
    maximum_change_points_per_section: int = 64

    def __post_init__(self) -> None:
        require_positive(
            "canvas-edge reference MAD multiplier",
            self.edge_reference_mad_multiplier,
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
        require_unit_interval(
            "boundary local measurement window ratio",
            self.local_measurement_window_ratio,
        )
        if self.local_measurement_window_ratio <= 0.0:
            raise ValueError("boundary local measurement window ratio must be positive")
        require_positive(
            "boundary minimum local measurement window",
            self.minimum_local_measurement_window_px,
        )
        require_unit_interval(
            "boundary edge transition persistence",
            self.edge_transition_persistence_ratio,
        )
        if self.edge_transition_persistence_ratio <= 0.0:
            raise ValueError("boundary edge transition persistence must be positive")
        require_unit_interval(
            "boundary path cluster tolerance",
            self.path_cluster_tolerance_ratio,
        )
        require_positive(
            "boundary path cluster minimum",
            self.path_cluster_tolerance_min_px,
        )
        require_positive(
            "boundary path inlier MAD multiplier",
            self.path_inlier_mad_multiplier,
        )
        require_unit_interval(
            "boundary maximum path-fit residual ratio",
            self.maximum_path_fit_residual_ratio,
        )
        if self.maximum_path_fit_residual_ratio <= 0.0:
            raise ValueError("boundary path-fit residual ratio must be positive")
        if self.maximum_path_section_gap < 0:
            raise ValueError("boundary path section gap cannot be negative")
        require_positive(
            "boundary maximum change-point count",
            self.maximum_change_points_per_section,
        )
