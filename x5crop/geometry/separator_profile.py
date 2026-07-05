from __future__ import annotations

import numpy as np

from ..utils import smooth_1d
from .detection_parameters import SeparatorProfileParameters


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
        profiles.append(((middle <= config.dark_threshold) | (middle >= config.light_threshold)).mean(axis=0).astype(np.float32))

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


def separator_profile(
    crop: np.ndarray,
    config: SeparatorProfileParameters | None = None,
) -> np.ndarray:
    config = config or SeparatorProfileParameters()
    h, w = crop.shape
    if h <= 0 or w <= 0:
        return np.zeros(0, dtype=np.float32)
    middle = vertical_profile_sample(crop, config.top_ratio, config.bottom_ratio)
    middle_f = middle.astype(np.float32, copy=False)
    extreme_score = segmented_extreme_separator_score(middle, config)
    soft_score, uniform_score = uniform_soft_separator_score(middle_f, config)
    gradient = column_gradient_score(middle_f)
    score = np.maximum(extreme_score * (config.uniform_base + config.uniform_weight * uniform_score), soft_score)
    score = np.maximum(score, np.clip(gradient, 0.0, 1.0) * config.gradient_weight)
    return smooth_1d(score.astype(np.float32), max(config.smooth_min, int(round(w * config.smooth_ratio))))


def interval_mean(profile: np.ndarray, start: int, end: int) -> float:
    start = max(0, min(int(start), len(profile)))
    end = max(start, min(int(end), len(profile)))
    if end <= start:
        return 0.0
    return float(profile[start:end].mean())
