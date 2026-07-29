from __future__ import annotations

import math

import numpy as np

from ..utils import sampled_percentile


def adaptive_activation_threshold(
    values: np.ndarray,
    percentile: float,
    minimum_range: float,
    maximum_percentile_samples: int,
) -> float | None:
    if not values.size:
        return None
    minimum = float(values.min())
    maximum = float(values.max())
    if maximum - minimum <= float(minimum_range):
        return None
    return float(
        sampled_percentile(
            values,
            [percentile],
            maximum_percentile_samples,
        )[0]
    )


def activation_mask(
    values: np.ndarray,
    threshold: float,
) -> np.ndarray:
    if not values.size:
        return np.zeros(values.shape, dtype=bool)
    if not math.isfinite(float(threshold)):
        raise ValueError("activation threshold must be finite")
    minimum = float(values.min())
    return values > threshold if threshold <= minimum else values >= threshold


def spatially_supported_activation_mask(
    values: np.ndarray,
    threshold: float,
    minimum_active_pixels: int,
) -> np.ndarray:
    if values.ndim != 2:
        raise ValueError("spatial activation requires a two-dimensional image")
    if minimum_active_pixels <= 0:
        raise ValueError("spatial activation requires positive pixel support")
    active = activation_mask(values, threshold)
    if int(np.count_nonzero(active)) < minimum_active_pixels:
        return np.zeros(values.shape, dtype=bool)
    axis_support = int(math.ceil(math.sqrt(minimum_active_pixels)))
    supported_rows = np.count_nonzero(active, axis=1) >= axis_support
    supported_columns = np.count_nonzero(active, axis=0) >= axis_support
    supported = active & supported_rows[:, None] & supported_columns[None, :]
    if int(np.count_nonzero(supported)) < minimum_active_pixels:
        return np.zeros(values.shape, dtype=bool)
    return supported
