from __future__ import annotations

import numpy as np

from ..domain import Box
from ..geometry.affine import AffineCoordinateTransform


AFFINE_ROW_CHUNK_SIZE = 256
# Black is the sampling primitive's explicit no-source-data value.  It appears
# only in the representational corners of the axis-aligned envelope around a
# rotated, already-safe source polygon; deskew never changes crop authority.
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
    # Keep SciPy out of the exact-slice path.  Review-only sources never reach
    # affine sampling, and an identity crop should not pay for ndimage import.
    from scipy.ndimage import map_coordinates

    output_shape = (box.height, box.width) + tuple(arr.shape[2:])
    background_value = AFFINE_BACKGROUND_VALUE
    # Every channel of every output row is filled below.  Initializing the
    # complete crop first only adds one full-memory write before sampling.
    output = np.empty(output_shape, dtype=arr.dtype)
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
    maximum_chunk_rows = min(AFFINE_ROW_CHUNK_SIZE, box.height)
    coordinates = np.empty(
        (2, maximum_chunk_rows, box.width),
        dtype=np.float64,
    )
    value = np.empty((maximum_chunk_rows, box.width), dtype=np.float64)
    for output_row in range(0, box.height, AFFINE_ROW_CHUNK_SIZE):
        row_end = min(box.height, output_row + AFFINE_ROW_CHUNK_SIZE)
        row_count = row_end - output_row
        expanded_y = np.arange(
            box.top + output_row,
            box.top + row_end,
            dtype=np.float64,
        )[:, None]
        chunk_coordinates = coordinates[:, :row_count]
        np.multiply(
            expanded_x,
            inverse[1][0],
            out=chunk_coordinates[0],
        )
        chunk_coordinates[0] += inverse[1][1] * expanded_y
        chunk_coordinates[0] += inverse[1][2]
        chunk_coordinates[0] -= sampling_authority_box.top
        np.multiply(
            expanded_x,
            inverse[0][0],
            out=chunk_coordinates[1],
        )
        chunk_coordinates[1] += inverse[0][1] * expanded_y
        chunk_coordinates[1] += inverse[0][2]
        chunk_coordinates[1] -= sampling_authority_box.left
        chunk_value = value[:row_count]
        for channel in range(arr.shape[2]):
            map_coordinates(
                authority[..., channel],
                chunk_coordinates,
                order=1,
                mode="grid-constant",
                cval=float(background_value),
                prefilter=False,
                output=chunk_value,
            )
            # Order-1 interpolation is a convex combination of uint16 source
            # values and the zero background, so it already lies in the uint16
            # range.  NumPy assignment preserves the former truncation rule
            # without allocating a second uint16 chunk.
            output[output_row:row_end, :, channel] = chunk_value
    return output
