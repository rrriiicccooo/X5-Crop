from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from .domain import Box


PERCENTILE_MAX = 100.0


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


def clamp_int(value: float, lower: int, upper: int) -> int:
    return int(max(lower, min(upper, int(round(value)))))


def clamp_float(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, float(value))))


def json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


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
    if arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
        return int(arr.shape[1]), int(arr.shape[2])
    return int(arr.shape[0]), int(arr.shape[1])


def infer_axes(arr: np.ndarray) -> str:
    if arr.ndim == 2:
        return "YX"
    if arr.ndim == 3 and arr.shape[-1] in (3, 4):
        return "YXS"
    if arr.ndim == 3 and arr.shape[0] in (3, 4):
        return "SYX"
    raise ValueError(f"Unsupported TIFF array shape: {arr.shape}")


def infer_axes_from_shape(shape: tuple[int, ...]) -> str:
    if len(shape) == 2:
        return "YX"
    if len(shape) == 3 and shape[-1] in (3, 4):
        return "YXS"
    if len(shape) == 3 and shape[0] in (3, 4):
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


def sampled_percentile(
    values: np.ndarray,
    percentiles: Iterable[float],
    max_samples: int,
) -> np.ndarray:
    sample = sampled_values_for_percentile(values, max_samples=max_samples)
    if sample.size == 0:
        return np.array([0.0 for _ in percentiles], dtype=np.float64)
    return np.percentile(sample, list(percentiles))


def smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return values.astype(np.float32, copy=False)
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def runs_from_mask(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: Optional[int] = None
    for i, flag in enumerate(mask.astype(bool)):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def bbox_from_mask(
    mask: np.ndarray,
    min_row_fraction: float,
    min_col_fraction: float,
) -> Optional[Box]:
    if mask.size == 0:
        return None
    row_has = mask.mean(axis=1) >= min_row_fraction
    col_has = mask.mean(axis=0) >= min_col_fraction
    rows = np.flatnonzero(row_has)
    cols = np.flatnonzero(col_has)
    if rows.size == 0 or cols.size == 0:
        return None
    return Box(int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)
