from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....domain import Box
from ....configuration.content import ContentConfiguration
from ....image.evidence import (
    activation_mask,
    adaptive_activation_threshold,
    spatially_supported_activation_mask,
)
from ....image.constants import UINT8_MAX_VALUE
from ....utils import runs_from_mask, smooth_1d


CONTENT_SMOOTHING_WINDOW_ENDPOINT_COUNT = 2


@dataclass(frozen=True)
class ContentRegionObservation:
    runs: tuple[tuple[int, int], ...]
    position_uncertainty_px: int

    def __post_init__(self) -> None:
        if self.position_uncertainty_px < 0:
            raise ValueError("content position uncertainty must be non-negative")
        if any(end <= start for start, end in self.runs):
            raise ValueError("content runs must have positive extent")


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
        return ContentRegionObservation((), position_uncertainty_px)
    evidence_threshold = adaptive_activation_threshold(
        crop,
        content_configuration.evidence.activation_percentile,
        content_configuration.evidence.minimum_evidence_range,
        content_configuration.evidence.maximum_percentile_samples,
    )
    if evidence_threshold is None:
        return ContentRegionObservation((), position_uncertainty_px)
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
        return ContentRegionObservation((), position_uncertainty_px)
    minimum_width = int(parameters.min_run_width_px)
    return ContentRegionObservation(
        tuple(
            (region.left + start, region.left + end)
            for start, end in runs_from_mask(activation_mask(smoothed, threshold))
            if end - start >= minimum_width
        ),
        position_uncertainty_px,
    )
