from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..utils import sampled_percentile


@dataclass(frozen=True)
class ImageMeasurementStatisticsParameters:
    intensity_percentiles: tuple[float, float, float, float, float] = (
        2.0,
        10.0,
        50.0,
        90.0,
        98.0,
    )
    noise_percentiles: tuple[float, float, float] = (50.0, 90.0, 99.0)
    edge_sample_ratio: float = 0.05
    edge_sample_min_px: int = 8


@dataclass(frozen=True)
class ImageMeasurementStatistics:
    intensity_quantiles: tuple[float, float, float, float, float]
    intensity_mad: float
    gradient_quantiles: tuple[float, float, float]
    gradient_mad: float
    texture_quantiles: tuple[float, float, float]
    texture_mad: float
    edge_intensity_quantiles: tuple[float, float, float]
    edge_texture_quantiles: tuple[float, float, float]

    @property
    def intensity_low(self) -> float:
        return self.intensity_quantiles[1]

    @property
    def intensity_median(self) -> float:
        return self.intensity_quantiles[2]

    @property
    def intensity_high(self) -> float:
        return self.intensity_quantiles[3]

    @property
    def edge_texture_limit(self) -> float:
        return self.edge_texture_quantiles[2]


def _median_absolute_deviation(values: np.ndarray, median: float) -> float:
    if not values.size:
        return 0.0
    return float(sampled_percentile(np.abs(values - float(median)), [50.0])[0])


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
    ) * 0.25


def image_measurement_statistics(
    gray: np.ndarray,
    parameters: ImageMeasurementStatisticsParameters,
) -> ImageMeasurementStatistics:
    if gray.ndim != 2 or not gray.size:
        raise ValueError("image measurement statistics require non-empty grayscale")
    data = gray.astype(np.float32, copy=False)
    intensity = tuple(
        float(value)
        for value in sampled_percentile(data, parameters.intensity_percentiles)
    )
    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    gradient = gx + gy
    texture = _neighbor_texture(data)
    gradient_quantiles = tuple(
        float(value)
        for value in sampled_percentile(gradient, parameters.noise_percentiles)
    )
    texture_quantiles = tuple(
        float(value)
        for value in sampled_percentile(texture, parameters.noise_percentiles)
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
    edge_intensity = data[edge_mask]
    edge_texture = texture[edge_mask]
    edge_intensity_quantiles = tuple(
        float(value)
        for value in sampled_percentile(edge_intensity, (10.0, 50.0, 90.0))
    )
    edge_texture_quantiles = tuple(
        float(value)
        for value in sampled_percentile(edge_texture, (50.0, 90.0, 99.0))
    )
    return ImageMeasurementStatistics(
        intensity_quantiles=intensity,
        intensity_mad=_median_absolute_deviation(data, intensity[2]),
        gradient_quantiles=gradient_quantiles,
        gradient_mad=_median_absolute_deviation(gradient, gradient_quantiles[0]),
        texture_quantiles=texture_quantiles,
        texture_mad=_median_absolute_deviation(texture, texture_quantiles[0]),
        edge_intensity_quantiles=edge_intensity_quantiles,
        edge_texture_quantiles=edge_texture_quantiles,
    )
