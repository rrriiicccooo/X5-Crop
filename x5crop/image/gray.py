from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .constants import UINT8_MAX_VALUE
from ..utils import (
    RGB_CHANNEL_COUNT,
    require_nonnegative,
    require_percentile,
    require_positive,
)


GRAY_ROW_CHUNK_SIZE = 128


@dataclass(frozen=True)
class BaseGrayParameters:
    """Registered-gray calibration used only by pixel measurement.

    Rec.709 luma coefficients preserve channel meaning.  Percentile clipping
    is an explicit robust display-domain normalization; it creates no edge,
    content, placement, or Gate authority.
    """
    red_weight: float = 0.2126
    green_weight: float = 0.7152
    blue_weight: float = 0.0722
    low_percentile: float = 0.2
    high_percentile: float = 99.8
    maximum_percentile_samples: int = 1_000_000

    def __post_init__(self) -> None:
        for name, value in (
            ("red luma weight", self.red_weight),
            ("green luma weight", self.green_weight),
            ("blue luma weight", self.blue_weight),
        ):
            require_nonnegative(name, value)
        if self.red_weight + self.green_weight + self.blue_weight <= 0.0:
            raise ValueError("luma weights must contain positive support")
        require_percentile("gray low percentile", self.low_percentile)
        require_percentile("gray high percentile", self.high_percentile)
        if self.high_percentile <= self.low_percentile:
            raise ValueError("gray high percentile must follow low percentile")
        require_positive(
            "gray percentile sample budget",
            self.maximum_percentile_samples,
        )


def make_base_gray_u8(
    arr: np.ndarray,
    params: BaseGrayParameters,
) -> np.ndarray:
    if (
        arr.dtype != np.dtype("uint16")
        or arr.ndim != 3
        or arr.shape[2] != RGB_CHANNEL_COUNT
    ):
        raise ValueError("registered gray requires uint16 RGB YXS input")

    height, width = arr.shape[:2]
    sample_step = max(
        1,
        math.ceil(
            height * width / params.maximum_percentile_samples
        ),
    )
    if arr.flags.c_contiguous:
        sampled_rgb = arr.reshape(-1, RGB_CHANNEL_COUNT)[::sample_step]
    else:
        positions = np.arange(
            0,
            height * width,
            sample_step,
            dtype=np.int64,
        )
        rows, columns = np.divmod(positions, width)
        sampled_rgb = arr[rows, columns]
    sampled_rgb = sampled_rgb.astype(np.float32)
    finite_values = (
        params.red_weight * sampled_rgb[:, 0]
        + params.green_weight * sampled_rgb[:, 1]
        + params.blue_weight * sampled_rgb[:, 2]
    )
    lo, hi = np.percentile(finite_values, [params.low_percentile, params.high_percentile])
    if hi <= lo:
        hi = float(finite_values.max())
        lo = float(finite_values.min())
    if hi <= lo:
        out = np.zeros((height, width), dtype=np.uint8)
    else:
        out = np.empty((height, width), dtype=np.uint8)
        scale = UINT8_MAX_VALUE / (hi - lo)
        for start in range(0, height, GRAY_ROW_CHUNK_SIZE):
            stop = min(height, start + GRAY_ROW_CHUNK_SIZE)
            rgb = arr[start:stop].astype(np.float32)
            values = (
                params.red_weight * rgb[..., 0]
                + params.green_weight * rgb[..., 1]
                + params.blue_weight * rgb[..., 2]
            )
            out[start:stop] = np.clip(
                (values - lo) * scale,
                0,
                UINT8_MAX_VALUE,
            ).astype(np.uint8)
    return out
