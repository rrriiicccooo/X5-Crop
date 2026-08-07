from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class MinimumGuardSpec:
    sequence_axis_mm_per_side: float
    cross_axis_mm_per_side: float

    def __post_init__(self) -> None:
        if (
            self.sequence_axis_mm_per_side <= 0.0
            or self.cross_axis_mm_per_side <= 0.0
        ):
            raise ValueError("minimum guard requires positive millimetres")


_MINIMUM_GUARD_BY_FORMAT = {
    "half": MinimumGuardSpec(0.15, 0.25),
    "135": MinimumGuardSpec(0.25, 0.25),
    "135-dual": MinimumGuardSpec(0.25, 0.25),
    "120-645": MinimumGuardSpec(0.30, 0.25),
    "120-66": MinimumGuardSpec(0.40, 0.25),
    "xpan": MinimumGuardSpec(0.45, 0.25),
    "120-67": MinimumGuardSpec(0.50, 0.25),
}


def minimum_guard_spec(format_id: str) -> MinimumGuardSpec:
    return _MINIMUM_GUARD_BY_FORMAT[format_id]


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
