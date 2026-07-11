from __future__ import annotations

import numpy as np

from ..domain import Gap




def gap_width_cv(gaps: list[Gap], origin: float, pitch: float, count: int) -> float:
    if count <= 1:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    widths = np.diff(np.array(cuts, dtype=np.float64))
    if widths.size != count or np.any(widths <= 1):
        return 1.0
    return float(widths.std() / max(1.0, widths.mean()))


def width_cv(widths: list[float]) -> float:
    values = np.array(widths, dtype=np.float64)
    if values.size <= 1:
        return 0.0
    if np.any(values <= 1.0):
        return 1.0
    return float(values.std() / max(1.0, values.mean()))


def separator_widths(gaps: list[Gap]) -> list[float]:
    return [
        float(gap.width)
        for gap in gaps
        if gap.start is not None and gap.end is not None and gap.width > 1.0
    ]


def separator_width_cv(gaps: list[Gap]) -> float:
    return width_cv(separator_widths(gaps))


def photo_widths_from_gap_edges(
    gaps: list[Gap],
    origin: float,
    pitch: float,
    count: int,
) -> list[float] | None:
    if count <= 0 or pitch <= 0.0:
        return None
    if count == 1:
        return None
    by_index = {int(gap.index): gap for gap in gaps}
    widths: list[float] = []
    left_edge = float(origin)
    for index in range(1, count):
        gap = by_index.get(index)
        if gap is None or gap.start is None or gap.end is None:
            return None
        start = float(gap.start)
        end = float(gap.end)
        if start < left_edge or end < start:
            return None
        widths.append(start - left_edge)
        left_edge = end
    right_edge = float(origin + pitch * count)
    if right_edge < left_edge:
        return None
    widths.append(right_edge - left_edge)
    if len(widths) != count or any(width <= 1.0 for width in widths):
        return None
    return widths
