from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import FOUR_NEIGHBOR_MEAN_WEIGHT
from ..utils import (
    require_percentile,
    require_positive,
    require_unit_interval,
    sampled_percentile,
    sampled_values_for_percentile,
)


@dataclass(frozen=True)
class ImageMeasurementStatisticsParameters:
    intensity_low_percentile: float = 10.0
    intensity_median_percentile: float = 50.0
    intensity_high_percentile: float = 90.0
    gradient_baseline_percentile: float = 50.0
    gradient_signal_percentile: float = 90.0
    texture_baseline_percentile: float = 50.0
    texture_signal_percentile: float = 90.0
    edge_texture_limit_percentile: float = 99.0
    edge_sample_ratio: float = 0.05
    edge_sample_min_px: int = 8
    maximum_percentile_samples: int = 1_000_000

    def __post_init__(self) -> None:
        percentiles = (
            ("intensity low", self.intensity_low_percentile),
            ("intensity median", self.intensity_median_percentile),
            ("intensity high", self.intensity_high_percentile),
            ("gradient baseline", self.gradient_baseline_percentile),
            ("gradient signal", self.gradient_signal_percentile),
            ("texture baseline", self.texture_baseline_percentile),
            ("texture signal", self.texture_signal_percentile),
            ("edge texture limit", self.edge_texture_limit_percentile),
        )
        for name, value in percentiles:
            require_percentile(f"{name} percentile", value)
        ordered_groups = (
            (
                self.intensity_low_percentile,
                self.intensity_median_percentile,
                self.intensity_high_percentile,
            ),
            (self.gradient_baseline_percentile, self.gradient_signal_percentile),
            (self.texture_baseline_percentile, self.texture_signal_percentile),
        )
        if any(tuple(sorted(group)) != group for group in ordered_groups):
            raise ValueError("measurement percentiles must follow their named order")
        require_unit_interval("edge sample ratio", self.edge_sample_ratio)
        require_positive("edge sample width", self.edge_sample_min_px)
        require_positive(
            "statistics percentile sample budget",
            self.maximum_percentile_samples,
        )


@dataclass(frozen=True)
class ImageMeasurementStatistics:
    intensity_low: float
    intensity_median: float
    intensity_high: float
    intensity_mad: float
    gradient_baseline: float
    gradient_signal: float
    gradient_mad: float
    texture_signal: float
    texture_mad: float
    edge_texture_limit: float


def _median_absolute_deviation(
    values: np.ndarray,
    median: float,
    maximum_samples: int,
) -> float:
    if not values.size:
        return 0.0
    sampled = sampled_values_for_percentile(
        np.abs(values - float(median)),
        maximum_samples,
    )
    return float(np.median(sampled))


def _neighbor_texture(data: np.ndarray) -> np.ndarray:
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
    return (
        np.abs(data - north)
        + np.abs(data - south)
        + np.abs(data - west)
        + np.abs(data - east)
    ) * FOUR_NEIGHBOR_MEAN_WEIGHT


def image_measurement_statistics(
    gray: np.ndarray,
    parameters: ImageMeasurementStatisticsParameters,
) -> ImageMeasurementStatistics:
    if gray.ndim != 2 or not gray.size:
        raise ValueError("image measurement statistics require non-empty grayscale")
    data = gray.astype(np.float32, copy=False)
    intensity = tuple(
        float(value)
        for value in sampled_percentile(
            data,
            (
                parameters.intensity_low_percentile,
                parameters.intensity_median_percentile,
                parameters.intensity_high_percentile,
            ),
            parameters.maximum_percentile_samples,
        )
    )
    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    gradient = gx + gy
    texture = _neighbor_texture(data)
    gradient_statistics = tuple(
        float(value)
        for value in sampled_percentile(
            gradient,
            (
                parameters.gradient_baseline_percentile,
                parameters.gradient_signal_percentile,
            ),
            parameters.maximum_percentile_samples,
        )
    )
    texture_statistics = tuple(
        float(value)
        for value in sampled_percentile(
            texture,
            (
                parameters.texture_baseline_percentile,
                parameters.texture_signal_percentile,
            ),
            parameters.maximum_percentile_samples,
        )
    )
    edge_band = min(
        min(gray.shape),
        max(
            int(parameters.edge_sample_min_px),
            int(round(min(gray.shape) * float(parameters.edge_sample_ratio))),
        ),
    )
    edge_mask = np.zeros(gray.shape, dtype=bool)
    edge_mask[:edge_band, :] = True
    edge_mask[-edge_band:, :] = True
    edge_mask[:, :edge_band] = True
    edge_mask[:, -edge_band:] = True
    edge_texture = texture[edge_mask]
    edge_texture_limit = float(
        sampled_percentile(
            edge_texture,
            (parameters.edge_texture_limit_percentile,),
            parameters.maximum_percentile_samples,
        )[0]
    )
    return ImageMeasurementStatistics(
        intensity_low=intensity[0],
        intensity_median=intensity[1],
        intensity_high=intensity[2],
        intensity_mad=_median_absolute_deviation(
            data,
            intensity[1],
            parameters.maximum_percentile_samples,
        ),
        gradient_baseline=gradient_statistics[0],
        gradient_signal=gradient_statistics[1],
        gradient_mad=_median_absolute_deviation(
            gradient,
            gradient_statistics[0],
            parameters.maximum_percentile_samples,
        ),
        texture_signal=texture_statistics[1],
        texture_mad=_median_absolute_deviation(
            texture,
            texture_statistics[0],
            parameters.maximum_percentile_samples,
        ),
        edge_texture_limit=edge_texture_limit,
    )
