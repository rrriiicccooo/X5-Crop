from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_percentile


@dataclass(frozen=True)
class BoundaryObservationParameters:
    holder_reference_percentile: float = 10.0
    change_point_percentile: float = 90.0

    def __post_init__(self) -> None:
        require_percentile(
            "holder reference percentile",
            self.holder_reference_percentile,
        )
        require_percentile(
            "boundary change-point percentile",
            self.change_point_percentile,
        )
