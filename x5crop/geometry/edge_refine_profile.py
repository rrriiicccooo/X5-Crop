from __future__ import annotations

import numpy as np

from ..utils import runs_from_mask, smooth_1d
from .detection_parameters import EdgeRefineProfileParameters
from .separator_profile import vertical_profile_sample


def normalize_profile(profile: np.ndarray, high_percentile: float) -> np.ndarray:
    profile = profile.astype(np.float32, copy=False)
    if profile.size == 0:
        return profile
    hi = float(np.percentile(profile, high_percentile))
    if hi <= 1e-6:
        return np.zeros_like(profile, dtype=np.float32)
    return np.clip(profile / hi, 0.0, 1.0).astype(np.float32)


def edge_refine_profiles(
    crop: np.ndarray,
    config: EdgeRefineProfileParameters,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = crop.shape
    if h <= 0 or w <= 1:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    middle = vertical_profile_sample(crop, config.top_ratio, config.bottom_ratio)
    if middle.size == 0:
        zeros = np.zeros(w, dtype=np.float32)
        return zeros, zeros, zeros
    middle_i16 = middle.astype(np.int16, copy=False)
    diff_x = np.abs(np.diff(middle_i16, axis=1)).astype(np.float32)
    edge = np.zeros(w, dtype=np.float32)
    if diff_x.shape[1] > 0:
        raw = config.mean_weight * diff_x.mean(axis=0) + config.p75_weight * np.percentile(diff_x, 75, axis=0)
        edge[1:] = raw
        edge = normalize_profile(
            smooth_1d(edge, max(config.smooth_min, int(round(w * config.smooth_ratio)))),
            config.high_percentile,
        )
    background = ((middle <= config.background_dark_threshold) | (middle >= config.background_light_threshold)).mean(axis=0).astype(np.float32)
    col_std = middle.astype(np.float32, copy=False).std(axis=0)
    if middle.shape[0] > 1:
        diff_y = np.abs(np.diff(middle_i16, axis=0)).astype(np.float32)
        y_edge = diff_y.mean(axis=0)
    else:
        y_edge = np.zeros(w, dtype=np.float32)
    activity = normalize_profile(col_std + config.y_edge_weight * y_edge, config.activity_percentile)
    return edge, background, activity


def local_edge_peaks(
    profile: np.ndarray,
    lo: int,
    hi: int,
    min_strength: float,
    candidate_percentile: float,
    min_distance_px: int,
) -> list[int]:
    width = len(profile)
    lo = max(0, min(int(lo), width))
    hi = max(lo, min(int(hi), width))
    if hi <= lo:
        return []
    local = profile[lo:hi]
    if local.size == 0:
        return []
    threshold = max(
        float(min_strength),
        float(np.percentile(local, candidate_percentile)),
    )
    peaks: list[int] = []
    for start, end in runs_from_mask(local >= threshold):
        if end <= start:
            continue
        peak = lo + start + int(np.argmax(local[start:end]))
        if float(profile[peak]) >= min_strength:
            peaks.append(int(peak))
    deduped: list[int] = []
    for peak in sorted(peaks):
        if not deduped or peak - deduped[-1] > min_distance_px:
            deduped.append(peak)
        elif profile[peak] > profile[deduped[-1]]:
            deduped[-1] = peak
    return deduped
