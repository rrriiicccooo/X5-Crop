from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..constants import GAP_DETECTED, GAP_ENHANCED_DETECTED
from ..domain import Box, Gap
from ..gap_methods import is_geometry_model_gap_method, is_hard_gap_method
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


@dataclass(frozen=True)
class EnhancedGapValidation:
    accepted: bool
    reason: str
    score: float
    min_score: float
    width: float
    max_width: float
    shift_px: float
    shift_limit: float

    def detail(self) -> dict[str, Any]:
        return {
            "accepted": bool(self.accepted),
            "reason": self.reason,
            "score": float(self.score),
            "min_score": float(self.min_score),
            "width": float(self.width),
            "max_width": float(self.max_width),
            "shift_px": float(self.shift_px),
            "shift_limit": float(self.shift_limit),
        }


@dataclass(frozen=True)
class EnhancedGapSearchResult:
    gap: Gap
    detail: dict[str, Any]


@dataclass(frozen=True)
class EnhancedGapPromotionResult:
    gap: Gap
    accepted_detail: Optional[dict[str, Any]] = None
    rejected_detail: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class EnhancedGapPromotionBatchResult:
    gaps: list[Gap]
    detail: dict[str, Any]


def enhanced_gap_validation(
    gap: Gap,
    expected: float,
    pitch: float,
    config: EnhancedSeparatorParameters,
) -> EnhancedGapValidation:
    width = enhanced_gap_width(gap)
    max_width = clamp_float(
        pitch * config.max_width_ratio,
        config.max_width_min,
        config.max_width_max,
    )
    shift = abs(float(gap.center) - float(expected))
    shift_limit = clamp_float(
        pitch * config.max_shift_ratio,
        config.max_shift_min,
        config.max_shift_max,
    )

    def result(accepted: bool, reason: str) -> EnhancedGapValidation:
        return EnhancedGapValidation(
            bool(accepted),
            reason,
            float(gap.score),
            float(config.min_score),
            float(width),
            float(max_width),
            float(shift),
            float(shift_limit),
        )

    if gap.method != GAP_DETECTED:
        return result(False, "not_detected_gap")
    if gap.score < config.min_score:
        return result(False, "score_below_min")
    if width <= 0:
        return result(False, "missing_gap_span")
    if width > max_width:
        return result(False, "width_too_wide")
    if shift > shift_limit:
        return result(False, "shift_too_large")
    return result(True, "accepted")


def enhanced_gap_detail(gap: Gap) -> dict[str, Any]:
    return {
        "index": int(gap.index),
        "center": float(gap.center),
        "score": float(gap.score),
        "method": gap.method,
        "start": None if gap.start is None else float(gap.start),
        "end": None if gap.end is None else float(gap.end),
        "width": float(enhanced_gap_width(gap)),
    }


def enhanced_gap_is_valid(gap: Gap, expected: float, pitch: float, config: EnhancedSeparatorParameters) -> bool:
    return enhanced_gap_validation(gap, expected, pitch, config).accepted


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
    result = find_enhanced_gap_with_detail(
        profile,
        expected,
        pitch,
        index,
        gap_search,
        enhanced_config,
    )
    return result.gap


def find_enhanced_gap_with_detail(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    gap_search: GapSearchParameters | None = None,
    enhanced_config: EnhancedSeparatorParameters | None = None,
) -> EnhancedGapSearchResult:
    config = enhanced_config or EnhancedSeparatorParameters()
    result = find_detected_gap(profile, expected, pitch, index, gap_search=gap_search)
    gap = result.detected_gap
    base_detail: dict[str, Any] = {
        "index": int(index),
        "expected": float(expected),
        "pitch": float(pitch),
        "search_reason": result.reason,
        "search": result.detail,
    }
    if gap is None:
        fallback = enhanced_gap_fallback(index, expected, result.fallback_score)
        base_detail.update(
            {
                "promoted": False,
                "detected_gap": None,
                "validation": {"accepted": False, "reason": "no_detected_gap"},
                "selected_gap": enhanced_gap_detail(fallback),
            }
        )
        return EnhancedGapSearchResult(fallback, base_detail)
    validation = enhanced_gap_validation(gap, expected, pitch, config)
    base_detail["detected_gap"] = enhanced_gap_detail(gap)
    base_detail["validation"] = validation.detail()
    if not validation.accepted:
        fallback = enhanced_gap_fallback(index, expected, gap.score)
        base_detail["promoted"] = False
        base_detail["selected_gap"] = enhanced_gap_detail(fallback)
        return EnhancedGapSearchResult(fallback, base_detail)
    enhanced = promote_enhanced_gap(gap, index)
    base_detail["promoted"] = True
    base_detail["selected_gap"] = enhanced_gap_detail(enhanced)
    return EnhancedGapSearchResult(enhanced, base_detail)


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
) -> EnhancedGapPromotionResult:
    if is_hard_gap_method(gap.method):
        return EnhancedGapPromotionResult(gap)
    expected = origin + pitch * gap.index
    search_result = find_enhanced_gap_with_detail(
        profile,
        expected,
        pitch,
        gap.index,
        gap_search,
        enhanced_config,
    )
    enhanced = search_result.gap
    detail = search_result.detail
    if enhanced.method == GAP_ENHANCED_DETECTED:
        return EnhancedGapPromotionResult(
            enhanced,
            accepted_detail={
                "index": int(gap.index),
                "center": float(enhanced.center),
                "score": float(enhanced.score),
                "replaced_method": gap.method,
                "search": detail,
                "validation": detail.get("validation", {}),
            },
        )
    return EnhancedGapPromotionResult(
        gap,
        rejected_detail={
            "index": int(gap.index),
            "score": float(enhanced.score),
            "method": enhanced.method,
            "kept_method": gap.method,
            "reason": detail.get("validation", {}).get("reason", detail.get("search_reason")),
            "search": detail,
            "validation": detail.get("validation", {}),
        },
    )


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
) -> EnhancedGapPromotionBatchResult:
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0 or outer.height <= 0:
        return EnhancedGapPromotionBatchResult(gaps, {"used": False, "reason": "empty_outer"})
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        policy_key = enhanced_gap_promotion_policy_key(robust_grid, gap_search, profile_config, enhanced_config)
        cache_key = enhanced_gap_promotion_cache_key(outer, gaps, origin, pitch, strip_mode, policy_key)
        cached = cache.enhanced_gap_promotions.get(cache_key)
        if cached is not None:
            cached_gaps, cached_detail = cached
            return EnhancedGapPromotionBatchResult(list(cached_gaps), copy.deepcopy(cached_detail))
    profile = cached_enhanced_separator_profile(cache, gray_work, outer, profile_config)
    merged: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for gap in gaps:
        promotion = promote_one_enhanced_gap(
            profile,
            gap,
            origin,
            pitch,
            gap_search,
            enhanced_config,
        )
        merged.append(promotion.gap)
        if promotion.accepted_detail is not None:
            accepted.append(promotion.accepted_detail)
        if promotion.rejected_detail is not None:
            rejected.append(promotion.rejected_detail)
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
    return EnhancedGapPromotionBatchResult(constrained, detail)


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
    hard = [gap for gap in gaps if is_hard_gap_method(gap.method)]
    geometry_model_present = any(is_geometry_model_gap_method(gap.method) for gap in gaps)
    low_score_hard = any(gap.score < config.auto_low_score for gap in hard)
    return len(hard) < expected or geometry_model_present or low_score_hard
