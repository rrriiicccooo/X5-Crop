from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DirectUseBudgetSpec:
    sequence_axis_ratio_per_side: float = 0.05
    cross_axis_ratio_per_side: float = 0.03

    def __post_init__(self) -> None:
        if (
            self.sequence_axis_ratio_per_side != 0.05
            or self.cross_axis_ratio_per_side != 0.03
        ):
            raise ValueError("direct-use budget ratios are frozen at 5%/3%")

DIRECT_USE_BUDGET_SPEC = DirectUseBudgetSpec()
