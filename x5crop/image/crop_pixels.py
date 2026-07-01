from __future__ import annotations

import numpy as np

from ..domain import Box


def crop_array(arr: np.ndarray, axes: str, box: Box) -> np.ndarray:
    if axes == "YX":
        return arr[box.top:box.bottom, box.left:box.right]
    if axes == "YXS":
        return arr[box.top:box.bottom, box.left:box.right, :]
    if axes == "SYX":
        return arr[:, box.top:box.bottom, box.left:box.right]
    raise ValueError(f"Unsupported axes: {axes}")


def validate_source_crop_pixels(source_arr: np.ndarray, axes: str, box: Box, cropped: np.ndarray) -> None:
    expected = np.ascontiguousarray(crop_array(source_arr, axes, box))
    if expected.dtype != cropped.dtype or tuple(expected.shape) != tuple(cropped.shape):
        raise RuntimeError(
            f"Source crop validation failed: expected {expected.shape}/{expected.dtype}, "
            f"got {cropped.shape}/{cropped.dtype}"
        )
    if not np.array_equal(expected, cropped):
        raise RuntimeError("Source crop validation failed: cropped pixels differ from source")
