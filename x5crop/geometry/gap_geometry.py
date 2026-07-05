from __future__ import annotations

import numpy as np

from ..domain import Gap
from ..gap_methods import is_hard_gap_method
from ..utils import clamp_float
from .detection_parameters import RobustGridParameters
from .model_gaps import equal_model_gap


def constrain_gap_to_geometry(
    gap: Gap,
    expected: float,
    pitch: float,
    strip_mode: str,
    robust_grid: RobustGridParameters | None = None,
) -> Gap:
    if not is_hard_gap_method(gap.method):
        return equal_model_gap(gap.index, expected, gap.score)
    config = robust_grid or RobustGridParameters()
    max_shift = clamp_float(
        pitch * (config.constrain_full_shift_ratio if strip_mode == "full" else config.constrain_partial_shift_ratio),
        config.constrain_shift_min,
        config.constrain_shift_max,
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
    "local_gap_geometry_error",
]
