from __future__ import annotations

from ..constants import GAP_EQUAL
from ..domain import Gap


def equal_model_gap(index: int, expected: float, score: float) -> Gap:
    return Gap(index, float(expected), float(score), GAP_EQUAL)


__all__ = ["equal_model_gap"]
