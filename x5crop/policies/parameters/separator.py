from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorObservationParameters:
    activation_percentile: float = 90.0
    minimum_profile_range: float = 1e-6
    minimum_run_px: int = 1
    maximum_observations: int = 32
