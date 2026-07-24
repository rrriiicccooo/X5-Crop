from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive, require_unit_interval


@dataclass(frozen=True)
class SharedShortAxisParameters:
    maximum_endpoint_uncertainty_photo_height_ratio: float = 0.02
    minimum_endpoint_uncertainty_px: float = 3.0

    def __post_init__(self) -> None:
        require_unit_interval(
            "shared short-axis endpoint uncertainty ratio",
            self.maximum_endpoint_uncertainty_photo_height_ratio,
        )
        if self.maximum_endpoint_uncertainty_photo_height_ratio <= 0.0:
            raise ValueError(
                "shared short-axis uncertainty ratio must be positive"
            )
        require_positive(
            "shared short-axis minimum endpoint uncertainty",
            self.minimum_endpoint_uncertainty_px,
        )
