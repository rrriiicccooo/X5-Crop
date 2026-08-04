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
    sampling_authority_box: Box,
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
    if (
        not sampling_authority_box.valid()
        or sampling_authority_box.left < 0
        or sampling_authority_box.top < 0
        or sampling_authority_box.right > source_width
        or sampling_authority_box.bottom > source_height
    ):
        raise ValueError("sampling authority must lie inside the source extent")
    if axes == "SYX":
        sampled = sample_affine_roi(
            np.moveaxis(arr, 0, -1),
            "YXS",
            transform,
            box,
            background_value=background_value,
            sampling_authority_box=sampling_authority_box,
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
    if (
        transform.is_identity
        and sampling_authority_box.left <= box.left
        and sampling_authority_box.top <= box.top
        and sampling_authority_box.right >= box.right
        and sampling_authority_box.bottom >= box.bottom
    ):
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
        x0 = np.floor(source_x).astype(np.int64)
        y0 = np.floor(source_y).astype(np.int64)
        x1 = x0 + 1
        y1 = y0 + 1
        weight_x = source_x - x0
        weight_y = source_y - y0
        sample_shape = source_x.shape + tuple(arr.shape[2:])

        def tap(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            valid = (
                (x >= sampling_authority_box.left)
                & (x < sampling_authority_box.right)
                & (y >= sampling_authority_box.top)
                & (y < sampling_authority_box.bottom)
                & (x >= 0)
                & (x < source_width)
                & (y >= 0)
                & (y < source_height)
            )
            values = np.full(
                sample_shape,
                background_value,
                dtype=np.float64,
            )
            if valid.any():
                values[valid] = arr[y[valid], x[valid]]
            return values

        weights = (
            (1.0 - weight_x) * (1.0 - weight_y),
            weight_x * (1.0 - weight_y),
            (1.0 - weight_x) * weight_y,
            weight_x * weight_y,
        )
        taps = (
            tap(x0, y0),
            tap(x1, y0),
            tap(x0, y1),
            tap(x1, y1),
        )
        if arr.ndim == 2:
            value = sum(
                sample * weight
                for sample, weight in zip(taps, weights, strict=True)
            )
        else:
            value = sum(
                sample * weight[..., None]
                for sample, weight in zip(taps, weights, strict=True)
            )
        output[output_row:row_end] = _cast_interpolated(value, arr.dtype)
    return output
