from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np


PERCENTILE_MAX = 100.0
RGB_CHANNEL_COUNT = 3
RGBA_CHANNEL_COUNT = 4
SUPPORTED_COLOR_CHANNEL_COUNTS = (RGB_CHANNEL_COUNT, RGBA_CHANNEL_COUNT)


def require_positive(name: str, value: int | float) -> None:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be positive")


def require_nonnegative(name: str, value: int | float) -> None:
    if not math.isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{name} must be non-negative")


def require_percentile(name: str, value: int | float) -> None:
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= PERCENTILE_MAX:
        raise ValueError(f"{name} must be within [0, 100]")


def require_unit_interval(name: str, value: int | float) -> None:
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be within [0, 1]")


def enum_name(value: Any, default: str = "") -> str:
    return str(getattr(value, "name", value) or default)


def planar_config_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    name = enum_name(value, "")
    upper = name.upper()
    if upper in {"1", "CONTIG", "CONTIGUOUS"}:
        return "CONTIG"
    if upper in {"2", "SEPARATE"}:
        return "SEPARATE"
    return upper or None


def spatial_shape(arr: np.ndarray) -> tuple[int, int]:
    if arr.ndim < 2:
        raise ValueError(f"Unsupported image shape: {arr.shape}")
    if (
        arr.ndim == 3
        and arr.shape[0] in SUPPORTED_COLOR_CHANNEL_COUNTS
        and arr.shape[-1] not in SUPPORTED_COLOR_CHANNEL_COUNTS
    ):
        return int(arr.shape[1]), int(arr.shape[2])
    return int(arr.shape[0]), int(arr.shape[1])


def infer_axes(arr: np.ndarray) -> str:
    if arr.ndim == 2:
        return "YX"
    if arr.ndim == 3 and arr.shape[-1] in SUPPORTED_COLOR_CHANNEL_COUNTS:
        return "YXS"
    if arr.ndim == 3 and arr.shape[0] in SUPPORTED_COLOR_CHANNEL_COUNTS:
        return "SYX"
    raise ValueError(f"Unsupported TIFF array shape: {arr.shape}")


def infer_axes_from_shape(shape: tuple[int, ...]) -> str:
    if len(shape) == 2:
        return "YX"
    if len(shape) == 3 and shape[-1] in SUPPORTED_COLOR_CHANNEL_COUNTS:
        return "YXS"
    if len(shape) == 3 and shape[0] in SUPPORTED_COLOR_CHANNEL_COUNTS:
        return "SYX"
    raise ValueError(f"Unsupported TIFF array shape: {shape}")


def spatial_shape_from_shape(shape: tuple[int, ...]) -> tuple[int, int]:
    axes = infer_axes_from_shape(shape)
    if axes == "SYX":
        return int(shape[1]), int(shape[2])
    return int(shape[0]), int(shape[1])


def sampled_values_for_percentile(
    values: np.ndarray,
    max_samples: int,
) -> np.ndarray:
    if max_samples <= 0:
        raise ValueError("percentile sample count must be positive")
    flat = values.reshape(-1)
    if flat.size <= max_samples:
        return flat
    step = max(1, int(math.ceil(flat.size / float(max_samples))))
    return flat[::step]
