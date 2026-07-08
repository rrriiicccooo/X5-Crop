from __future__ import annotations

import numpy as np

from ..domain import Gap
from ..gap_methods import is_hard_gap_method
from ..utils import clamp_float
from .detection_parameters import GapGeometryConstraintParameters
from .model_gaps import equal_model_gap


def constrain_gap_to_geometry(
    gap: Gap,
    expected: float,
    pitch: float,
    parameters: GapGeometryConstraintParameters,
) -> Gap:
    if not is_hard_gap_method(gap.method):
        return equal_model_gap(gap.index, expected, gap.score)
    max_shift = clamp_float(
        pitch * parameters.shift_ratio,
        parameters.shift_min,
        parameters.shift_max,
    )
    shift = max(-max_shift, min(max_shift, gap.center - expected))
    center = float(expected + shift)
    method = gap.method
    if gap.start is not None and gap.end is not None:
        delta = center - float(gap.center)
        start = float(gap.start + delta)
        end = float(gap.end + delta)
    else:
        start = None
        end = None
    return Gap(gap.index, center, gap.score, method, start, end)


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
        return [float(pitch)]
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


def photo_width_cv_from_gap_edges(
    gaps: list[Gap],
    origin: float,
    pitch: float,
    count: int,
) -> float | None:
    widths = photo_widths_from_gap_edges(gaps, origin, pitch, count)
    if widths is None:
        return None
    return width_cv(widths)


def local_gap_geometry_error(gaps: list[Gap], gap_index: int, origin: float, pitch: float, count: int) -> float:
    if count <= 1 or gap_index < 1 or gap_index >= count:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    left_w = cuts[gap_index] - cuts[gap_index - 1]
    right_w = cuts[gap_index + 1] - cuts[gap_index]
    if left_w <= 1 or right_w <= 1:
        return float("inf")
    return abs(left_w - pitch) + abs(right_w - pitch)


__all__ = [
    "constrain_gap_to_geometry",
    "gap_width_cv",
    "photo_width_cv_from_gap_edges",
    "photo_widths_from_gap_edges",
    "separator_width_cv",
    "separator_widths",
    "local_gap_geometry_error",
    "width_cv",
]
