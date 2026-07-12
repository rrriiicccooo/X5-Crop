from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..geometry.sampling import sampling_step_for_limit
from ..utils import (
    require_nonnegative,
    require_percentile,
    require_positive,
    require_unit_interval,
    smooth_1d,
)
from .statistics import ImageMeasurementStatistics


@dataclass(frozen=True)
class SeparatorProfileParameters:
    top_ratio: float = 0.10
    bottom_ratio: float = 0.90
    segments: int = 5
    consistency_percentile: float = 20.0
    sample_short_axis_max: int = 500
    smooth_ratio: float = 0.0015
    smooth_min: int = 3
    numerical_floor: float = 1e-6

    def __post_init__(self) -> None:
        require_unit_interval("separator profile top ratio", self.top_ratio)
        require_unit_interval("separator profile bottom ratio", self.bottom_ratio)
        if self.bottom_ratio <= self.top_ratio:
            raise ValueError("separator profile bottom must follow top")
        require_positive("separator profile segment count", self.segments)
        require_percentile(
            "separator consistency percentile",
            self.consistency_percentile,
        )
        require_positive(
            "separator short-axis sample limit",
            self.sample_short_axis_max,
        )
        require_nonnegative("separator smoothing ratio", self.smooth_ratio)
        require_positive("separator minimum smoothing width", self.smooth_min)
        require_positive("separator numerical floor", self.numerical_floor)


@dataclass(frozen=True)
class SeparatorProfileSignals:
    cross_axis_extreme: np.ndarray
    tonal_uniformity: np.ndarray
    transition_uniformity: np.ndarray


def vertical_profile_sample(
    crop: np.ndarray,
    top_ratio: float,
    bottom_ratio: float,
) -> np.ndarray:
    height = crop.shape[0]
    y0 = max(0, min(height - 1, int(round(height * top_ratio))))
    y1 = max(y0 + 1, min(height, int(round(height * bottom_ratio))))
    return crop[y0:y1, :]


def _cross_axis_extreme_score(
    middle: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorProfileParameters,
) -> np.ndarray:
    profiles: list[np.ndarray] = []
    segments = int(parameters.segments)
    for index in range(segments):
        start = int(round(index * middle.shape[0] / segments))
        end = int(round((index + 1) * middle.shape[0] / segments))
        if end <= start:
            continue
        segment = middle[start:end, :]
        profiles.append(
            (
                (segment <= statistics.intensity_low)
                | (segment >= statistics.intensity_high)
            ).mean(axis=0, dtype=np.float32)
        )
    if not profiles:
        return np.zeros(middle.shape[1], dtype=np.float32)
    return np.percentile(
        np.stack(profiles, axis=0),
        float(parameters.consistency_percentile),
        axis=0,
    ).astype(np.float32)


def separator_profile_signals(
    middle: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorProfileParameters,
) -> SeparatorProfileSignals:
    data = middle.astype(np.float32, copy=False)
    floor = float(parameters.numerical_floor)
    column_mean = data.mean(axis=0)
    column_std = data.std(axis=0)
    tonal_scale = max(
        floor,
        statistics.intensity_mad,
        statistics.intensity_median - statistics.intensity_low,
        statistics.intensity_high - statistics.intensity_median,
    )
    texture_scale = max(
        floor,
        statistics.texture_quantiles[1],
        statistics.texture_mad,
    )
    tonal_deviation = np.clip(
        np.abs(column_mean - statistics.intensity_median) / tonal_scale,
        0.0,
        1.0,
    )
    uniformity = 1.0 - np.clip(column_std / texture_scale, 0.0, 1.0)
    tonal_uniformity = np.minimum(tonal_deviation, uniformity).astype(np.float32)
    gradient = np.abs(np.diff(data, axis=1, prepend=data[:, :1])).mean(axis=0)
    gradient_scale = max(
        floor,
        statistics.gradient_quantiles[1],
        statistics.gradient_mad,
    )
    transition_uniformity = np.minimum(
        np.clip(gradient / gradient_scale, 0.0, 1.0),
        uniformity,
    ).astype(np.float32)
    return SeparatorProfileSignals(
        cross_axis_extreme=_cross_axis_extreme_score(
            middle,
            statistics,
            parameters,
        ),
        tonal_uniformity=tonal_uniformity,
        transition_uniformity=transition_uniformity,
    )


def combined_separator_profile_score(signals: SeparatorProfileSignals) -> np.ndarray:
    return np.maximum.reduce(
        (
            signals.cross_axis_extreme,
            signals.tonal_uniformity,
            signals.transition_uniformity,
        )
    ).astype(np.float32)


def separator_profile_smooth_window(
    width: int,
    parameters: SeparatorProfileParameters,
) -> int:
    return max(
        int(parameters.smooth_min),
        int(round(width * float(parameters.smooth_ratio))),
    )


def separator_profile(
    crop: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorProfileParameters,
) -> np.ndarray:
    height, width = crop.shape
    if height <= 0 or width <= 0:
        return np.zeros(0, dtype=np.float32)
    middle = vertical_profile_sample(
        crop,
        parameters.top_ratio,
        parameters.bottom_ratio,
    )
    middle = middle[
        ::sampling_step_for_limit(
            middle.shape[0],
            parameters.sample_short_axis_max,
        ),
        :,
    ]
    signals = separator_profile_signals(middle, statistics, parameters)
    return smooth_1d(
        combined_separator_profile_score(signals),
        separator_profile_smooth_window(width, parameters),
    )
