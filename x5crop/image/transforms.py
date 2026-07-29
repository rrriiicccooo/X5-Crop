from __future__ import annotations

import numpy as np

from ..domain import Box
from ..geometry.affine import AffineCoordinateTransform
from ..utils import spatial_shape


AFFINE_ROW_CHUNK_SIZE = 256
BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX = 1.0


def _dtype_limits(dtype: np.dtype) -> tuple[int, int] | None:
    if np.issubdtype(dtype, np.bool_):
        return (0, 1)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return int(info.min), int(info.max)
    return None


def photometric_background_value(
    arr: np.ndarray,
    photometric: str,
) -> int | float:
    limits = _dtype_limits(arr.dtype)
    minimum_is_white = photometric.upper() == "MINISWHITE"
    if limits is not None:
        return limits[0] if minimum_is_white else limits[1]
    finite = arr[np.isfinite(arr)]
    if not finite.size:
        raise ValueError("affine background requires finite image samples")
    return float(finite.min() if minimum_is_white else finite.max())


def _cast_interpolated(value: np.ndarray, dtype: np.dtype) -> np.ndarray:
    limits = _dtype_limits(dtype)
    if limits is not None:
        value = np.clip(value, limits[0], limits[1])
    return value.astype(dtype)


def sample_affine_roi(
    arr: np.ndarray,
    axes: str,
    transform: AffineCoordinateTransform,
    box: Box,
    *,
    background_value: int | float,
) -> np.ndarray:
    """Sample one half-open output ROI through the supplied affine transform."""
    source_height, source_width = spatial_shape(arr)
    if (source_width, source_height) != (
        transform.source_extent.width,
        transform.source_extent.height,
    ):
        raise ValueError("affine source array must match the transform extent")
    if (
        not box.valid()
        or box.left < 0
        or box.top < 0
        or box.right > transform.output_extent.width
        or box.bottom > transform.output_extent.height
    ):
        raise ValueError("affine ROI must lie inside the expanded output domain")
    if axes == "SYX":
        sampled = sample_affine_roi(
            np.moveaxis(arr, 0, -1),
            "YXS",
            transform,
            box,
            background_value=background_value,
        )
        return np.moveaxis(sampled, -1, 0)
    if arr.ndim == 2:
        if axes != "YX":
            raise ValueError(f"Unsupported axes for grayscale affine sampling: {axes}")
    elif arr.ndim == 3:
        if axes != "YXS":
            raise ValueError(f"Unsupported axes for image affine sampling: {axes}")
    else:
        raise ValueError("affine sampling requires a 2D or 3D image")
    if transform.is_identity:
        return arr[box.top : box.bottom, box.left : box.right]
    output_shape = (box.height, box.width) + tuple(arr.shape[2:])
    output = np.full(output_shape, background_value, dtype=arr.dtype)
    inverse = transform.inverse_matrix
    for output_row in range(0, box.height, AFFINE_ROW_CHUNK_SIZE):
        row_end = min(box.height, output_row + AFFINE_ROW_CHUNK_SIZE)
        expanded_y = np.arange(
            box.top + output_row,
            box.top + row_end,
            dtype=np.float64,
        )[:, None]
        expanded_x = np.arange(
            box.left,
            box.right,
            dtype=np.float64,
        )[None, :]
        source_x = (
            inverse[0][0] * expanded_x
            + inverse[0][1] * expanded_y
            + inverse[0][2]
        )
        source_y = (
            inverse[1][0] * expanded_x
            + inverse[1][1] * expanded_y
            + inverse[1][2]
        )
        valid = (
            (source_x >= 0.0)
            & (source_x <= source_width - 1)
            & (source_y >= 0.0)
            & (source_y <= source_height - 1)
        )
        if not valid.any():
            continue
        x0 = np.clip(
            np.floor(source_x).astype(np.int64),
            0,
            source_width - 1,
        )
        y0 = np.clip(
            np.floor(source_y).astype(np.int64),
            0,
            source_height - 1,
        )
        x1 = np.clip(x0 + 1, 0, source_width - 1)
        y1 = np.clip(y0 + 1, 0, source_height - 1)
        weight_x = source_x - x0
        weight_y = source_y - y0
        if arr.ndim == 2:
            value = (
                arr[y0, x0] * (1.0 - weight_x) * (1.0 - weight_y)
                + arr[y0, x1] * weight_x * (1.0 - weight_y)
                + arr[y1, x0] * (1.0 - weight_x) * weight_y
                + arr[y1, x1] * weight_x * weight_y
            )
        else:
            value = (
                arr[y0, x0].astype(np.float64)
                * ((1.0 - weight_x) * (1.0 - weight_y))[..., None]
                + arr[y0, x1].astype(np.float64)
                * (weight_x * (1.0 - weight_y))[..., None]
                + arr[y1, x0].astype(np.float64)
                * ((1.0 - weight_x) * weight_y)[..., None]
                + arr[y1, x1].astype(np.float64)
                * (weight_x * weight_y)[..., None]
            )
        chunk = output[output_row:row_end]
        chunk[valid] = _cast_interpolated(value[valid], arr.dtype)
    return output
