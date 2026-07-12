from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorObservationParameters:
    profile_threshold: float = 0.22
    minimum_run_px: int = 1
    maximum_observations: int = 32


@dataclass(frozen=True)
class FrameDimensionPriorParameters:
    pass
