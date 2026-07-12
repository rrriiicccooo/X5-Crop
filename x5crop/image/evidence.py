from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import (
    FIVE_POINT_MEAN_WEIGHT,
    FOUR_NEIGHBOR_MEAN_WEIGHT,
    UINT8_MAX_VALUE,
    UINT8_ROUNDING_OFFSET,
)
from ..utils import (
    require_nonnegative,
    require_percentile,
    require_positive,
    require_unit_interval,
    runs_from_mask,
    sampled_percentile,
    smooth_1d,
)
from .statistics import ImageMeasurementStatistics


CONTENT_EVIDENCE_COMPONENT_COUNT = 4


@dataclass(frozen=True)
class DeskewFallbackEvidenceParameters:
    low_percentile: float = 0.5
    high_percentile: float = 99.5
    shadow_gamma: float = 0.72
    edge_weight: float = 2.0
    shadow_blend_weight: float = 0.82
    edge_blend_weight: float = 0.18
    gutter_extreme_min_fraction: float = 0.82
    gutter_activity_max: float = 0.10
    gutter_run_width_ratio: float = 1.0 / 14.0
    gutter_run_width_min: int = 3
    maximum_percentile_samples: int = 1_000_000

    def __post_init__(self) -> None:
        require_percentile("deskew fallback low percentile", self.low_percentile)
        require_percentile("deskew fallback high percentile", self.high_percentile)
        if self.high_percentile <= self.low_percentile:
            raise ValueError("deskew fallback high percentile must follow low")
        require_positive("deskew fallback shadow gamma", self.shadow_gamma)
        require_nonnegative("deskew fallback edge weight", self.edge_weight)
        require_nonnegative(
            "deskew fallback shadow blend weight",
            self.shadow_blend_weight,
        )
        require_nonnegative(
            "deskew fallback edge blend weight",
            self.edge_blend_weight,
        )
        if self.shadow_blend_weight + self.edge_blend_weight <= 0.0:
            raise ValueError("deskew fallback blend requires positive support")
        require_unit_interval(
            "deskew fallback gutter extreme fraction",
            self.gutter_extreme_min_fraction,
        )
        require_unit_interval(
            "deskew fallback gutter activity",
            self.gutter_activity_max,
        )
        require_nonnegative(
            "deskew fallback gutter width ratio",
            self.gutter_run_width_ratio,
        )
        require_positive(
            "deskew fallback gutter minimum width",
            self.gutter_run_width_min,
        )
        require_positive(
            "deskew fallback percentile sample budget",
            self.maximum_percentile_samples,
        )


@dataclass(frozen=True)
class SeparatorEvidenceImageParameters:
    low_percentile: float = 2.0
    high_percentile: float = 98.0
    vertical_edge_smooth_ratio: float = 0.0015
    vertical_edge_smooth_min: int = 3
    tonal_low_percentile: float = 10.0
    tonal_high_percentile: float = 90.0
    local_weight: float = 0.72
    vertical_edge_weight: float = 0.28
    tonal_band_weight: float = 0.55
    numerical_floor: float = 1e-6
    maximum_percentile_samples: int = 1_000_000

    def __post_init__(self) -> None:
        for name, value in (
            ("separator image low percentile", self.low_percentile),
            ("separator image high percentile", self.high_percentile),
            ("separator tonal low percentile", self.tonal_low_percentile),
            ("separator tonal high percentile", self.tonal_high_percentile),
        ):
            require_percentile(name, value)
        if self.high_percentile <= self.low_percentile:
            raise ValueError("separator image high percentile must follow low")
        if self.tonal_high_percentile <= self.tonal_low_percentile:
            raise ValueError("separator tonal high percentile must follow low")
        require_nonnegative(
            "separator vertical-edge smoothing ratio",
            self.vertical_edge_smooth_ratio,
        )
        require_positive(
            "separator vertical-edge minimum width",
            self.vertical_edge_smooth_min,
        )
        for name, value in (
            ("separator local weight", self.local_weight),
            ("separator vertical-edge weight", self.vertical_edge_weight),
            ("separator tonal-band weight", self.tonal_band_weight),
        ):
            require_nonnegative(name, value)
        require_positive("separator image numerical floor", self.numerical_floor)
        require_positive(
            "separator image percentile sample budget",
            self.maximum_percentile_samples,
        )


@dataclass(frozen=True)
class ContentEvidenceImageParameters:
    gradient_percentile: float = 99.2
    texture_percentile: float = 99.2
    local_contrast_percentile: float = 99.0
    tonal_presence_percentile: float = 99.0
    numerical_floor: float = 1e-6
    maximum_percentile_samples: int = 1_000_000
    minimum_consensus_channels: int = 2

    def __post_init__(self) -> None:
        for name, value in (
            ("content gradient percentile", self.gradient_percentile),
            ("content texture percentile", self.texture_percentile),
            ("content local-contrast percentile", self.local_contrast_percentile),
            ("content tonal-presence percentile", self.tonal_presence_percentile),
        ):
            require_percentile(name, value)
        require_positive("content evidence numerical floor", self.numerical_floor)
        require_positive(
            "content evidence percentile sample budget",
            self.maximum_percentile_samples,
        )
        require_positive(
            "content evidence consensus channel count",
            self.minimum_consensus_channels,
        )
        if self.minimum_consensus_channels > CONTENT_EVIDENCE_COMPONENT_COUNT:
            raise ValueError("content evidence consensus exceeds component count")


