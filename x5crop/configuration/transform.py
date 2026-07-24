from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive, require_unit_interval


@dataclass(frozen=True)
class TransformDetectionParameters:
    identity_span_ratio: float = 0.0005
    identity_span_min_px: float = 3.0
    identity_span_max_px: float = 12.0
    maximum_angle_degrees: float = 2.0
    maximum_projected_uncertainty_photo_height_ratio: float = 0.05

    def __post_init__(self) -> None:
        for name, value in (
            ("transform identity span minimum", self.identity_span_min_px),
            ("transform identity span maximum", self.identity_span_max_px),
            ("transform maximum angle", self.maximum_angle_degrees),
        ):
            require_positive(name, value)
        require_unit_interval(
            "transform identity span ratio",
            self.identity_span_ratio,
        )
        require_unit_interval(
            "transform maximum projected uncertainty",
            self.maximum_projected_uncertainty_photo_height_ratio,
        )
        if (
            self.identity_span_ratio <= 0.0
            or self.maximum_projected_uncertainty_photo_height_ratio <= 0.0
        ):
            raise ValueError("transform evidence ratios must be positive")
        if self.identity_span_max_px < self.identity_span_min_px:
            raise ValueError("transform identity span maximum must cover minimum")
