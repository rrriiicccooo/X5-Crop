from __future__ import annotations

import numpy as np

from ..utils import (
    runs_from_mask,
    sampled_percentile,
    sampled_values_for_percentile,
    smooth_1d,
)


def make_deskew_fallback_gray(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32)
    lo, hi = sampled_percentile(data, [0.5, 99.5])
    if hi <= lo:
        return gray.copy()
    stretched = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    shadow_lift = np.power(stretched, 0.72)
    gx = np.abs(np.diff(shadow_lift, axis=1, prepend=shadow_lift[:, :1]))
    gy = np.abs(np.diff(shadow_lift, axis=0, prepend=shadow_lift[:1, :]))
    edge = np.clip((gx + gy) * 2.0, 0.0, 1.0)
    fallback = np.clip(shadow_lift * 0.82 + edge * 0.18, 0.0, 1.0)
    extreme = ((gray < 35) | (gray > 235)).mean(axis=0)
    activity = (gx + gy).mean(axis=0)
    gutter_cols = (extreme >= 0.82) & (activity <= 0.10)
    for start, end in runs_from_mask(gutter_cols):
        if end - start <= max(3, gray.shape[1] // 14):
            fallback[:, start:end] = stretched[:, start:end]
    return (fallback * 255.0 + 0.5).astype(np.uint8)


def make_separator_evidence_gray(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32, copy=False)
    lo, hi = sampled_percentile(data, [2.0, 98.0])
    if hi <= lo:
        return gray.copy()
    local = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    gx = np.abs(np.diff(local, axis=1, prepend=local[:, :1]))
    vertical_edge = smooth_1d(gx.mean(axis=0).astype(np.float32), max(3, int(round(gray.shape[1] * 0.0015))))
    column_mean = local.mean(axis=0)
    dark_response = np.clip((0.28 - column_mean) / 0.28, 0.0, 1.0)
    light_band = np.clip((column_mean - 0.78) / 0.22, 0.0, 1.0)
    band = np.maximum(dark_response, light_band)
    evidence = np.maximum(local * 0.72, vertical_edge[None, :] * 0.28)
    evidence = np.maximum(evidence, band[None, :] * 0.55)
    return (np.clip(evidence, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def normalize_score_image(score: np.ndarray, percentile: float = 99.4) -> np.ndarray:
    data = score.astype(np.float32, copy=False)
    hi = float(sampled_percentile(data, [percentile])[0])
    if hi <= 1e-6:
        return np.zeros(data.shape, dtype=np.float32)
    return np.clip(data / hi, 0.0, 1.0)


def make_content_evidence_gray(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32, copy=False) / 255.0
    if data.size == 0:
        return gray.copy()

    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    gradient = normalize_score_image(gx + gy, 99.2)

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
    neighbor_texture = (np.abs(data - north) + np.abs(data - south) + np.abs(data - west) + np.abs(data - east)) * 0.25
    texture = normalize_score_image(neighbor_texture, 99.2)

    local_mean = (data + north + south + west + east) * 0.2
    local_contrast = normalize_score_image(np.abs(data - local_mean), 99.0)

    tonal_presence = normalize_score_image(np.abs(data - float(np.median(sampled_values_for_percentile(data)))) * 0.35, 99.0)
    evidence = 0.42 * gradient + 0.34 * texture + 0.18 * local_contrast + 0.06 * tonal_presence
    evidence = np.clip(evidence, 0.0, 1.0)
    return (evidence * 255.0 + 0.5).astype(np.uint8)
