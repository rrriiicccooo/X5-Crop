from __future__ import annotations

from dataclasses import dataclass, field

from ..image.separator_profile import SeparatorProfileParameters
from ..utils import require_percentile, require_positive
from ..utils import require_unit_interval


@dataclass(frozen=True)
class SeparatorObservationParameters:
    activation_percentile: float = 90.0
    prominence_activation_percentile: float = 80.0
    minimum_profile_range: float = 1e-6
    minimum_run_px: int = 1
    maximum_observations: int = 32
    maximum_cross_axis_break_ratio: float = 0.03
    minimum_cross_axis_supported_ratio: float = 0.50
    edge_measurement_cross_sections: int = 9
    edge_position_lower_percentile: float = 10.0
    edge_position_upper_percentile: float = 90.0

    def __post_init__(self) -> None:
        require_percentile(
            "separator activation percentile",
            self.activation_percentile,
        )
        require_percentile(
            "separator prominence activation percentile",
            self.prominence_activation_percentile,
        )
        require_positive("separator profile range", self.minimum_profile_range)
        require_positive("separator minimum run width", self.minimum_run_px)
        require_positive("separator observation budget", self.maximum_observations)
        require_unit_interval(
            "separator cross-axis break ratio",
            self.maximum_cross_axis_break_ratio,
        )
        require_unit_interval(
            "separator cross-axis supported ratio",
            self.minimum_cross_axis_supported_ratio,
        )
        require_positive(
            "separator edge cross-section count",
            self.edge_measurement_cross_sections,
        )
        require_percentile(
            "separator edge lower percentile",
            self.edge_position_lower_percentile,
        )
        require_percentile(
            "separator edge upper percentile",
            self.edge_position_upper_percentile,
        )
        if self.edge_position_upper_percentile <= self.edge_position_lower_percentile:
            raise ValueError("separator edge percentiles must be ordered")


@dataclass(frozen=True)
class SeparatorConfiguration:
    observation: SeparatorObservationParameters = field(
        default_factory=SeparatorObservationParameters
    )
    profile: SeparatorProfileParameters = field(
        default_factory=SeparatorProfileParameters
    )
