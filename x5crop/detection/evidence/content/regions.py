from __future__ import annotations

import numpy as np

from ....cache import MeasurementCache, MeasurementRegionKey
from ....configuration.content import ContentConfiguration
from ....domain import Box
from ....image.content import ContentRegionObservation
from ....image.evidence import (
    adaptive_activation_threshold,
    spatially_supported_activation_mask,
)
from ....image.constants import UINT8_MAX_VALUE
from ....utils import runs_from_mask, sampled_percentile, smooth_1d


CONTENT_SMOOTHING_WINDOW_ENDPOINT_COUNT = 2
PROFILE_POPULATION_COUNT = 2
PROFILE_THRESHOLD_MIDPOINT_WEIGHT = 0.5


def _distinct_profile_population_thresholds(
    profile: np.ndarray,
    minimum_profile_range: float,
    minimum_class_samples: int,
) -> tuple[float | None, float | None]:
    remaining = profile.astype(np.float64, copy=False)
    reliable_threshold: float | None = None
    guidance_threshold: float | None = None
    while remaining.size >= minimum_class_samples * PROFILE_POPULATION_COUNT:
        values = np.sort(remaining)
        if float(values[-1] - values[0]) < minimum_profile_range:
            break
        cumulative = np.cumsum(values)
        cumulative_squares = np.cumsum(values * values)
        split_counts = np.arange(1, values.size, dtype=np.float64)
        remaining_counts = float(values.size) - split_counts
        within_lower = (
            cumulative_squares[:-1]
            - cumulative[:-1] * cumulative[:-1] / split_counts
        )
        upper_sum = cumulative[-1] - cumulative[:-1]
        within_upper = (
            cumulative_squares[-1]
            - cumulative_squares[:-1]
            - upper_sum * upper_sum / remaining_counts
        )
        valid = (
            split_counts >= minimum_class_samples
        ) & (
            remaining_counts >= minimum_class_samples
        ) & (
            values[1:] > values[:-1]
        )
        valid_indices = np.flatnonzero(valid)
        if not valid_indices.size:
            break
        best = int(valid_indices[np.argmin((within_lower + within_upper)[valid])])
        threshold = float(
            (values[best] + values[best + 1])
            * PROFILE_THRESHOLD_MIDPOINT_WEIGHT
        )
        if reliable_threshold is None:
            reliable_threshold = threshold
        guidance_threshold = threshold
        remaining = remaining[remaining < threshold]
    return reliable_threshold, guidance_threshold


def _broad_content_mask(
    profile: np.ndarray,
    low_activity_percentile: float,
    high_activity_percentile: float,
    minimum_profile_range: float,
    minimum_valley_width: int,
    maximum_percentile_samples: int,
) -> np.ndarray:
    low, high = sampled_percentile(
        profile,
        (low_activity_percentile, high_activity_percentile),
        maximum_percentile_samples,
    )
    if float(high - low) < minimum_profile_range:
        return np.zeros(profile.shape, dtype=bool)
    valleys = tuple(
        (start, end)
        for start, end in runs_from_mask(profile <= float(low))
        if end - start >= minimum_valley_width
    )
    if len(valleys) < 2:
        return np.zeros(profile.shape, dtype=bool)
    broad = np.zeros(profile.shape, dtype=bool)
    broad[valleys[0][1] : valleys[-1][0]] = True
    for start, end in valleys[1:-1]:
        broad[start:end] = False
    return broad


def content_region_observation(
    evidence: np.ndarray,
    region: Box,
    *,
    content_configuration: ContentConfiguration,
) -> ContentRegionObservation:
    parameters = content_configuration.profile
    smooth_window = max(
        parameters.smooth_min_px,
        int(round(max(1, region.width) * parameters.smooth_ratio)),
    )
    position_uncertainty_px = (
        smooth_window + 1
    ) // CONTENT_SMOOTHING_WINDOW_ENDPOINT_COUNT
    crop = evidence[region.top : region.bottom, region.left : region.right].astype(
        np.float32
    ) / UINT8_MAX_VALUE
    if crop.size == 0:
        return ContentRegionObservation(region, (), position_uncertainty_px)
    evidence_threshold = adaptive_activation_threshold(
        crop,
        content_configuration.evidence.activation_percentile,
        content_configuration.evidence.minimum_evidence_range,
        content_configuration.evidence.maximum_percentile_samples,
    )
    if evidence_threshold is None:
        return ContentRegionObservation(region, (), position_uncertainty_px)
    spatial_support = spatially_supported_activation_mask(
        crop,
        evidence_threshold,
        content_configuration.evidence.minimum_active_pixels,
    )
    supported_profile = np.where(spatial_support, crop, 0.0).mean(
        axis=0,
        dtype=np.float32,
    )
    smoothed_supported = smooth_1d(
        supported_profile.astype(np.float32),
        smooth_window,
    )
    minimum_width = max(
        int(parameters.min_run_width_px),
        smooth_window * CONTENT_SMOOTHING_WINDOW_ENDPOINT_COUNT,
    )
    reliable_threshold, guidance_threshold = _distinct_profile_population_thresholds(
        smoothed_supported,
        parameters.minimum_profile_range,
        minimum_width,
    )
    localized_content = (
        np.zeros(smoothed_supported.shape, dtype=bool)
        if reliable_threshold is None
        else smoothed_supported >= reliable_threshold
    )
    guidance_content = (
        np.zeros(smoothed_supported.shape, dtype=bool)
        if guidance_threshold is None
        else smoothed_supported >= guidance_threshold
    )
    smoothed_appearance = smooth_1d(
        crop.mean(axis=0, dtype=np.float32),
        smooth_window,
    )
    broad_content = _broad_content_mask(
        smoothed_appearance,
        parameters.low_activity_percentile,
        parameters.high_activity_percentile,
        parameters.minimum_profile_range,
        max(
            int(parameters.min_run_width_px),
            smooth_window // CONTENT_SMOOTHING_WINDOW_ENDPOINT_COUNT,
        ),
        content_configuration.evidence.maximum_percentile_samples,
    )
    reliable_runs = tuple(
        (region.left + start, region.left + end)
        for start, end in runs_from_mask(localized_content)
        if end - start >= minimum_width
    )
    guidance_runs = tuple(
        (region.left + start, region.left + end)
        for start, end in runs_from_mask(guidance_content | broad_content)
        if end - start >= minimum_width
    )
    return ContentRegionObservation(
        region,
        reliable_runs,
        position_uncertainty_px,
        guidance_runs,
    )


def cached_content_region_observation(
    cache: MeasurementCache,
    region: Box,
    configuration: ContentConfiguration,
) -> ContentRegionObservation:
    absolute = region.clamp(cache.gray_work.shape[1], cache.gray_work.shape[0])
    if not absolute.valid():
        raise ValueError("content observation requires a valid workspace region")
    key = MeasurementRegionKey(configuration, absolute)
    found = key in cache.content_region_observations
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        cache.content_region_observations[key] = content_region_observation(
            cache.content_evidence_work,
            absolute,
            content_configuration=configuration,
        )
    return cache.content_region_observations[key]
