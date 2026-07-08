from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..utils import sampled_values_for_percentile


@dataclass(frozen=True)
class BaseGrayParameters:
    red_weight: float = 0.2126
    green_weight: float = 0.7152
    blue_weight: float = 0.0722
    low_percentile: float = 0.2
    high_percentile: float = 99.8
    miniswhite_inverts: bool = True


def make_base_gray_u8(
    arr: np.ndarray,
    axes: str,
    photometric: str,
    params: BaseGrayParameters,
) -> np.ndarray:
    if axes == "YX":
        gray = arr
    elif axes == "YXS":
        rgb = arr[..., :3].astype(np.float32)
        gray = (
            params.red_weight * rgb[..., 0]
            + params.green_weight * rgb[..., 1]
            + params.blue_weight * rgb[..., 2]
        )
    elif axes == "SYX":
        rgb = arr[:3, ...].astype(np.float32)
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
    finite_values = sampled_values_for_percentile(gray[finite])
    lo, hi = np.percentile(finite_values, [params.low_percentile, params.high_percentile])
    if hi <= lo:
        hi = float(finite_values.max())
        lo = float(finite_values.min())
    if hi <= lo:
        out = np.zeros(gray.shape, dtype=np.uint8)
    else:
        out = np.clip((gray - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    if params.miniswhite_inverts and photometric.upper() == "MINISWHITE":
        out = 255 - out
    return out


__all__ = [
    "BaseGrayParameters",
    "make_base_gray_u8",
]
