from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..utils import (
    runs_from_mask,
    sampled_percentile,
    sampled_values_for_percentile,
    smooth_1d,
)


@dataclass(frozen=True)
class DeskewFallbackEvidenceParameters:
    low_percentile: float = 0.5
    high_percentile: float = 99.5
    shadow_gamma: float = 0.72
    edge_weight: float = 2.0
    shadow_blend_weight: float = 0.82
    edge_blend_weight: float = 0.18
    extreme_dark_threshold: int = 35
    extreme_light_threshold: int = 235
    gutter_extreme_min_fraction: float = 0.82
    gutter_activity_max: float = 0.10
    gutter_run_width_ratio: float = 1.0 / 14.0
    gutter_run_width_min: int = 3


@dataclass(frozen=True)
class SeparatorEvidenceImageParameters:
    low_percentile: float = 2.0
    high_percentile: float = 98.0
    vertical_edge_smooth_ratio: float = 0.0015
    vertical_edge_smooth_min: int = 3
    tonal_dark_mean: float = 0.28
    tonal_light_mean: float = 0.78
    local_weight: float = 0.72
    vertical_edge_weight: float = 0.28
    tonal_band_weight: float = 0.55


@dataclass(frozen=True)
class ContentEvidenceImageParameters:
    gradient_percentile: float = 99.2
    texture_percentile: float = 99.2
    local_contrast_percentile: float = 99.0
    tonal_presence_multiplier: float = 0.35
    tonal_presence_percentile: float = 99.0
    gradient_weight: float = 0.42
    texture_weight: float = 0.34
    local_contrast_weight: float = 0.18
    tonal_presence_weight: float = 0.06


def make_deskew_fallback_gray(
    gray: np.ndarray,
    params: DeskewFallbackEvidenceParameters,
) -> np.ndarray:
    data = gray.astype(np.float32)
    lo, hi = sampled_percentile(data, [params.low_percentile, params.high_percentile])
    if hi <= lo:
        return gray.copy()
    stretched = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    shadow_lift = np.power(stretched, params.shadow_gamma)
    gx = np.abs(np.diff(shadow_lift, axis=1, prepend=shadow_lift[:, :1]))
    gy = np.abs(np.diff(shadow_lift, axis=0, prepend=shadow_lift[:1, :]))
    edge = np.clip((gx + gy) * params.edge_weight, 0.0, 1.0)
    fallback = np.clip(
        shadow_lift * params.shadow_blend_weight + edge * params.edge_blend_weight,
        0.0,
        1.0,
    )
    extreme = (
        (gray < params.extreme_dark_threshold)
        | (gray > params.extreme_light_threshold)
    ).mean(axis=0)
    activity = (gx + gy).mean(axis=0)
    gutter_cols = (
        (extreme >= params.gutter_extreme_min_fraction)
        & (activity <= params.gutter_activity_max)
    )
    for start, end in runs_from_mask(gutter_cols):
        if end - start <= max(
            params.gutter_run_width_min,
            int(round(gray.shape[1] * params.gutter_run_width_ratio)),
        ):
            fallback[:, start:end] = stretched[:, start:end]
    return (fallback * 255.0 + 0.5).astype(np.uint8)


def make_separator_evidence_gray(
    gray: np.ndarray,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    data = gray.astype(np.float32, copy=False)
    lo, hi = sampled_percentile(data, [params.low_percentile, params.high_percentile])
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
    dark_response = np.clip(
        (params.tonal_dark_mean - column_mean) / params.tonal_dark_mean,
        0.0,
        1.0,
    )
    light_band = np.clip(
        (column_mean - params.tonal_light_mean) / (1.0 - params.tonal_light_mean),
        0.0,
        1.0,
    )
    band = np.maximum(dark_response, light_band)
    evidence = np.maximum(
        local * params.local_weight,
        vertical_edge[None, :] * params.vertical_edge_weight,
    )
    evidence = np.maximum(evidence, band[None, :] * params.tonal_band_weight)
    return (np.clip(evidence, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def normalize_score_image(score: np.ndarray, percentile: float = 99.4) -> np.ndarray:
    data = score.astype(np.float32, copy=False)
    hi = float(sampled_percentile(data, [percentile])[0])
    if hi <= 1e-6:
        return np.zeros(data.shape, dtype=np.float32)
    return np.clip(data / hi, 0.0, 1.0)


def make_content_evidence_gray(
    gray: np.ndarray,
    params: ContentEvidenceImageParameters,
) -> np.ndarray:
    data = gray.astype(np.float32, copy=False) / 255.0
    if data.size == 0:
        return gray.copy()

    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    gradient = normalize_score_image(gx + gy, params.gradient_percentile)

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
    texture = normalize_score_image(neighbor_texture, params.texture_percentile)

    local_mean = (data + north + south + west + east) * 0.2
    local_contrast = normalize_score_image(np.abs(data - local_mean), params.local_contrast_percentile)

    tonal_presence = normalize_score_image(
        np.abs(data - float(np.median(sampled_values_for_percentile(data)))) * params.tonal_presence_multiplier,
        params.tonal_presence_percentile,
    )
    evidence = (
        params.gradient_weight * gradient
        + params.texture_weight * texture
        + params.local_contrast_weight * local_contrast
        + params.tonal_presence_weight * tonal_presence
    )
    evidence = np.clip(evidence, 0.0, 1.0)
    return (evidence * 255.0 + 0.5).astype(np.uint8)


__all__ = [
    "ContentEvidenceImageParameters",
    "DeskewFallbackEvidenceParameters",
    "SeparatorEvidenceImageParameters",
    "make_content_evidence_gray",
    "make_deskew_fallback_gray",
    "make_separator_evidence_gray",
    "normalize_score_image",
]
