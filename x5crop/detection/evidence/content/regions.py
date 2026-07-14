from __future__ import annotations

import numpy as np

from ....cache import MeasurementCache, MeasurementRegionKey
from ....configuration.content import ContentConfiguration
from ....domain import Box
from ....image.content import ContentRegionObservation
from ....image.evidence import (
    activation_mask,
    adaptive_activation_threshold,
    spatially_supported_activation_mask,
)
from ....image.constants import UINT8_MAX_VALUE
from ....utils import runs_from_mask, smooth_1d


CONTENT_SMOOTHING_WINDOW_ENDPOINT_COUNT = 2


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
    profile = spatial_support.mean(axis=0, dtype=np.float32)
    smoothed = smooth_1d(profile.astype(np.float32), smooth_window)
    threshold = adaptive_activation_threshold(
        smoothed,
        parameters.activation_percentile,
        content_configuration.evidence.minimum_evidence_range,
        content_configuration.evidence.maximum_percentile_samples,
    )
    if threshold is None:
        return ContentRegionObservation(region, (), position_uncertainty_px)
    minimum_width = int(parameters.min_run_width_px)
    return ContentRegionObservation(
        region,
        tuple(
            (region.left + start, region.left + end)
            for start, end in runs_from_mask(activation_mask(smoothed, threshold))
            if end - start >= minimum_width
        ),
        position_uncertainty_px,
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
