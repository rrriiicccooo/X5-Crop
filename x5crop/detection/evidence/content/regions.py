from __future__ import annotations

import numpy as np

from ....domain import Box
from ....configuration.content import ContentConfiguration
from ....image.evidence import adaptive_activation_threshold
from ....utils import runs_from_mask, smooth_1d


def content_region_runs(
    evidence: np.ndarray,
    region: Box,
    *,
    content_policy: ContentConfiguration,
) -> tuple[tuple[int, int], ...]:
    parameters = content_policy.profile
    crop = evidence[region.top : region.bottom, region.left : region.right].astype(
        np.float32
    ) / 255.0
    if crop.size == 0:
        return ()
    profile = crop.mean(axis=0)
    smooth_window = max(
        parameters.smooth_min_px,
        int(round(max(1, region.width) * parameters.smooth_ratio)),
    )
    smoothed = smooth_1d(profile.astype(np.float32), smooth_window)
    threshold = adaptive_activation_threshold(
        smoothed,
        parameters.activation_percentile,
        1e-6,
    )
    if threshold is None:
        return ()
    minimum_width = int(parameters.min_run_width_px)
    return tuple(
        (region.left + start, region.left + end)
        for start, end in runs_from_mask(smoothed >= threshold)
        if end - start >= minimum_width
    )
