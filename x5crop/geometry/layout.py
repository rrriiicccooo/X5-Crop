from __future__ import annotations

import numpy as np


def infer_layout(width: int, height: int) -> str:
    return "horizontal" if width >= height else "vertical"


def work_gray(gray: np.ndarray, layout: str) -> np.ndarray:
    return gray if layout == "horizontal" else np.ascontiguousarray(gray.T)
