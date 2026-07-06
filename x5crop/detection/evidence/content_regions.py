from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ...cache import AnalysisCache
from ...domain import Box
from ...formats import FormatSpec
from ...geometry.boxes import box_cache_key
from ...policies.runtime.content import ContentPolicy
from ...utils import bbox_from_mask, runs_from_mask, sampled_percentile, smooth_1d
from .content_signal import resolve_content_policy


CONTENT_REGION_HINT_ROLE = "content_region_hint"
CONTENT_BBOX_HINT_ROLE = "content_bbox_hint"
CONTENT_RUN_HINT_ROLE = "content_run_hint"


def content_region_runs(
    evidence: np.ndarray,
    outer: Box,
    count: int,
    format_name: str,
    cache: Optional[AnalysisCache] = None,
    content_policy: Optional[ContentPolicy] = None,
) -> tuple[list[tuple[int, int]], dict[str, Any]]:
    content_policy = resolve_content_policy(format_name, "full", content_policy)
    profile_policy = content_policy.profile
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None and evidence is cache.content_evidence_work:
        cache_key = (str(format_name), int(count), *box_cache_key(outer), profile_policy)
        cached = cache.content_region_runs.get(cache_key)
        if cached is not None:
            runs, detail = cached
            return list(runs), copy.deepcopy(detail)
    crop = evidence[outer.top:outer.bottom, outer.left:outer.right].astype(np.float32) / 255.0
    if crop.size == 0:
        return [], {"used": False, "role": CONTENT_RUN_HINT_ROLE, "reason": "empty_content_outer"}
    profile = crop.mean(axis=0)
    smooth_window = max(5, int(round(max(1, outer.width) * profile_policy.smooth_ratio)))
    smoothed = smooth_1d(profile.astype(np.float32), smooth_window)
    p35, p65, p90 = sampled_percentile(smoothed, [35, 65, 90])
    threshold = max(
        profile_policy.threshold_min,
        min(
            profile_policy.threshold_max,
            float(p35 + (p90 - p35) * profile_policy.p35_weight),
            float(p65) * profile_policy.p65_multiplier,
        ),
    )
    runs = runs_from_mask(smoothed >= threshold)
    min_width = max(6, int(round(outer.width / max(1, count) * profile_policy.min_run_ratio)))
    filtered: list[tuple[int, int]] = []
    for start, end in runs:
        if end - start >= min_width:
            filtered.append((outer.left + start, outer.left + end))
    detail = {
        "used": True,
        "role": CONTENT_RUN_HINT_ROLE,
        "profile_threshold": threshold,
        "profile_smooth_window": smooth_window,
        "profile_percentiles": {"p35": float(p35), "p65": float(p65), "p90": float(p90)},
        "raw_run_count": len(runs),
        "usable_run_count": len(filtered),
        "min_run_width": min_width,
    }
    if cache_key is not None:
        cache.content_region_runs[cache_key] = (list(filtered), copy.deepcopy(detail))
    return filtered, detail


def select_content_runs(runs: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
    if len(runs) <= count:
        return runs
    ordered = sorted(runs, key=lambda run: run[1] - run[0], reverse=True)[:count]
    return sorted(ordered)


def content_mask_region_detail(
    evidence_float: np.ndarray,
    gray_work_shape: tuple[int, int],
    fmt: FormatSpec,
    cache: Optional[AnalysisCache] = None,
    content_policy: Optional[ContentPolicy] = None,
) -> dict[str, Any]:
    content_policy = resolve_content_policy(fmt.name, "full", content_policy)
    mask_policy = content_policy.mask
    cache_key = (fmt.name, mask_policy)
    if cache is not None:
        cached = cache.content_mask_details.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
    wh, ww = gray_work_shape
    p55, p75, p92 = sampled_percentile(evidence_float, mask_policy.percentiles)
    mask_threshold = max(
        mask_policy.threshold_min,
        min(
            mask_policy.threshold_max,
            float(p55 + (p92 - p55) * mask_policy.p55_weight),
            float(p75) * mask_policy.p75_multiplier,
        ),
    )
    mask = evidence_float >= mask_threshold
    outer = bbox_from_mask(
        mask,
        min_row_fraction=mask_policy.bbox_min_fraction,
        min_col_fraction=mask_policy.bbox_min_fraction,
    )
    detail: dict[str, Any] = {
        "used": True,
        "role": CONTENT_BBOX_HINT_ROLE,
        "mask_threshold": float(mask_threshold),
        "mask_percentiles": {"p55": float(p55), "p75": float(p75), "p92": float(p92)},
        "outer": None if outer is None else asdict(outer),
    }
    if outer is not None and outer.valid():
        expanded = outer.expand(
            max(2, int(round(ww * mask_policy.outer_expand_ratio))),
            max(2, int(round(wh * mask_policy.outer_expand_ratio))),
            ww,
            wh,
        )
        detail["outer"] = asdict(expanded)
    if cache is not None:
        cache.content_mask_details[cache_key] = copy.deepcopy(detail)
    return detail


__all__ = [
    "CONTENT_BBOX_HINT_ROLE",
    "CONTENT_REGION_HINT_ROLE",
    "CONTENT_RUN_HINT_ROLE",
    "content_mask_region_detail",
    "content_region_runs",
    "select_content_runs",
]
