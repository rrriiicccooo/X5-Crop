from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import UINT8_MAX_VALUE
from ..utils import (
    RGB_CHANNEL_COUNT,
    require_nonnegative,
    require_percentile,
    require_positive,
    sampled_values_for_percentile,
)


@dataclass(frozen=True)
class BaseGrayParameters:
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
    axes: str,
    photometric: str,
    params: BaseGrayParameters,
) -> np.ndarray:
    if axes == "YX":
        gray = arr
    elif axes == "YXS":
        rgb = arr[..., :RGB_CHANNEL_COUNT].astype(np.float32)
        gray = (
            params.red_weight * rgb[..., 0]
            + params.green_weight * rgb[..., 1]
            + params.blue_weight * rgb[..., 2]
        )
    elif axes == "SYX":
        rgb = arr[:RGB_CHANNEL_COUNT, ...].astype(np.float32)
        gray = (
            params.red_weight * rgb[0]
            + params.green_weight * rgb[1]
            + params.blue_weight * rgb[2]
        )
    else:
        raise ValueError(f"Unsupported axes: {axes}")

    gray = gray.astype(np.float32, copy=False)
    finite = np.isfinite(gray)
    if not finite.any():
        return np.zeros(gray.shape, dtype=np.uint8)
    finite_values = sampled_values_for_percentile(
        gray[finite],
        params.maximum_percentile_samples,
    )
    lo, hi = np.percentile(finite_values, [params.low_percentile, params.high_percentile])
    if hi <= lo:
        hi = float(finite_values.max())
        lo = float(finite_values.min())
    if hi <= lo:
        out = np.zeros(gray.shape, dtype=np.uint8)
    else:
        out = np.clip(
            (gray - lo) * (UINT8_MAX_VALUE / (hi - lo)),
            0,
            UINT8_MAX_VALUE,
        ).astype(np.uint8)
    if photometric.upper() == "MINISWHITE":
        out = int(UINT8_MAX_VALUE) - out
    return out
