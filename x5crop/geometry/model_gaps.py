from __future__ import annotations

from ..constants import GAP_CONTENT, GAP_EQUAL
from ..domain import Gap


def equal_model_gap(index: int, expected: float, score: float) -> Gap:
    return Gap(index, float(expected), float(score), GAP_EQUAL)




def content_model_gap(
    index: int,
    center: float,
    score: float,
    start: float | None = None,
    end: float | None = None,
) -> Gap:
    return Gap(
        index,
        float(center),
        float(score),
        GAP_CONTENT,
        None if start is None else float(start),
        None if end is None else float(end),
    )
