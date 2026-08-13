"""Canonical mapping between source layout and physical axes."""

from __future__ import annotations

import math

from ...domain import Box, FiniteInterval
from .model import BoundaryAxis


def source_axes(layout: str) -> tuple[BoundaryAxis, BoundaryAxis]:
    if layout == "horizontal":
        return BoundaryAxis.X, BoundaryAxis.Y
    if layout == "vertical":
        return BoundaryAxis.Y, BoundaryAxis.X
    raise ValueError(f"unsupported source layout: {layout}")


def axis_interval(box: Box, axis: BoundaryAxis) -> FiniteInterval:
    return (
        FiniteInterval(float(box.left), float(box.right - 1))
        if axis == BoundaryAxis.X
        else FiniteInterval(float(box.top), float(box.bottom - 1))
    )


def coordinate_count(interval: FiniteInterval) -> int:
    return max(
        1,
        int(math.floor(interval.maximum) - math.ceil(interval.minimum) + 1),
    )
