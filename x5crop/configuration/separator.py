from __future__ import annotations

from dataclasses import dataclass, field

from ..image.separator_profile import SeparatorProfileParameters
from ..utils import require_percentile, require_positive
from ..utils import require_unit_interval


@dataclass(frozen=True)
class SeparatorObservationParameters:
    activation_percentile: float = 90.0
    minimum_profile_range: float = 1e-6
    minimum_run_px: int = 1
    maximum_observations: int = 32
    maximum_cross_axis_break_ratio: float = 0.03

    def __post_init__(self) -> None:
        require_percentile(
            "separator activation percentile",
            self.activation_percentile,
        )
        require_positive("separator profile range", self.minimum_profile_range)
        require_positive("separator minimum run width", self.minimum_run_px)
        require_positive("separator observation budget", self.maximum_observations)
        require_unit_interval(
            "separator cross-axis break ratio",
            self.maximum_cross_axis_break_ratio,
        )


@dataclass(frozen=True)
class SeparatorConfiguration:
    observation: SeparatorObservationParameters = field(
        default_factory=SeparatorObservationParameters
    )
    profile: SeparatorProfileParameters = field(
        default_factory=SeparatorProfileParameters
    )
