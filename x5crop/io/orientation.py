from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


SUPPORTED_TIFF_ORIENTATIONS = frozenset(range(1, 9))


@dataclass(frozen=True)
class OrientationMapping:
    """Reversible raw-raster to canonical-visual pixel-center mapping."""

    original_tag: int
    raw_width: int
    raw_height: int
    canonical_width: int
    canonical_height: int
    raw_to_canonical: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    canonical_to_raw: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]

    def __post_init__(self) -> None:
        if (
            self.original_tag not in SUPPORTED_TIFF_ORIENTATIONS
            or self.raw_width <= 0
            or self.raw_height <= 0
            or self.canonical_width <= 0
            or self.canonical_height <= 0
        ):
            raise ValueError("TIFF orientation mapping is invalid")
        for matrix in (self.raw_to_canonical, self.canonical_to_raw):
            values = tuple(value for row in matrix for value in row)
            if (
                any(not math.isfinite(value) for value in values)
                or matrix[2] != (0.0, 0.0, 1.0)
            ):
                raise ValueError("TIFF orientation mapping must be affine")

    def map_raw_point(self, x: float, y: float) -> tuple[float, float]:
        return _map_point(self.raw_to_canonical, x, y)

    def map_canonical_point(self, x: float, y: float) -> tuple[float, float]:
        return _map_point(self.canonical_to_raw, x, y)

    def as_record(self) -> dict[str, object]:
        return {
            "original_tag": self.original_tag,
            "output_tag": 1,
            "raw_extent": {
                "width": self.raw_width,
                "height": self.raw_height,
            },
            "canonical_extent": {
                "width": self.canonical_width,
                "height": self.canonical_height,
            },
            "raw_to_canonical": [list(row) for row in self.raw_to_canonical],
            "canonical_to_raw": [list(row) for row in self.canonical_to_raw],
        }


def _map_point(
    matrix: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
    x: float,
    y: float,
) -> tuple[float, float]:
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("TIFF orientation coordinates must be finite")
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
    )


def orientation_mapping(
    orientation: int | None,
    raw_width: int,
    raw_height: int,
) -> OrientationMapping:
    tag = 1 if orientation is None else int(orientation)
    if tag not in SUPPORTED_TIFF_ORIENTATIONS:
        raise ValueError(f"Unsupported TIFF Orientation: {tag}")
    if raw_width <= 0 or raw_height <= 0:
        raise ValueError("TIFF orientation requires a positive raw extent")

    w = float(raw_width - 1)
    h = float(raw_height - 1)
    matrices = {
        1: ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        2: ((-1.0, 0.0, w), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        3: ((-1.0, 0.0, w), (0.0, -1.0, h), (0.0, 0.0, 1.0)),
        4: ((1.0, 0.0, 0.0), (0.0, -1.0, h), (0.0, 0.0, 1.0)),
        5: ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        6: ((0.0, -1.0, h), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        7: ((0.0, -1.0, h), (-1.0, 0.0, w), (0.0, 0.0, 1.0)),
        8: ((0.0, 1.0, 0.0), (-1.0, 0.0, w), (0.0, 0.0, 1.0)),
    }
    inverses = {
        1: matrices[1],
        2: matrices[2],
        3: matrices[3],
        4: matrices[4],
        5: matrices[5],
        6: ((0.0, 1.0, 0.0), (-1.0, 0.0, h), (0.0, 0.0, 1.0)),
        7: ((0.0, -1.0, w), (-1.0, 0.0, h), (0.0, 0.0, 1.0)),
        8: ((0.0, -1.0, w), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    }
    swaps_axes = tag in {5, 6, 7, 8}
    return OrientationMapping(
        original_tag=tag,
        raw_width=raw_width,
        raw_height=raw_height,
        canonical_width=raw_height if swaps_axes else raw_width,
        canonical_height=raw_width if swaps_axes else raw_height,
        raw_to_canonical=matrices[tag],
        canonical_to_raw=inverses[tag],
    )


def canonicalize_orientation(
    raw: np.ndarray,
    axes: str,
    orientation: int | None,
) -> tuple[np.ndarray, OrientationMapping]:
    if axes not in {"YX", "YXS"}:
        raise ValueError("V5 orientation canonicalization requires YX or YXS")
    if raw.ndim != len(axes):
        raise ValueError("TIFF axes do not match the raw raster")
    raw_height, raw_width = int(raw.shape[0]), int(raw.shape[1])
    mapping = orientation_mapping(orientation, raw_width, raw_height)
    tag = mapping.original_tag
    if tag == 1:
        canonical = raw
    elif tag == 2:
        canonical = np.flip(raw, axis=1)
    elif tag == 3:
        canonical = np.flip(raw, axis=(0, 1))
    elif tag == 4:
        canonical = np.flip(raw, axis=0)
    elif tag == 5:
        canonical = np.swapaxes(raw, 0, 1)
    elif tag == 6:
        canonical = np.rot90(raw, k=3, axes=(0, 1))
    elif tag == 7:
        canonical = np.flip(np.swapaxes(raw, 0, 1), axis=(0, 1))
    else:
        canonical = np.rot90(raw, k=1, axes=(0, 1))
    return np.ascontiguousarray(canonical), mapping
