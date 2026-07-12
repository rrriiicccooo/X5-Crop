from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry.detection_parameters import SeparatorProfileParameters


@dataclass(frozen=True)
class SeparatorObservationParameters:
    activation_percentile: float = 90.0
    minimum_profile_range: float = 1e-6
    minimum_run_px: int = 1
    maximum_observations: int = 32


@dataclass(frozen=True)
class SeparatorConfiguration:
    observation: SeparatorObservationParameters = field(
        default_factory=SeparatorObservationParameters
    )
    profile: SeparatorProfileParameters = field(
        default_factory=SeparatorProfileParameters
    )
