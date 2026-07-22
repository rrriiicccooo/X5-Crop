from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .constants import (
    FIVE_POINT_MEAN_WEIGHT,
    UINT8_MAX_VALUE,
    UINT8_ROUNDING_OFFSET,
)
from ..utils import (
    require_nonnegative,
    require_percentile,
    require_positive,
    sampled_percentile,
    smooth_1d,
)


CONTENT_EVIDENCE_NEIGHBORHOOD_RADIUS_PX = 1


@dataclass(frozen=True)
class SeparatorEvidenceImageParameters:
    low_percentile: float = 2.0
    high_percentile: float = 98.0
    vertical_edge_smooth_ratio: float = 0.0015
    vertical_edge_smooth_min: int = 3
    tonal_low_percentile: float = 10.0
    tonal_high_percentile: float = 90.0
    local_weight: float = 0.72
    vertical_edge_weight: float = 0.28
    tonal_band_weight: float = 0.55
    numerical_floor: float = 1e-6
    maximum_percentile_samples: int = 1_000_000

    def __post_init__(self) -> None:
        for name, value in (
            ("separator image low percentile", self.low_percentile),
            ("separator image high percentile", self.high_percentile),
            ("separator tonal low percentile", self.tonal_low_percentile),
            ("separator tonal high percentile", self.tonal_high_percentile),
        ):
            require_percentile(name, value)
        if self.high_percentile <= self.low_percentile:
            raise ValueError("separator image high percentile must follow low")
        if self.tonal_high_percentile <= self.tonal_low_percentile:
            raise ValueError("separator tonal high percentile must follow low")
        require_nonnegative(
            "separator vertical-edge smoothing ratio",
            self.vertical_edge_smooth_ratio,
        )
        require_positive(
            "separator vertical-edge minimum width",
            self.vertical_edge_smooth_min,
        )
        for name, value in (
            ("separator local weight", self.local_weight),
            ("separator vertical-edge weight", self.vertical_edge_weight),
            ("separator tonal-band weight", self.tonal_band_weight),
        ):
            require_nonnegative(name, value)
        require_positive("separator image numerical floor", self.numerical_floor)
        require_positive(
            "separator image percentile sample budget",
            self.maximum_percentile_samples,
        )


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


def make_separator_evidence_gray(
    gray: np.ndarray,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    data = gray.astype(np.float32, copy=False)
    lo, hi = sampled_percentile(
        data,
        [params.low_percentile, params.high_percentile],
        params.maximum_percentile_samples,
    )
    if hi <= lo:
        return gray.copy()
    local = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    gx = np.abs(np.diff(local, axis=1, prepend=local[:, :1]))
    vertical_edge = smooth_1d(
        gx.mean(axis=0).astype(np.float32),
        max(
            params.vertical_edge_smooth_min,
            int(round(gray.shape[1] * params.vertical_edge_smooth_ratio)),
        ),
    )
    column_mean = local.mean(axis=0)
    tonal_low, tonal_high = sampled_percentile(
        column_mean,
        [
            params.tonal_low_percentile,
            params.tonal_high_percentile,
        ],
        params.maximum_percentile_samples,
    )
    tonal_center = float(np.median(column_mean))
    dark_response = np.clip(
        (tonal_center - column_mean)
        / max(params.numerical_floor, tonal_center - tonal_low),
        0.0,
        1.0,
    )
    light_band = np.clip(
        (column_mean - tonal_center)
        / max(params.numerical_floor, tonal_high - tonal_center),
        0.0,
        1.0,
    )
    band = np.maximum(dark_response, light_band)
    evidence = np.maximum(
        local * params.local_weight,
        vertical_edge[None, :] * params.vertical_edge_weight,
    )
    evidence = np.maximum(evidence, band[None, :] * params.tonal_band_weight)
    return (
        np.clip(evidence, 0.0, 1.0) * UINT8_MAX_VALUE
        + UINT8_ROUNDING_OFFSET
    ).astype(np.uint8)


def make_content_evidence_gray(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32, copy=False) / UINT8_MAX_VALUE
    if data.size == 0:
        return gray.copy()

    north = np.empty_like(data)
    south = np.empty_like(data)
    west = np.empty_like(data)
    east = np.empty_like(data)
    north[0, :] = data[0, :]
    north[1:, :] = data[:-1, :]
    south[-1, :] = data[-1, :]
    south[:-1, :] = data[1:, :]
    west[:, 0] = data[:, 0]
    west[:, 1:] = data[:, :-1]
    east[:, -1] = data[:, -1]
    east[:, :-1] = data[:, 1:]
    horizontal_activity = np.abs(data - west) + np.abs(data - east)
    vertical_activity = np.abs(data - north) + np.abs(data - south)

    local_mean = (
        data + north + south + west + east
    ) * FIVE_POINT_MEAN_WEIGHT
    local_contrast = np.abs(data - local_mean)

    evidence = np.minimum(
        np.minimum(horizontal_activity, vertical_activity),
        local_contrast,
    )
    evidence = np.clip(evidence, 0.0, 1.0)
    return (
        evidence * UINT8_MAX_VALUE + UINT8_ROUNDING_OFFSET
    ).astype(np.uint8)
