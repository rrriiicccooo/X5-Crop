from __future__ import annotations

import numpy as np

from ....cache import MeasurementCache
from ....domain import Box
from ....policies.runtime.content import ContentPolicy
from ....utils import bbox_from_mask, runs_from_mask, sampled_percentile, smooth_1d


def content_region_runs(
    evidence: np.ndarray,
    outer: Box,
    count: int,
    *,
    content_policy: ContentPolicy,
) -> tuple[tuple[int, int], ...]:
    profile_parameters = content_policy.profile
    crop = evidence[outer.top : outer.bottom, outer.left : outer.right].astype(
        np.float32
    ) / 255.0
    if crop.size == 0:
        return ()
    profile = crop.mean(axis=0)
    smooth_window = max(
        profile_parameters.smooth_min_px,
        int(round(max(1, outer.width) * profile_parameters.smooth_ratio)),
    )
    smoothed = smooth_1d(profile.astype(np.float32), smooth_window)
    low, middle, high = sampled_percentile(
        smoothed,
        profile_parameters.percentiles,
    )
    threshold = max(
        profile_parameters.threshold_min,
        min(
            profile_parameters.threshold_max,
            float(
                low
                + (high - low) * profile_parameters.low_percentile_weight
            ),
            float(middle) * profile_parameters.mid_percentile_multiplier,
        ),
    )
    minimum_width = max(
        profile_parameters.min_run_width_px,
        int(
            round(
                outer.width
                / max(1, count)
                * profile_parameters.min_run_ratio
            )
        ),
    )
    filtered = tuple(
        (outer.left + start, outer.left + end)
        for start, end in runs_from_mask(smoothed >= threshold)
        if end - start >= minimum_width
    )
    return filtered


def select_content_runs(
    runs: tuple[tuple[int, int], ...],
    count: int,
) -> tuple[tuple[int, int], ...]:
    if len(runs) <= count:
        return runs
    selected = sorted(
        runs,
        key=lambda run: run[1] - run[0],
        reverse=True,
    )[:count]
    return tuple(sorted(selected))


def content_mask_region(
    evidence_float: np.ndarray,
    gray_work_shape: tuple[int, int],
    cache: MeasurementCache,
    *,
    content_policy: ContentPolicy,
) -> Box | None:
    parameters = content_policy.mask
    cache_key = (parameters,)
    if cache_key in cache.content_mask_regions:
        return cache.content_mask_regions[cache_key]
    work_height, work_width = gray_work_shape
    low, middle, high = sampled_percentile(
        evidence_float,
        parameters.percentiles,
    )
    threshold = max(
        parameters.threshold_min,
        min(
            parameters.threshold_max,
            float(low + (high - low) * parameters.p55_weight),
            float(middle) * parameters.p75_multiplier,
        ),
    )
    region = bbox_from_mask(
        evidence_float >= threshold,
        min_row_fraction=parameters.bbox_min_fraction,
        min_col_fraction=parameters.bbox_min_fraction,
    )
    if region is not None and region.valid():
        region = region.expand(
            max(2, int(round(work_width * parameters.outer_expand_ratio))),
            max(2, int(round(work_height * parameters.outer_expand_ratio))),
            work_width,
            work_height,
        )
    cache.content_mask_regions[cache_key] = region
    return region
