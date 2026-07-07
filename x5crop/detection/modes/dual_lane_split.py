from __future__ import annotations

import numpy as np

from ...domain import Box


def split_dual_lanes(gray_work: np.ndarray, lane_count: int) -> list[Box]:
    if lane_count != 2:
        raise ValueError("dual lane detector supports exactly two lanes")

    h, w = gray_work.shape
    split_y = h // 2
    return [Box(0, 0, w, split_y), Box(0, split_y, w, h)]


__all__ = [
    "split_dual_lanes",
]
