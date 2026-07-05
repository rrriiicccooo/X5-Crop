from __future__ import annotations

import copy
from typing import Any, Optional

import numpy as np

from ..constants import GAP_DETECTED, GAP_ENHANCED_DETECTED, GAP_EQUAL, GAP_GRID, HARD_GAP_METHODS
from ..domain import Box, Gap
from ..cache import AnalysisCache
from ..utils import clamp_float
from .boxes import box_cache_key
from .gap_geometry import constrain_gap_to_geometry
from .gap_search import find_detected_gap
from .model_gaps import equal_model_gap
from .detection_parameters import (
    EnhancedSeparatorParameters,
    GapSearchParameters,
    RobustGridParameters,
    SeparatorProfileParameters,
)
from .separator_cache import cached_enhanced_separator_profile


def enhanced_gap_fallback(index: int, expected: float, score: float) -> Gap:
    return equal_model_gap(index, expected, score)


def enhanced_gap_width(gap: Gap) -> float:
    if gap.start is None or gap.end is None:
        return 0.0
    return abs(float(gap.end) - float(gap.start))


def enhanced_gap_is_valid(gap: Gap, expected: float, pitch: float, config: EnhancedSeparatorParameters) -> bool:
    if gap.method != GAP_DETECTED or gap.score < config.min_score:
        return False
    width = enhanced_gap_width(gap)
    if width <= 0 or width > clamp_float(pitch * config.max_width_ratio, config.max_width_min, config.max_width_max):
        return False
    if abs(gap.center - expected) > clamp_float(pitch * config.max_shift_ratio, config.max_shift_min, config.max_shift_max):
        return False
    return True


def promote_enhanced_gap(gap: Gap, index: int) -> Gap:
    return Gap(index, gap.center, gap.score, GAP_ENHANCED_DETECTED, gap.start, gap.end)


def find_enhanced_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    gap_search: GapSearchParameters | None = None,
    enhanced_config: EnhancedSeparatorParameters | None = None,
) -> Gap:
    config = enhanced_config or EnhancedSeparatorParameters()
    result = find_detected_gap(profile, expected, pitch, index, gap_search=gap_search)
    gap = result.detected_gap
    if gap is None:
        return enhanced_gap_fallback(index, expected, result.fallback_score)
    if not enhanced_gap_is_valid(gap, expected, pitch, config):
        return enhanced_gap_fallback(index, expected, gap.score)
    return promote_enhanced_gap(gap, index)


def enhanced_gap_promotion_cache_key(
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    policy_key: tuple[Any, ...] = (),
) -> tuple[Any, ...]:
    return (
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


def enhanced_gap_promotion_policy_key(
    robust_grid: RobustGridParameters | None,
    gap_search: GapSearchParameters | None,
    profile_config: SeparatorProfileParameters | None,
    enhanced_config: EnhancedSeparatorParameters | None,
) -> tuple[Any, ...]:
    return (
        robust_grid or RobustGridParameters(),
        gap_search or GapSearchParameters(),
        profile_config or SeparatorProfileParameters(),
        enhanced_config or EnhancedSeparatorParameters(),
    )


def promote_one_enhanced_gap(
    profile: np.ndarray,
    gap: Gap,
    origin: float,
    pitch: float,
    gap_search: GapSearchParameters | None,
    enhanced_config: EnhancedSeparatorParameters | None,
) -> tuple[Gap, dict[str, Any] | None, dict[str, Any] | None]:
    if gap.method in HARD_GAP_METHODS:
        return gap, None, None
    expected = origin + pitch * gap.index
    enhanced = find_enhanced_gap(profile, expected, pitch, gap.index, gap_search, enhanced_config)
    if enhanced.method == GAP_ENHANCED_DETECTED:
        return enhanced, {
            "index": int(gap.index),
            "center": float(enhanced.center),
            "score": float(enhanced.score),
            "replaced_method": gap.method,
        }, None
    return gap, None, {
        "index": int(gap.index),
        "score": float(enhanced.score),
        "method": enhanced.method,
        "kept_method": gap.method,
    }


def promote_enhanced_separator_gaps(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    robust_grid: RobustGridParameters | None = None,
    gap_search: GapSearchParameters | None = None,
    profile_config: SeparatorProfileParameters | None = None,
    enhanced_config: EnhancedSeparatorParameters | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0 or outer.height <= 0:
        return gaps, {"used": False, "reason": "empty_outer"}
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        policy_key = enhanced_gap_promotion_policy_key(robust_grid, gap_search, profile_config, enhanced_config)
        cache_key = enhanced_gap_promotion_cache_key(outer, gaps, origin, pitch, strip_mode, policy_key)
        cached = cache.enhanced_gap_promotions.get(cache_key)
        if cached is not None:
            cached_gaps, cached_detail = cached
            return list(cached_gaps), copy.deepcopy(cached_detail)
    profile = cached_enhanced_separator_profile(cache, gray_work, outer, profile_config)
    merged: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for gap in gaps:
        merged_gap, accepted_detail, rejected_detail = promote_one_enhanced_gap(
            profile,
            gap,
            origin,
            pitch,
            gap_search,
            enhanced_config,
        )
        merged.append(merged_gap)
        if accepted_detail is not None:
            accepted.append(accepted_detail)
        if rejected_detail is not None:
            rejected.append(rejected_detail)
    constrained = [
        constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode, robust_grid)
        if gap.method == GAP_ENHANCED_DETECTED else gap
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
        cache.enhanced_gap_promotions[cache_key] = (list(constrained), copy.deepcopy(detail))
    return constrained, detail


def should_run_enhanced_gap_promotion(
    analysis: str,
    gaps: list[Gap],
    count: int,
    enhanced_config: EnhancedSeparatorParameters | None = None,
) -> bool:
    config = enhanced_config or EnhancedSeparatorParameters()
    if analysis == "off":
        return False
    if analysis == "always":
        return True
    expected = max(0, count - 1)
    if expected <= 0:
        return False
    hard = [gap for gap in gaps if gap.method in HARD_GAP_METHODS]
    model_only = [gap for gap in gaps if gap.method in {GAP_EQUAL, GAP_GRID}]
    low_score_hard = any(gap.score < config.auto_low_score for gap in hard)
    return len(hard) < expected or bool(model_only) or low_score_hard
