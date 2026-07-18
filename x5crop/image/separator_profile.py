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


SYMMETRIC_WINDOW_SIDE_COUNT = 2


@dataclass(frozen=True)
class SeparatorProfileParameters:
    top_ratio: float = 0.10
    bottom_ratio: float = 0.90
    segments: int = 5
    consistency_percentile: float = 20.0
    sample_short_axis_max: int = 500
    local_baseline_ratio: float = 0.025
    local_baseline_min_px: int = 64
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
        require_unit_interval(
            "separator local baseline ratio",
            self.local_baseline_ratio,
        )
        if self.local_baseline_ratio <= 0.0:
            raise ValueError("separator local baseline ratio must be positive")
        require_positive(
            "separator local baseline minimum width",
            self.local_baseline_min_px,
        )
        require_nonnegative("separator smoothing ratio", self.smooth_ratio)
        require_positive("separator minimum smoothing width", self.smooth_min)
        require_positive("separator numerical floor", self.numerical_floor)


@dataclass(frozen=True)
class SeparatorProfileSignals:
    tonal_tail_continuity: np.ndarray
    tonal_uniformity: np.ndarray
    local_tonal_uniformity: np.ndarray
    local_texture_uniformity: np.ndarray
    transition_uniformity: np.ndarray


@dataclass(frozen=True, eq=False)
class SeparatorProfileMeasurement:
    raw_score: np.ndarray
    smoothed_score: np.ndarray
    smoothing_window_px: int
    local_baseline_window_px: int

    def __post_init__(self) -> None:
        if self.raw_score.ndim != 1 or self.smoothed_score.ndim != 1:
            raise ValueError("separator profile scores must be one-dimensional")
        if self.raw_score.shape != self.smoothed_score.shape:
            raise ValueError("separator profile scores must share one shape")
        require_positive(
            "separator profile smoothing width",
            self.smoothing_window_px,
        )
        require_positive(
            "separator local baseline width",
            self.local_baseline_window_px,
        )


def vertical_profile_sample(
    crop: np.ndarray,
    top_ratio: float,
    bottom_ratio: float,
) -> np.ndarray:
    height = crop.shape[0]
    y0 = max(0, min(height - 1, int(round(height * top_ratio))))
    y1 = max(y0 + 1, min(height, int(round(height * bottom_ratio))))
    return crop[y0:y1, :]


def _tonal_tail_continuity_score(
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
        statistics.texture_signal,
        statistics.texture_mad,
    )
    tonal_deviation = np.clip(
        np.abs(column_mean - statistics.intensity_median) / tonal_scale,
        0.0,
        1.0,
    )
    uniformity = 1.0 - np.clip(column_std / texture_scale, 0.0, 1.0)
    tonal_uniformity = np.minimum(tonal_deviation, uniformity).astype(np.float32)
    local_baseline_window_px = separator_profile_local_baseline_window(
        middle.shape[1],
        parameters,
    )
    local_baseline = _local_profile_baseline(
        column_mean,
        local_baseline_window_px,
    )
    local_tonal_uniformity = np.minimum(
        np.clip(
            np.abs(column_mean - local_baseline) / tonal_scale,
            0.0,
            1.0,
        ),
        uniformity,
    ).astype(np.float32)
    local_texture_baseline = _local_profile_baseline(
        column_std,
        local_baseline_window_px,
    )
    local_texture_uniformity = np.minimum(
        np.clip(
            (local_texture_baseline - column_std) / texture_scale,
            0.0,
            1.0,
        ),
        uniformity,
    ).astype(np.float32)
    gradient = np.abs(np.diff(data, axis=1, prepend=data[:, :1])).mean(axis=0)
    gradient_scale = max(
        floor,
        statistics.gradient_signal,
        statistics.gradient_mad,
    )
    transition_uniformity = np.minimum(
        np.clip(gradient / gradient_scale, 0.0, 1.0),
        uniformity,
    ).astype(np.float32)
    return SeparatorProfileSignals(
        tonal_tail_continuity=_tonal_tail_continuity_score(
            middle,
            statistics,
            parameters,
        ),
        tonal_uniformity=tonal_uniformity,
        local_tonal_uniformity=local_tonal_uniformity,
        local_texture_uniformity=local_texture_uniformity,
        transition_uniformity=transition_uniformity,
    )


def combined_separator_profile_score(signals: SeparatorProfileSignals) -> np.ndarray:
    return np.maximum.reduce(
        (
            signals.tonal_tail_continuity,
            signals.tonal_uniformity,
            signals.local_tonal_uniformity,
            signals.local_texture_uniformity,
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


def separator_profile_local_baseline_window(
    width: int,
    parameters: SeparatorProfileParameters,
) -> int:
    return max(
        int(parameters.local_baseline_min_px),
        int(round(width * float(parameters.local_baseline_ratio))),
    )


def _local_profile_baseline(profile: np.ndarray, window: int) -> np.ndarray:
    bounded_window = max(1, min(int(window), int(profile.size)))
    if bounded_window <= 1:
        return profile.astype(np.float32, copy=False)
    leading = (bounded_window - 1) // SYMMETRIC_WINDOW_SIDE_COUNT
    trailing = bounded_window - 1 - leading
    padded = np.pad(
        profile.astype(np.float32, copy=False),
        (leading, trailing),
        mode="edge",
    )
    kernel = np.ones(bounded_window, dtype=np.float32) / float(bounded_window)
    return np.convolve(padded, kernel, mode="valid")


def _readonly_score(score: np.ndarray) -> np.ndarray:
    measured = np.asarray(score, dtype=np.float32).copy()
    measured.setflags(write=False)
    return measured


def measure_separator_profile(
    crop: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorProfileParameters,
) -> SeparatorProfileMeasurement:
    height, width = crop.shape
    if height <= 0 or width <= 0:
        return SeparatorProfileMeasurement(
            _readonly_score(np.zeros(0, dtype=np.float32)),
            _readonly_score(np.zeros(0, dtype=np.float32)),
            1,
            1,
        )
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
    raw_score = combined_separator_profile_score(signals)
    smoothing_window_px = separator_profile_smooth_window(width, parameters)
    local_baseline_window_px = separator_profile_local_baseline_window(
        width,
        parameters,
    )
    return SeparatorProfileMeasurement(
        raw_score=_readonly_score(raw_score),
        smoothed_score=_readonly_score(
            smooth_1d(raw_score, smoothing_window_px)
        ),
        smoothing_window_px=smoothing_window_px,
        local_baseline_window_px=local_baseline_window_px,
    )
