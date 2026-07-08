from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..utils import smooth_1d
from .detection_parameters import SeparatorProfileParameters


@dataclass(frozen=True)
class SeparatorProfileSignals:
    extreme_score: np.ndarray
    soft_score: np.ndarray
    uniform_score: np.ndarray
    gradient_score: np.ndarray


def vertical_profile_sample(crop: np.ndarray, top_ratio: float, bottom_ratio: float) -> np.ndarray:
    height = crop.shape[0]
    y0 = max(0, min(height - 1, int(round(height * top_ratio))))
    y1 = max(y0 + 1, min(height, int(round(height * bottom_ratio))))
    return crop[y0:y1, :]


def segmented_extreme_separator_score(
    middle: np.ndarray,
    config: SeparatorProfileParameters,
) -> np.ndarray:
    profiles: list[np.ndarray] = []
    segments = max(1, int(config.segments))
    for i in range(segments):
        sy0 = int(round(i * middle.shape[0] / segments))
        sy1 = int(round((i + 1) * middle.shape[0] / segments))
        if sy1 <= sy0:
            continue
        part = middle[sy0:sy1, :]
        black = (part <= config.dark_threshold).mean(axis=0).astype(np.float32)
        white = (part >= config.light_threshold).mean(axis=0).astype(np.float32)
        profiles.append(np.maximum(black, white))
    if not profiles:
        fallback = (
            ((middle <= config.dark_threshold) | (middle >= config.light_threshold))
            .mean(axis=0)
            .astype(np.float32)
        )
        profiles.append(fallback)

    stack = np.stack(profiles, axis=0)
    average_extreme = stack.mean(axis=0).astype(np.float32)
    vertical_consistency = np.percentile(stack, config.consistency_percentile, axis=0).astype(np.float32)
    return config.average_weight * average_extreme + config.consistency_weight * vertical_consistency


def uniform_soft_separator_score(
    middle_f: np.ndarray,
    config: SeparatorProfileParameters,
) -> tuple[np.ndarray, np.ndarray]:
    col_std = middle_f.std(axis=0)
    uniform_score = 1.0 - np.clip(col_std / config.std_norm, 0.0, 1.0)
    col_mean = middle_f.mean(axis=0)
    dark_soft = np.clip((config.dark_soft_mean - col_mean) / config.dark_soft_mean, 0.0, 1.0)
    light_soft = np.clip((col_mean - config.light_soft_mean) / config.light_soft_span, 0.0, 1.0)
    soft_score = np.maximum(dark_soft, light_soft) * uniform_score * config.soft_weight
    return soft_score, uniform_score


def column_gradient_score(middle_f: np.ndarray) -> np.ndarray:
    return np.abs(np.diff(middle_f, axis=1, prepend=middle_f[:, :1])).mean(axis=0) / 255.0


def separator_profile_signals(
    middle: np.ndarray,
    config: SeparatorProfileParameters,
) -> SeparatorProfileSignals:
    middle_f = middle.astype(np.float32, copy=False)
    extreme_score = segmented_extreme_separator_score(middle, config)
    soft_score, uniform_score = uniform_soft_separator_score(middle_f, config)
    gradient_score = column_gradient_score(middle_f)
    return SeparatorProfileSignals(
        extreme_score=extreme_score,
        soft_score=soft_score,
        uniform_score=uniform_score,
        gradient_score=gradient_score,
    )


def combined_separator_profile_score(
    signals: SeparatorProfileSignals,
    config: SeparatorProfileParameters,
) -> np.ndarray:
    weighted_extreme = signals.extreme_score * (
        config.uniform_base + config.uniform_weight * signals.uniform_score
    )
    score = np.maximum(weighted_extreme, signals.soft_score)
    return np.maximum(
        score,
        np.clip(signals.gradient_score, 0.0, 1.0) * config.gradient_weight,
    )


def separator_profile_smooth_window(width: int, config: SeparatorProfileParameters) -> int:
    return max(config.smooth_min, int(round(width * config.smooth_ratio)))


def separator_profile(
    crop: np.ndarray,
    config: SeparatorProfileParameters,
) -> np.ndarray:
    h, w = crop.shape
    if h <= 0 or w <= 0:
        return np.zeros(0, dtype=np.float32)
    middle = vertical_profile_sample(crop, config.top_ratio, config.bottom_ratio)
    signals = separator_profile_signals(middle, config)
    score = combined_separator_profile_score(signals, config)
    return smooth_1d(score.astype(np.float32), separator_profile_smooth_window(w, config))


def interval_mean(profile: np.ndarray, start: int, end: int) -> float:
    start = max(0, min(int(start), len(profile)))
    end = max(start, min(int(end), len(profile)))
    if end <= start:
        return 0.0
    return float(profile[start:end].mean())


__all__ = [
    "SeparatorProfileSignals",
    "column_gradient_score",
    "combined_separator_profile_score",
    "interval_mean",
    "segmented_extreme_separator_score",
    "separator_profile",
    "separator_profile_signals",
    "separator_profile_smooth_window",
    "uniform_soft_separator_score",
    "vertical_profile_sample",
]