def adaptive_activation_threshold(
    values: np.ndarray,
    percentile: float,
    minimum_range: float,
    maximum_percentile_samples: int,
) -> float | None:
    if not values.size:
        return None
    minimum = float(values.min())
    maximum = float(values.max())
    if maximum - minimum <= float(minimum_range):
        return None
    return float(
        sampled_percentile(
            values,
            [percentile],
            maximum_percentile_samples,
        )[0]
    )


def make_deskew_fallback_gray(
    gray: np.ndarray,
    params: DeskewFallbackEvidenceParameters,
) -> np.ndarray:
    data = gray.astype(np.float32)
    lo, hi = sampled_percentile(
        data,
        [params.low_percentile, params.high_percentile],
        params.maximum_percentile_samples,
    )
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
    extreme = ((data <= lo) | (data >= hi)).mean(axis=0)
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
    return (
        fallback * UINT8_MAX_VALUE + UINT8_ROUNDING_OFFSET
    ).astype(np.uint8)


def make_separator_evidence_gray(
    gray: np.ndarray,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    data = gray.astype(np.float32, copy=False)
    lo, hi = sampled_percentile(
        data,
        [params.low_percentile, params.high_percentile],
        params.maximum_percentile_samples,
    )
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
    tonal_low, tonal_high = sampled_percentile(
        column_mean,
        [
            params.tonal_low_percentile,
            params.tonal_high_percentile,
        ],
        params.maximum_percentile_samples,
    )
    tonal_center = float(np.median(column_mean))
    dark_response = np.clip(
        (tonal_center - column_mean)
        / max(params.numerical_floor, tonal_center - tonal_low),
        0.0,
        1.0,
    )
    light_band = np.clip(
        (column_mean - tonal_center)
        / max(params.numerical_floor, tonal_high - tonal_center),
        0.0,
        1.0,
    )
    band = np.maximum(dark_response, light_band)
    evidence = np.maximum(
        local * params.local_weight,
        vertical_edge[None, :] * params.vertical_edge_weight,
    )
    evidence = np.maximum(evidence, band[None, :] * params.tonal_band_weight)
    return (
        np.clip(evidence, 0.0, 1.0) * UINT8_MAX_VALUE
        + UINT8_ROUNDING_OFFSET
    ).astype(np.uint8)


def normalize_score_image(
    score: np.ndarray,
    percentile: float,
    numerical_floor: float,
    maximum_percentile_samples: int,
) -> np.ndarray:
    data = score.astype(np.float32, copy=False)
    hi = float(
        sampled_percentile(
            data,
            [percentile],
            maximum_percentile_samples,
        )[0]
    )
    if hi <= numerical_floor:
        return np.zeros(data.shape, dtype=np.float32)
    return np.clip(data / hi, 0.0, 1.0)


def make_content_evidence_gray(
    gray: np.ndarray,
    statistics: ImageMeasurementStatistics,
    params: ContentEvidenceImageParameters,
) -> np.ndarray:
    data = gray.astype(np.float32, copy=False) / UINT8_MAX_VALUE
    if data.size == 0:
        return gray.copy()

    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    gradient = normalize_score_image(
        gx + gy,
        params.gradient_percentile,
        params.numerical_floor,
        params.maximum_percentile_samples,
    )

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
    neighbor_texture = (
        np.abs(data - north)
        + np.abs(data - south)
        + np.abs(data - west)
        + np.abs(data - east)
    ) * FOUR_NEIGHBOR_MEAN_WEIGHT
    texture = normalize_score_image(
        neighbor_texture,
        params.texture_percentile,
        params.numerical_floor,
        params.maximum_percentile_samples,
    )

    local_mean = (
        data + north + south + west + east
    ) * FIVE_POINT_MEAN_WEIGHT
    local_contrast = normalize_score_image(
        np.abs(data - local_mean),
        params.local_contrast_percentile,
        params.numerical_floor,
        params.maximum_percentile_samples,
    )

    tonal_presence = normalize_score_image(
        np.abs(
            data - float(statistics.intensity_median) / UINT8_MAX_VALUE
        ),
        params.tonal_presence_percentile,
        params.numerical_floor,
        params.maximum_percentile_samples,
    )
    stack = np.stack((gradient, texture, local_contrast, tonal_presence), axis=0)
    consensus_index = -int(params.minimum_consensus_channels)
    evidence = np.partition(stack, consensus_index, axis=0)[consensus_index]
    evidence = np.clip(evidence, 0.0, 1.0)
    return (
        evidence * UINT8_MAX_VALUE + UINT8_ROUNDING_OFFSET
    ).astype(np.uint8)
