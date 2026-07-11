from __future__ import annotations

import numpy as np

from ..domain import SeparatorBandObservation


def width_cv(widths: list[float]) -> float:
    values = np.array(widths, dtype=np.float64)
    if values.size <= 1:
        return 0.0
    if np.any(values <= 1.0):
        return 1.0
    return float(values.std() / max(1.0, values.mean()))


def separator_widths(gaps: list[SeparatorBandObservation]) -> list[float]:
    return [
        float(gap.width)
        for gap in gaps
        if gap.start is not None and gap.end is not None and gap.width > 1.0
    ]


def measured_photo_widths_from_gap_edges(
    gaps: list[SeparatorBandObservation],
    origin: float,
    pitch: float,
    count: int,
) -> list[float] | None:
    if count <= 0 or pitch <= 0.0:
        return None
    if count == 1:
        return None
    by_index = {
        int(gap.index): gap
        for gap in gaps
        if gap.start is not None and gap.end is not None
    }
    widths: list[float] = []
    right_edge = float(origin + pitch * count)
    first = by_index.get(1)
    if first is not None:
        width = float(first.start) - float(origin)
        if width > 1.0:
            widths.append(width)
    for index in range(1, count - 1):
        left = by_index.get(index)
        right = by_index.get(index + 1)
        if left is None or right is None:
            continue
        width = float(right.start) - float(left.end)
        if width > 1.0:
            widths.append(width)
    last = by_index.get(count - 1)
    if last is not None:
        width = right_edge - float(last.end)
        if width > 1.0:
            widths.append(width)
    return widths if len(widths) >= 2 else None
