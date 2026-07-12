from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundaryObservationParameters:
    holder_reference_percentile: float = 10.0
    change_point_percentile: float = 90.0
