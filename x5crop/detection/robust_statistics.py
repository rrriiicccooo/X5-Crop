"""Shared robust-statistics primitives with explicit measurement units."""

from __future__ import annotations

import math

import numpy as np


# Consistency factor that maps Gaussian MAD to standard deviation.  This is a
# statistical identity, not a film-format or sample calibration.
NORMAL_MAD_SCALE = 1.4826

# Registered grayscale measurement is normalized to uint8 before this layer;
# one code value is therefore the smallest meaningful non-zero noise scale.
REGISTERED_UINT8_QUANTIZATION_STEP = 1.0


def positive_mad_z(
    values: np.ndarray,
    *,
    active_only: bool = False,
    minimum_scale: float = 0.0,
) -> np.ndarray:
    """Return the positive robust z-score in the caller's measurement units."""

    if not math.isfinite(minimum_scale) or minimum_scale < 0.0:
        raise ValueError("robust minimum scale must be finite and non-negative")
    numeric = values.astype(np.float64, copy=False)
    if numeric.size == 0:
        return numeric
    sample = numeric[np.isfinite(numeric)]
    if active_only:
        sample = sample[sample > np.finfo(np.float32).eps]
    if not sample.size:
        return np.zeros_like(numeric, dtype=np.float64)
    center = float(np.median(sample))
    mad = float(np.median(np.abs(sample - center)))
    scale = max(minimum_scale, NORMAL_MAD_SCALE * mad)
    if scale <= np.finfo(np.float64).eps:
        return np.zeros_like(numeric, dtype=np.float64)
    result = (numeric - center) / scale
    np.maximum(result, 0.0, out=result)
    result[~np.isfinite(result)] = 0.0
    return result


def positive_mad_z_rows(
    values: np.ndarray,
    *,
    minimum_scale: float = 0.0,
) -> np.ndarray:
    """Return one positive robust z-score normalization per matrix row.

    ``values`` must contain finite measurements.  The registered transition
    owner supplies finite float64 measurements; non-finite input is
    rejected rather than changing the finite-sample denominator.  Keeping the
    row reduction vectorized makes a batch of native traces avoid a Python call
    per trace while using the same median/MAD constants as
    :func:`positive_mad_z`.
    """

    if not math.isfinite(minimum_scale) or minimum_scale < 0.0:
        raise ValueError("robust minimum scale must be finite and non-negative")
    if values.ndim != 2:
        raise ValueError("row robust normalization requires a two-dimensional array")
    numeric = values.astype(np.float64, copy=False)
    if not np.all(np.isfinite(numeric)):
        raise ValueError("row robust normalization requires finite values")
    if numeric.shape[1] == 0:
        return numeric
    # Row responses can be column-contiguous views. Partition one private
    # row-contiguous buffer, then reuse it for deviations and the final result.
    # Neither partition changes the caller's measurements or normalization
    # domain, and no extra median copy remains live beside this workspace.
    result = np.array(numeric, dtype=np.float64, copy=True, order="C")
    center = np.median(result, axis=1, overwrite_input=True)
    np.subtract(numeric, center[:, None], out=result)
    np.abs(result, out=result)
    mad = np.median(result, axis=1, overwrite_input=True)
    scale = np.maximum(minimum_scale, NORMAL_MAD_SCALE * mad)
    valid = scale > np.finfo(np.float64).eps
    np.subtract(numeric, center[:, None], out=result)
    result[~valid] = 0.0
    np.divide(result, scale[:, None], out=result, where=valid[:, None])
    np.maximum(result, 0.0, out=result)
    return result
