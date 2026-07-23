from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import require_positive, require_unit_interval
from .path_sampling import BoundaryPathSamplingParameters


PHOTO_EDGE_SUPPORT_BIN_COUNT = 3


@dataclass(frozen=True)
class PhotoEdgeDetectionParameters:
    path_sampling: BoundaryPathSamplingParameters = field(
        default_factory=BoundaryPathSamplingParameters
    )
    minimum_candidate_sections: int = 3
    minimum_fit_inliers: int = 5
    minimum_inlier_ratio: float = 0.80
    minimum_supported_windows: int = 3
    minimum_support_distribution_bins: int = 2
    minimum_local_effect: float = 2.0
    local_window_height_ratio: float = 0.01
    local_window_min_px: int = 3
    robust_mad_multiplier: float = 3.0
    maximum_separation_drift_ratio: float = 0.10
    maximum_shared_axis_uncertainty_ratio: float = 0.02
    shared_axis_uncertainty_floor_px: float = 3.0
    maximum_center_offset_mm: float = 1.0
    maximum_photo_dimension_deviation_mm: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(
            self.path_sampling,
            BoundaryPathSamplingParameters,
        ):
            raise TypeError(
                "photo-edge parameters require typed path sampling"
            )
        for name, value in (
            ("photo-edge minimum candidate sections", self.minimum_candidate_sections),
            ("photo-edge minimum fit inliers", self.minimum_fit_inliers),
            ("photo-edge minimum supported windows", self.minimum_supported_windows),
            (
                "photo-edge minimum support distribution bins",
                self.minimum_support_distribution_bins,
            ),
            ("photo-edge minimum local effect", self.minimum_local_effect),
            ("photo-edge local window minimum", self.local_window_min_px),
            ("photo-edge robust MAD multiplier", self.robust_mad_multiplier),
            (
                "photo-edge shared-axis uncertainty floor",
                self.shared_axis_uncertainty_floor_px,
            ),
            ("photo-edge maximum center offset", self.maximum_center_offset_mm),
            (
                "photo-edge maximum dimension deviation",
                self.maximum_photo_dimension_deviation_mm,
            ),
        ):
            require_positive(name, value)
        if self.minimum_fit_inliers < self.minimum_candidate_sections:
            raise ValueError(
                "photo-edge fit inliers must cover candidate retention"
            )
        if self.minimum_supported_windows > self.minimum_fit_inliers:
            raise ValueError(
                "photo-edge supported windows cannot exceed required inliers"
            )
        if (
            self.minimum_support_distribution_bins
            > PHOTO_EDGE_SUPPORT_BIN_COUNT
        ):
            raise ValueError(
                "photo-edge support distribution uses exactly three bins"
            )
        require_unit_interval(
            "photo-edge minimum inlier ratio",
            self.minimum_inlier_ratio,
        )
        require_unit_interval(
            "photo-edge local window height ratio",
            self.local_window_height_ratio,
        )
        if self.minimum_inlier_ratio <= 0.0:
            raise ValueError("photo-edge minimum inlier ratio must be positive")
        if self.local_window_height_ratio <= 0.0:
            raise ValueError("photo-edge local window ratio must be positive")
        require_unit_interval(
            "photo-edge maximum separation drift",
            self.maximum_separation_drift_ratio,
        )
        if self.maximum_separation_drift_ratio <= 0.0:
            raise ValueError(
                "photo-edge maximum separation drift must be positive"
            )
        require_unit_interval(
            "photo-edge maximum shared-axis uncertainty",
            self.maximum_shared_axis_uncertainty_ratio,
        )
        if self.maximum_shared_axis_uncertainty_ratio <= 0.0:
            raise ValueError(
                "photo-edge shared-axis uncertainty ratio must be positive"
            )
