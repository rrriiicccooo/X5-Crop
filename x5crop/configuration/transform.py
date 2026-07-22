from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_nonnegative, require_positive, require_unit_interval


@dataclass(frozen=True)
class DeskewDetectionParameters:
    minimum_path_samples: int = 4
    minimum_common_support_ratio: float = 1.0
    minimum_photo_edge_intensity_range_ratio: float = 0.10
    minimum_holder_photo_gap_ratio: float = 0.01
    maximum_slope_delta: float = 0.006
    residual_floor_px: float = 3.0
    residual_height_ratio: float = 0.003
    identity_span_ratio: float = 0.0005
    identity_span_min_px: float = 3.0
    identity_span_max_px: float = 12.0
    maximum_angle_degrees: float = 2.0

    def __post_init__(self) -> None:
        for name, value in (
            ("deskew minimum path samples", self.minimum_path_samples),
            ("deskew residual floor", self.residual_floor_px),
            ("deskew identity span minimum", self.identity_span_min_px),
            ("deskew identity span maximum", self.identity_span_max_px),
            ("deskew maximum angle", self.maximum_angle_degrees),
        ):
            require_positive(name, value)
        require_unit_interval(
            "deskew minimum common support",
            self.minimum_common_support_ratio,
        )
        for name, value in (
            (
                "deskew minimum photo-edge intensity range",
                self.minimum_photo_edge_intensity_range_ratio,
            ),
            (
                "deskew minimum holder-photo gap",
                self.minimum_holder_photo_gap_ratio,
            ),
        ):
            require_unit_interval(name, value)
        if any(
            value <= 0.0
            for value in (
                self.minimum_common_support_ratio,
                self.minimum_photo_edge_intensity_range_ratio,
                self.minimum_holder_photo_gap_ratio,
            )
        ):
            raise ValueError("deskew evidence ratios must be positive")
        for name, value in (
            ("deskew maximum slope delta", self.maximum_slope_delta),
            ("deskew residual height ratio", self.residual_height_ratio),
            ("deskew identity span ratio", self.identity_span_ratio),
        ):
            require_nonnegative(name, value)
        if self.identity_span_max_px < self.identity_span_min_px:
            raise ValueError("deskew identity span maximum must cover minimum")
