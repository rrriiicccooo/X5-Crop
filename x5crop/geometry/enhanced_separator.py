from __future__ import annotations

import copy
from typing import Any, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Box, Gap
from ..runtime import AnalysisCache
from ..utils import clamp_float
from .boxes import box_cache_key
from .gap_search import constrain_gap_to_geometry, find_gap
from .detection_parameters import EnhancedSeparatorConfig, GapSearchConfig, RobustGridConfig, SeparatorProfileConfig
from .separator_cache import cached_enhanced_separator_profile


def find_enhanced_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    format_name: str,
    gap_search: GapSearchConfig | None = None,
    enhanced_config: EnhancedSeparatorConfig | None = None,
) -> Gap:
    config = enhanced_config or EnhancedSeparatorConfig()
    gap = find_gap(profile, expected, pitch, index, format_name, gap_search=gap_search)
    if gap.method != "detected":
        return gap
    if gap.score < config.min_score:
        return Gap(index, float(expected), gap.score, "equal")
    if gap.start is None or gap.end is None:
        return Gap(index, float(expected), gap.score, "equal")
    width = abs(float(gap.end) - float(gap.start))
    if width <= 0 or width > clamp_float(pitch * config.max_width_ratio, config.max_width_min, config.max_width_max):
        return Gap(index, float(expected), gap.score, "equal")
    if abs(gap.center - expected) > clamp_float(pitch * config.max_shift_ratio, config.max_shift_min, config.max_shift_max):
        return Gap(index, float(expected), gap.score, "equal")
    return Gap(index, gap.center, gap.score, "enhanced-detected", gap.start, gap.end)


def enhanced_separator_merge_cache_key(
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    format_name: str,
    policy_key: tuple[Any, ...] = (),
) -> tuple[Any, ...]:
    return (
        str(format_name),
        str(strip_mode),
        policy_key,
        box_cache_key(outer),
        round(float(origin), 4),
        round(float(pitch), 4),
        tuple(
            (
                int(gap.index),
                str(gap.method),
                round(float(gap.center), 4),
                round(float(gap.score), 6),
                None if gap.start is None else round(float(gap.start), 4),
                None if gap.end is None else round(float(gap.end), 4),
            )
            for gap in gaps
        ),
    )


def merge_enhanced_separator_gaps(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    format_name: str,
    cache: Optional[AnalysisCache] = None,
    robust_grid: RobustGridConfig | None = None,
    gap_search: GapSearchConfig | None = None,
    profile_config: SeparatorProfileConfig | None = None,
    enhanced_config: EnhancedSeparatorConfig | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0 or outer.height <= 0:
        return gaps, {"used": False, "reason": "empty_outer"}
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        policy_key = (
            robust_grid or RobustGridConfig(),
            gap_search or GapSearchConfig(),
            profile_config or SeparatorProfileConfig(),
            enhanced_config or EnhancedSeparatorConfig(),
        )
        cache_key = enhanced_separator_merge_cache_key(outer, gaps, origin, pitch, strip_mode, format_name, policy_key)
        cached = cache.enhanced_separator_merges.get(cache_key)
        if cached is not None:
            cached_gaps, cached_detail = cached
            return list(cached_gaps), copy.deepcopy(cached_detail)
    profile = cached_enhanced_separator_profile(cache, gray_work, outer, format_name, profile_config)
    merged: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for gap in gaps:
        if gap.method in HARD_GAP_METHODS:
            merged.append(gap)
            continue
        expected = origin + pitch * gap.index
        enhanced = find_enhanced_gap(profile, expected, pitch, gap.index, format_name, gap_search, enhanced_config)
        if enhanced.method == "enhanced-detected":
            merged.append(enhanced)
            accepted.append(
                {
                    "index": int(gap.index),
                    "center": float(enhanced.center),
                    "score": float(enhanced.score),
                    "replaced_method": gap.method,
                }
            )
        else:
            merged.append(gap)
            rejected.append(
                {
                    "index": int(gap.index),
                    "score": float(enhanced.score),
                    "method": enhanced.method,
                    "kept_method": gap.method,
                }
            )
    constrained = [
        constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode, robust_grid)
        if gap.method == "enhanced-detected" else gap
        for gap in merged
    ]
    detail = {
        "used": True,
        "accepted": accepted,
        "rejected": rejected[:8],
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }
    if cache_key is not None and cache is not None:
        cache.enhanced_separator_merges[cache_key] = (list(constrained), copy.deepcopy(detail))
    return constrained, detail


def should_run_enhanced_separator_analysis(
    analysis: str,
    gaps: list[Gap],
    count: int,
    enhanced_config: EnhancedSeparatorConfig | None = None,
) -> bool:
    config = enhanced_config or EnhancedSeparatorConfig()
    if analysis == "off":
        return False
    if analysis == "always":
        return True
    expected = max(0, count - 1)
    if expected <= 0:
        return False
    hard = [gap for gap in gaps if gap.method in HARD_GAP_METHODS]
    model_only = [gap for gap in gaps if gap.method in {"equal", "grid"}]
    low_score_hard = any(gap.score < config.auto_low_score for gap in hard)
    return len(hard) < expected or bool(model_only) or low_score_hard
