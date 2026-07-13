from __future__ import annotations

import numpy as np

from ....cache import MeasurementCache, MeasurementRegionKey
from ....configuration.content import ContentEvidenceParameters
from ....domain import Box
from ....image.evidence import activation_mask, adaptive_activation_threshold


def content_evidence_threshold(
    evidence: np.ndarray,
    parameters: ContentEvidenceParameters,
) -> float | None:
    return adaptive_activation_threshold(
        evidence,
        parameters.activation_percentile,
        parameters.minimum_evidence_range,
        parameters.maximum_percentile_samples,
    )


def cached_content_evidence_threshold(
    cache: MeasurementCache,
    region: Box,
    parameters: ContentEvidenceParameters,
) -> float | None:
    absolute = region.clamp(
        cache.content_evidence_float_work.shape[1],
        cache.content_evidence_float_work.shape[0],
    )
    if not absolute.valid():
        return None
    key = MeasurementRegionKey(parameters, absolute)
    found = key in cache.content_evidence_thresholds
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        evidence = cache.content_evidence_float_work[
            absolute.top : absolute.bottom,
            absolute.left : absolute.right,
        ]
        cache.content_evidence_thresholds[key] = content_evidence_threshold(
            evidence,
            parameters,
        )
    return cache.content_evidence_thresholds[key]


def sample_supports_content(
    sample: np.ndarray,
    threshold: float,
    minimum_active_pixels: int,
) -> bool:
    required = int(minimum_active_pixels)
    return bool(
        sample.size >= required
        and int(np.count_nonzero(activation_mask(sample, threshold))) >= required
    )
