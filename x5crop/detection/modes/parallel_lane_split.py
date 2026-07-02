from __future__ import annotations

import numpy as np

from ...domain import Box


def translate_work_box(box: Box, offset_x: int, offset_y: int) -> Box:
    return Box(
        box.left + offset_x,
        box.top + offset_y,
        box.right + offset_x,
        box.bottom + offset_y,
    )


def split_parallel_strip_lanes(gray_work: np.ndarray, lane_count: int) -> list[Box]:
    if lane_count != 2:
        raise ValueError("parallel lane detector supports exactly two lanes")

    h, w = gray_work.shape
    split_y = h // 2
    return [Box(0, 0, w, split_y), Box(0, split_y, w, h)]


__all__ = [
    "split_parallel_strip_lanes",
    "translate_work_box",
]
