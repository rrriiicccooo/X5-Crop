from __future__ import annotations

import numpy as np
from scipy.ndimage import map_coordinates

from ..domain import Box
from ..geometry.affine import AffineCoordinateTransform


AFFINE_ROW_CHUNK_SIZE = 256
AFFINE_SAMPLE_MAX_VALUE = int(np.iinfo(np.uint16).max)
# Black remains the sampling primitive's explicit no-source-data value.  The
# production Gate separately requires every official output sample centre to
# inverse-map inside lane authority, so this fallback cannot silently create
# black corners in an automatically approved TIFF.
AFFINE_BACKGROUND_VALUE = 0


def sample_affine_roi(
    arr: np.ndarray,
    transform: AffineCoordinateTransform,
    box: Box,
    *,
    sampling_authority_box: Box,
) -> np.ndarray:
    """Sample one half-open output ROI through the supplied affine transform."""
    if arr.dtype != np.dtype("uint16") or arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("affine sampling requires uint16 RGB YXS input")
    source_height, source_width = arr.shape[:2]
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
    if (
        transform.is_identity
        and sampling_authority_box.left <= box.left
        and sampling_authority_box.top <= box.top
        and sampling_authority_box.right >= box.right
        and sampling_authority_box.bottom >= box.bottom
    ):
        return arr[box.top : box.bottom, box.left : box.right]
    output_shape = (box.height, box.width) + tuple(arr.shape[2:])
    background_value = AFFINE_BACKGROUND_VALUE
    output = np.full(output_shape, background_value, dtype=arr.dtype)
    inverse = transform.inverse_matrix
    authority = arr[
        sampling_authority_box.top : sampling_authority_box.bottom,
        sampling_authority_box.left : sampling_authority_box.right,
    ]
    expanded_x = np.arange(
        box.left,
        box.right,
        dtype=np.float64,
    )[None, :]
    for output_row in range(0, box.height, AFFINE_ROW_CHUNK_SIZE):
        row_end = min(box.height, output_row + AFFINE_ROW_CHUNK_SIZE)
        expanded_y = np.arange(
            box.top + output_row,
            box.top + row_end,
            dtype=np.float64,
        )[:, None]
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
        coordinates = np.asarray(
            (
                source_y - sampling_authority_box.top,
                source_x - sampling_authority_box.left,
            ),
            dtype=np.float64,
        )
        value = np.empty(source_x.shape, dtype=np.float64)
        for channel in range(arr.shape[2]):
            map_coordinates(
                authority[..., channel],
                coordinates,
                order=1,
                mode="grid-constant",
                cval=float(background_value),
                prefilter=False,
                output=value,
            )
            np.clip(value, 0, AFFINE_SAMPLE_MAX_VALUE, out=value)
            output[output_row:row_end, :, channel] = value.astype(arr.dtype)
    return output
