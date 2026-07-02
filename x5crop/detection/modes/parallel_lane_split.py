from __future__ import annotations

import numpy as np

from ...domain import Box
from ...utils import bbox_from_mask


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
    content = bbox_from_mask(gray_work < 246, min_row_fraction=0.010, min_col_fraction=0.010)
    if content is None or not content.valid():
        content = Box(0, 0, w, h)

    split_y = int(round((content.top + content.bottom) / 2.0))
    guard = max(2, min(80, int(round(content.height * 0.006))))
    lanes = [
        Box(content.left, content.top, content.right, max(content.top + 1, split_y - guard)).clamp(w, h),
        Box(content.left, min(content.bottom - 1, split_y + guard), content.right, content.bottom).clamp(w, h),
    ]
    if any(not lane.valid() or lane.height < max(20, h * 0.10) for lane in lanes):
        split_y = h // 2
        lanes = [Box(0, 0, w, split_y), Box(0, split_y, w, h)]
    return lanes


__all__ = [
    "split_parallel_strip_lanes",
    "translate_work_box",
]
