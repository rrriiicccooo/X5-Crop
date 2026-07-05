from __future__ import annotations

import numpy as np

from ..utils import sampled_values_for_percentile


def make_base_gray_u8(arr: np.ndarray, axes: str, photometric: str) -> np.ndarray:
    if axes == "YX":
        gray = arr
    elif axes == "YXS":
        rgb = arr[..., :3].astype(np.float32)
        gray = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    elif axes == "SYX":
        rgb = arr[:3, ...].astype(np.float32)
        gray = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    else:
        raise ValueError(f"Unsupported axes: {axes}")

    gray = gray.astype(np.float32, copy=False)
    finite = np.isfinite(gray)
    if not finite.any():
        return np.zeros(gray.shape, dtype=np.uint8)
    finite_values = sampled_values_for_percentile(gray[finite])
    lo, hi = np.percentile(finite_values, [0.2, 99.8])
    if hi <= lo:
        hi = float(finite_values.max())
        lo = float(finite_values.min())
    if hi <= lo:
        out = np.zeros(gray.shape, dtype=np.uint8)
    else:
        out = np.clip((gray - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    if photometric.upper() == "MINISWHITE":
        out = 255 - out
    return out


__all__ = [
    "make_base_gray_u8",
]
