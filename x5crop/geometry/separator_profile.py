from __future__ import annotations

import numpy as np

from ..utils import runs_from_mask, smooth_1d
from .detection_parameters import EdgeRefineProfileParameters, SeparatorProfileParameters


def separator_profile(
    crop: np.ndarray,
    config: SeparatorProfileParameters | None = None,
) -> np.ndarray:
    config = config or SeparatorProfileParameters()
    h, w = crop.shape
    if h <= 0 or w <= 0:
        return np.zeros(0, dtype=np.float32)
    y0 = max(0, min(h - 1, int(round(h * config.top_ratio))))
    y1 = max(y0 + 1, min(h, int(round(h * config.bottom_ratio))))
    middle = crop[y0:y1, :]
    middle_f = middle.astype(np.float32, copy=False)

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
    extreme_score = config.average_weight * average_extreme + config.consistency_weight * vertical_consistency

    col_std = middle_f.std(axis=0)
    uniform_score = 1.0 - np.clip(col_std / config.std_norm, 0.0, 1.0)
    col_mean = middle_f.mean(axis=0)
    dark_soft = np.clip((config.dark_soft_mean - col_mean) / config.dark_soft_mean, 0.0, 1.0)
    light_soft = np.clip((col_mean - config.light_soft_mean) / config.light_soft_span, 0.0, 1.0)
    soft_score = np.maximum(dark_soft, light_soft) * uniform_score * config.soft_weight

    gradient = np.abs(np.diff(middle_f, axis=1, prepend=middle_f[:, :1])).mean(axis=0) / 255.0
    score = np.maximum(extreme_score * (config.uniform_base + config.uniform_weight * uniform_score), soft_score)
    score = np.maximum(score, np.clip(gradient, 0.0, 1.0) * config.gradient_weight)
    return smooth_1d(score.astype(np.float32), max(config.smooth_min, int(round(w * config.smooth_ratio))))


def normalize_profile(profile: np.ndarray, high_percentile: float = 99.0) -> np.ndarray:
    profile = profile.astype(np.float32, copy=False)
    if profile.size == 0:
        return profile
    hi = float(np.percentile(profile, high_percentile))
    if hi <= 1e-6:
        return np.zeros_like(profile, dtype=np.float32)
    return np.clip(profile / hi, 0.0, 1.0).astype(np.float32)


def edge_refine_profiles(
    crop: np.ndarray,
    config: EdgeRefineProfileParameters | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    config = config or EdgeRefineProfileParameters()
    h, w = crop.shape
    if h <= 0 or w <= 1:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    y0 = max(0, min(h - 1, int(round(h * config.top_ratio))))
    y1 = max(y0 + 1, min(h, int(round(h * config.bottom_ratio))))
    middle = crop[y0:y1, :]
    if middle.size == 0:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    middle_i16 = middle.astype(np.int16, copy=False)
    diff_x = np.abs(np.diff(middle_i16, axis=1)).astype(np.float32)
    edge = np.zeros(w, dtype=np.float32)
    if diff_x.shape[1] > 0:
        raw = config.mean_weight * diff_x.mean(axis=0) + config.p75_weight * np.percentile(diff_x, 75, axis=0)
        edge[1:] = raw
        edge = normalize_profile(smooth_1d(edge, max(config.smooth_min, int(round(w * config.smooth_ratio)))), config.high_percentile)
    background = ((middle <= config.background_dark_threshold) | (middle >= config.background_light_threshold)).mean(axis=0).astype(np.float32)
    col_std = middle.astype(np.float32, copy=False).std(axis=0)
    if middle.shape[0] > 1:
        diff_y = np.abs(np.diff(middle_i16, axis=0)).astype(np.float32)
        y_edge = diff_y.mean(axis=0)
    else:
        y_edge = np.zeros(w, dtype=np.float32)
    activity = normalize_profile(col_std + config.y_edge_weight * y_edge, config.activity_percentile)
    return edge, background, activity


def local_edge_peaks(profile: np.ndarray, lo: int, hi: int, min_strength: float) -> list[int]:
    width = len(profile)
    lo = max(0, min(int(lo), width))
    hi = max(lo, min(int(hi), width))
    if hi <= lo:
        return []
    local = profile[lo:hi]
    if local.size == 0:
        return []
    threshold = max(float(min_strength), float(np.percentile(local, 84)))
    peaks: list[int] = []
    for start, end in runs_from_mask(local >= threshold):
        if end <= start:
            continue
        peak = lo + start + int(np.argmax(local[start:end]))
        if float(profile[peak]) >= min_strength:
            peaks.append(int(peak))
    deduped: list[int] = []
    for peak in sorted(peaks):
        if not deduped or peak - deduped[-1] > 2:
            deduped.append(peak)
        elif profile[peak] > profile[deduped[-1]]:
            deduped[-1] = peak
    return deduped


def interval_mean(profile: np.ndarray, start: int, end: int) -> float:
    start = max(0, min(int(start), len(profile)))
    end = max(start, min(int(end), len(profile)))
    if end <= start:
        return 0.0
    return float(profile[start:end].mean())
