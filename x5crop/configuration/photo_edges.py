from __future__ import annotations

from dataclasses import dataclass, field
import math

from ..utils import require_positive, require_unit_interval


@dataclass(frozen=True)
class PhotoEdgeGeometryParameters:
    subpixel_resolution_px: float = 1.0 / 16.0
    maximum_subdivision_depth: int = 64
    maximum_region_cells: int = 16_384
    maximum_consensus_states: int = 4_096

    def __post_init__(self) -> None:
        for name, value in (
            ("photo-edge subpixel resolution", self.subpixel_resolution_px),
            (
                "photo-edge maximum subdivision depth",
                self.maximum_subdivision_depth,
            ),
            ("photo-edge maximum region cells", self.maximum_region_cells),
            (
                "photo-edge maximum consensus states",
                self.maximum_consensus_states,
            ),
        ):
            require_positive(name, value)
        if not isinstance(self.maximum_subdivision_depth, int):
            raise TypeError("photo-edge subdivision depth must be an integer")
        if not isinstance(self.maximum_region_cells, int):
            raise TypeError("photo-edge region-cell budget must be an integer")
        if not isinstance(self.maximum_consensus_states, int):
            raise TypeError("photo-edge consensus budget must be an integer")


@dataclass(frozen=True)
class PhotoEdgeDetectionParameters:
    minimum_independent_observations: int = 3
    minimum_local_effect: float = 2.0
    local_noise_floor_u8: float = 0.5
    local_window_height_ratio: float = 0.01
    local_window_min_px: int = 3
    multiscale_factors: tuple[float, ...] = (0.5, 1.0, 2.0)
    minimum_supporting_scales: int = 2
    multiscale_position_tolerance_ratio: float = 0.1
    long_support_width_px: int = 8
    long_anchor_stride_px: int = 4
    chunk_size_px: int = 1_024
    maximum_search_angle_degrees: float = 4.0
    maximum_center_offset_mm: float = 1.0
    maximum_photo_dimension_deviation_mm: float = 1.0
    geometry: PhotoEdgeGeometryParameters = field(
        default_factory=PhotoEdgeGeometryParameters
    )

    def __post_init__(self) -> None:
        for name, value in (
            (
                "photo-edge minimum independent observations",
                self.minimum_independent_observations,
            ),
            ("photo-edge minimum local effect", self.minimum_local_effect),
            ("photo-edge local noise floor", self.local_noise_floor_u8),
            (
                "photo-edge local window height ratio",
                self.local_window_height_ratio,
            ),
            ("photo-edge local window minimum", self.local_window_min_px),
            (
                "photo-edge minimum supporting scales",
                self.minimum_supporting_scales,
            ),
            (
                "photo-edge multiscale position tolerance ratio",
                self.multiscale_position_tolerance_ratio,
            ),
            ("photo-edge long support width", self.long_support_width_px),
            ("photo-edge long anchor stride", self.long_anchor_stride_px),
            ("photo-edge chunk size", self.chunk_size_px),
            (
                "photo-edge maximum search angle",
                self.maximum_search_angle_degrees,
            ),
            ("photo-edge maximum center offset", self.maximum_center_offset_mm),
            (
                "photo-edge maximum dimension deviation",
                self.maximum_photo_dimension_deviation_mm,
            ),
        ):
            require_positive(name, value)
        for name in (
            "minimum_independent_observations",
            "local_window_min_px",
            "minimum_supporting_scales",
            "long_support_width_px",
            "long_anchor_stride_px",
            "chunk_size_px",
        ):
            if not isinstance(getattr(self, name), int):
                raise TypeError(f"photo-edge {name} must be an integer")
        require_unit_interval(
            "photo-edge local window height ratio",
            self.local_window_height_ratio,
        )
        require_unit_interval(
            "photo-edge multiscale position tolerance ratio",
            self.multiscale_position_tolerance_ratio,
        )
        if min(
            self.local_window_height_ratio,
            self.multiscale_position_tolerance_ratio,
        ) <= 0.0:
            raise ValueError("photo-edge measurement ratios must be positive")
        if (
            len(self.multiscale_factors)
            < self.minimum_supporting_scales
            or tuple(sorted(set(self.multiscale_factors)))
            != self.multiscale_factors
            or any(
                not math.isfinite(factor) or factor <= 0.0
                for factor in self.multiscale_factors
            )
        ):
            raise ValueError(
                "photo-edge scales must be ordered, unique, positive, and "
                "cover the supporting-scale minimum"
            )
        if self.long_anchor_stride_px > self.long_support_width_px:
            raise ValueError(
                "photo-edge anchor stride cannot exceed its support width"
            )
        if self.chunk_size_px < self.long_support_width_px:
            raise ValueError(
                "photo-edge chunks must contain a complete support footprint"
            )
        if not isinstance(self.geometry, PhotoEdgeGeometryParameters):
            raise TypeError("photo-edge detection requires typed geometry parameters")
