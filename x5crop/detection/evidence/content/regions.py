from __future__ import annotations

import numpy as np

from ....domain import Box
from ....policies.runtime.content import ContentPolicy
from ....utils import runs_from_mask, sampled_percentile, smooth_1d


def content_region_runs(
    evidence: np.ndarray,
    region: Box,
    frame_width_reference_px: float,
    *,
    content_policy: ContentPolicy,
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
    low, middle, high = sampled_percentile(smoothed, parameters.percentiles)
    threshold = max(
        parameters.threshold_min,
        min(
            parameters.threshold_max,
            float(low + (high - low) * parameters.low_percentile_weight),
            float(middle) * parameters.mid_percentile_multiplier,
        ),
    )
    minimum_width = max(
        parameters.min_run_width_px,
        int(
            round(
                max(1.0, float(frame_width_reference_px))
                * parameters.min_run_ratio
            )
        ),
    )
    return tuple(
        (region.left + start, region.left + end)
        for start, end in runs_from_mask(smoothed >= threshold)
        if end - start >= minimum_width
    )
