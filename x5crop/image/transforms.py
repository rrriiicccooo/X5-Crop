from __future__ import annotations

import math

import numpy as np

from ..utils import spatial_shape


def dtype_white(dtype: np.dtype) -> int | float:
    if np.issubdtype(dtype, np.integer):
        return int(np.iinfo(dtype).max)
    return 1.0


def rotate_array_expand(arr: np.ndarray, angle_degrees: float, axes: str) -> np.ndarray:
    if abs(angle_degrees) < 1e-9:
        return arr
    if axes == "SYX":
        rotated = rotate_array_expand(np.moveaxis(arr, 0, -1), angle_degrees, "YXS")
        return np.moveaxis(rotated, -1, 0)
    angle = math.radians(angle_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    h, w = spatial_shape(arr)
    corners = np.array(
        [[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]],
        dtype=np.float64,
    )
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    centered = corners - np.array([cx, cy])
    rot = np.column_stack(
        [
            centered[:, 0] * cos_a - centered[:, 1] * sin_a,
            centered[:, 0] * sin_a + centered[:, 1] * cos_a,
        ]
    )
    min_xy = rot.min(axis=0)
    max_xy = rot.max(axis=0)
    out_w = int(math.ceil(max_xy[0] - min_xy[0] + 1))
    out_h = int(math.ceil(max_xy[1] - min_xy[1] + 1))
    out_shape = (out_h, out_w) + tuple(arr.shape[2:])
    out = np.full(out_shape, dtype_white(arr.dtype), dtype=arr.dtype)

    out_cx = (out_w - 1) / 2.0
    out_cy = (out_h - 1) / 2.0
    chunk = 256
    for y0 in range(0, out_h, chunk):
        y1 = min(out_h, y0 + chunk)
        yy, xx = np.mgrid[y0:y1, 0:out_w].astype(np.float64)
        x_rel = xx - out_cx
        y_rel = yy - out_cy
        src_x = x_rel * cos_a + y_rel * sin_a + cx
        src_y = -x_rel * sin_a + y_rel * cos_a + cy
        valid = (src_x >= 0) & (src_x <= w - 1) & (src_y >= 0) & (src_y <= h - 1)
        if not valid.any():
            continue
        x0f = np.floor(src_x).astype(np.int64)
        y0f = np.floor(src_y).astype(np.int64)
        x1f = np.clip(x0f + 1, 0, w - 1)
        y1f = np.clip(y0f + 1, 0, h - 1)
        x0f = np.clip(x0f, 0, w - 1)
        y0f = np.clip(y0f, 0, h - 1)
        wx = src_x - x0f
        wy = src_y - y0f
        if arr.ndim == 2:
            value = (
                arr[y0f, x0f] * (1 - wx) * (1 - wy)
                + arr[y0f, x1f] * wx * (1 - wy)
                + arr[y1f, x0f] * (1 - wx) * wy
                + arr[y1f, x1f] * wx * wy
            )
            out[y0:y1, :][valid] = np.clip(value[valid], 0, dtype_white(arr.dtype)).astype(arr.dtype)
        elif axes == "YXS":
            value = (
                arr[y0f, x0f].astype(np.float64) * ((1 - wx) * (1 - wy))[..., None]
                + arr[y0f, x1f].astype(np.float64) * (wx * (1 - wy))[..., None]
                + arr[y1f, x0f].astype(np.float64) * ((1 - wx) * wy)[..., None]
                + arr[y1f, x1f].astype(np.float64) * (wx * wy)[..., None]
            )
            out_chunk = out[y0:y1, :]
            out_chunk[valid] = np.clip(value[valid], 0, dtype_white(arr.dtype)).astype(arr.dtype)
        else:
            raise ValueError(f"Unsupported axes for deskew rotation: {axes}")
    return out
