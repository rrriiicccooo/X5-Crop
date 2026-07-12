from __future__ import annotations

import numpy as np

HORIZONTAL = "horizontal"
VERTICAL = "vertical"
WORK_LAYOUTS = frozenset({HORIZONTAL, VERTICAL})


def require_work_layout(layout: str) -> str:
    if layout not in WORK_LAYOUTS:
        raise ValueError(f"unsupported work layout: {layout}")
    return layout


def is_horizontal_layout(layout: str) -> bool:
    return require_work_layout(layout) == HORIZONTAL


def infer_layout(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("layout inference requires positive image dimensions")
    return HORIZONTAL if width >= height else VERTICAL


def work_gray(gray: np.ndarray, layout: str) -> np.ndarray:
    if gray.ndim != 2:
        raise ValueError("work gray must be a two-dimensional image")
    return gray if is_horizontal_layout(layout) else np.ascontiguousarray(gray.T)
