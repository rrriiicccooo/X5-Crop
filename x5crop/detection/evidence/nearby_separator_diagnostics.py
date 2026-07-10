from __future__ import annotations

import copy
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...cache.separator import cached_separator_profile
from ...domain import Box, Gap
from ...gap_methods import is_hard_gap_method
from ...geometry.boxes import box_cache_key
from ...geometry.detection_parameters import SeparatorProfileParameters
from ...geometry.nearby_separator import nearby_separator_search_detail
from ...policies.parameters.diagnostics import NearbySeparatorDiagnosticsParameters


def nearby_separator_diagnostic_detail(
    gray_work: np.ndarray,
    work_outer: Box,
    gap: Gap,
    pitch: float,
    start: int,
    end: int,
    nearby_policy: NearbySeparatorDiagnosticsParameters,
    profile_policy: SeparatorProfileParameters,
    cache: AnalysisCache | None,
) -> dict[str, Any]:
    if not is_hard_gap_method(gap.method) or pitch <= 0:
        return {"searched": False, "reason": "not_hard_gap"}
    cache_key: tuple[Any, ...] | None = None
    if cache is not None:
        cache_key = (
            "nearby_separator_diagnostic",
            profile_policy,
            nearby_policy,
            box_cache_key(work_outer),
            int(gap.index),
            str(gap.method),
            float(gap.center),
            float(gap.score),
            None if gap.start is None else float(gap.start),
            None if gap.end is None else float(gap.end),
            float(pitch),
            int(start),
            int(end),
        )
        cached = cache.nearby_separator_details.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
    crop = gray_work[work_outer.top:work_outer.bottom, work_outer.left:work_outer.right]
    if crop.size == 0:
        return {"searched": False, "reason": "empty_outer"}
    profile = cached_separator_profile(cache, gray_work, work_outer, profile_policy)
    if profile.size == 0:
        return {"searched": False, "reason": "empty_profile"}
    search_gap = Gap(
        gap.index,
        gap.center,
        gap.score,
        gap.method,
        float(start - work_outer.left),
        float(end - work_outer.left),
        gap.lane_box,
    )
    detail = nearby_separator_search_detail(
        profile,
        search_gap,
        pitch,
        nearby_policy,
        score_add=nearby_policy.detail_score_add,
        score_multiplier=nearby_policy.detail_score_multiplier,
        absolute_center_offset=float(work_outer.left),
    ) or {"searched": False, "reason": "empty_search_window"}
    if cache_key is not None and cache is not None:
        cache.nearby_separator_details[cache_key] = copy.deepcopy(detail)
    return detail
