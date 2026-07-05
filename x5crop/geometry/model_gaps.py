from __future__ import annotations

from ..constants import GAP_EQUAL, GAP_GRID
from ..domain import Gap


def equal_model_gap(index: int, expected: float, score: float) -> Gap:
    return Gap(index, float(expected), float(score), GAP_EQUAL)


def grid_model_gap(index: int, center: float, score: float) -> Gap:
    return Gap(index, float(center), float(score), GAP_GRID)


__all__ = ["equal_model_gap", "grid_model_gap"]
