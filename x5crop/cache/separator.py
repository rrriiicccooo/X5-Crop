from __future__ import annotations

import copy
from typing import Any, Optional

import numpy as np

from . import AnalysisCache
from ..domain import Box, Gap
from ..geometry.boxes import box_cache_key, crop_work_outer, full_work_box, is_full_work_box
from ..geometry.detection_parameters import (
    EdgeRefineProfileParameters,
    EnhancedSeparatorParameters,
    GapGeometryConstraintParameters,
    GapSearchParameters,
    RobustGridExecutionParameters,
    SeparatorProfileParameters,
)
from ..geometry.edge_refine_profile import edge_refine_profiles
from ..geometry.enhanced_separator import (
    EnhancedGapPromotionBatchResult,
    promote_enhanced_separator_gaps,
)
from ..geometry.separator_profile import separator_profile
from ..image.evidence import make_separator_evidence_gray


def cached_full_separator_evidence(cache: Optional[AnalysisCache], gray_work: np.ndarray) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(gray_work)
    if cache.separator_evidence_work_full is None:
        cache.separator_evidence_work_full = make_separator_evidence_gray(cache.gray_work)
        cache.separator_evidence_crops[box_cache_key(full_work_box(cache.gray_work))] = cache.separator_evidence_work_full
    return cache.separator_evidence_work_full


def separator_profile_cache_key(
    outer: Box,
    profile_config: SeparatorProfileParameters | None = None,
) -> tuple[Any, ...]:
    return (profile_config or SeparatorProfileParameters(), *box_cache_key(outer))


def separator_profile_full_cache_key(
    profile_config: SeparatorProfileParameters | None = None,
) -> tuple[Any, ...]:
    return (profile_config or SeparatorProfileParameters(),)


def edge_refine_profile_cache_key(
    outer: Box,
    edge_refine_config: EdgeRefineProfileParameters | None = None,
) -> tuple[Any, ...]:
    return (edge_refine_config or EdgeRefineProfileParameters(), *box_cache_key(outer))


def cached_separator_profile(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    profile_config: SeparatorProfileParameters | None = None,
) -> np.ndarray:
    if cache is None:
        return separator_profile(crop_work_outer(gray_work, outer), profile_config)
    if is_full_work_box(cache.gray_work, outer):
        full_key = separator_profile_full_cache_key(profile_config)
        profile = cache.separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(cache.gray_work, profile_config)
            cache.separator_profiles_full[full_key] = profile
            cache.separator_profiles[separator_profile_cache_key(full_work_box(cache.gray_work), profile_config)] = profile
        return profile
    key = separator_profile_cache_key(outer, profile_config)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        profile = separator_profile(crop_work_outer(cache.gray_work, outer), profile_config)
        cache.separator_profiles[key] = profile
    return profile


def cached_enhanced_separator_profile(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    profile_config: SeparatorProfileParameters | None = None,
) -> np.ndarray:
    if cache is None:
        crop = crop_work_outer(gray_work, outer)
        return separator_profile(make_separator_evidence_gray(crop), profile_config)
    if is_full_work_box(cache.gray_work, outer):
        full_key = separator_profile_full_cache_key(profile_config)
        profile = cache.enhanced_separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(cached_full_separator_evidence(cache, cache.gray_work), profile_config)
            cache.enhanced_separator_profiles_full[full_key] = profile
            cache.enhanced_separator_profiles[
                separator_profile_cache_key(full_work_box(cache.gray_work), profile_config)
            ] = profile
        return profile
    key = separator_profile_cache_key(outer, profile_config)
    profile = cache.enhanced_separator_profiles.get(key)
    if profile is None:
        crop = crop_work_outer(cache.gray_work, outer)
        profile = separator_profile(make_separator_evidence_gray(crop), profile_config)
        cache.enhanced_separator_profiles[key] = profile
    return profile


def cached_separator_evidence_crop(cache: Optional[AnalysisCache], gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(crop_work_outer(gray_work, outer))
    if is_full_work_box(cache.gray_work, outer):
        return cached_full_separator_evidence(cache, cache.gray_work)
    key = box_cache_key(outer)
    evidence = cache.separator_evidence_crops.get(key)
    if evidence is None:
        evidence = make_separator_evidence_gray(crop_work_outer(cache.gray_work, outer))
        cache.separator_evidence_crops[key] = evidence
    return evidence


def cached_edge_refine_profiles(
    cache: Optional[AnalysisCache],
    crop: np.ndarray,
    outer: Box,
    edge_refine_config: EdgeRefineProfileParameters | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if cache is None:
        return edge_refine_profiles(crop, edge_refine_config)
    key = edge_refine_profile_cache_key(outer, edge_refine_config)
    profiles = cache.edge_refine_profiles.get(key)
    if profiles is None:
        profiles = edge_refine_profiles(crop_work_outer(cache.gray_work, outer), edge_refine_config)
        cache.edge_refine_profiles[key] = profiles
    return profiles


def enhanced_gap_promotion_cache_key(
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    mode_key: str,
    policy_key: tuple[Any, ...] = (),
) -> tuple[Any, ...]:
    return (
        str(mode_key),
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
    robust_grid: RobustGridExecutionParameters | None,
    gap_search: GapSearchParameters | None,
    profile_config: SeparatorProfileParameters | None,
    enhanced_config: EnhancedSeparatorParameters | None,
) -> tuple[Any, ...]:
    return (
        robust_grid or RobustGridExecutionParameters(),
        gap_search or GapSearchParameters(),
        profile_config or SeparatorProfileParameters(),
        enhanced_config or EnhancedSeparatorParameters(),
    )


def cached_promote_enhanced_separator_gaps(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    mode_key: str,
    cache: Optional[AnalysisCache],
    gap_geometry: GapGeometryConstraintParameters,
    robust_grid: RobustGridExecutionParameters | None = None,
    gap_search: GapSearchParameters | None = None,
    profile_config: SeparatorProfileParameters | None = None,
    enhanced_config: EnhancedSeparatorParameters | None = None,
) -> EnhancedGapPromotionBatchResult:
    if not outer.valid() or outer.width <= 0 or outer.height <= 0:
        return EnhancedGapPromotionBatchResult(gaps, {"used": False, "reason": "empty_outer"})
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        policy_key = enhanced_gap_promotion_policy_key(robust_grid, gap_search, profile_config, enhanced_config)
        cache_key = enhanced_gap_promotion_cache_key(outer, gaps, origin, pitch, mode_key, policy_key)
        cached = cache.enhanced_gap_promotions.get(cache_key)
        if cached is not None:
            cached_gaps, cached_detail = cached
            return EnhancedGapPromotionBatchResult(list(cached_gaps), copy.deepcopy(cached_detail))

    profile = cached_enhanced_separator_profile(cache, gray_work, outer, profile_config)
    result = promote_enhanced_separator_gaps(
        profile,
        gaps,
        origin,
        pitch,
        gap_geometry,
        robust_grid,
        gap_search,
        enhanced_config,
    )
    if cache_key is not None and cache is not None:
        cache.enhanced_gap_promotions[cache_key] = (list(result.gaps), copy.deepcopy(result.detail))
    return result


__all__ = [
    "cached_edge_refine_profiles",
    "cached_enhanced_separator_profile",
    "cached_full_separator_evidence",
    "cached_promote_enhanced_separator_gaps",
    "cached_separator_evidence_crop",
    "cached_separator_profile",
    "edge_refine_profile_cache_key",
    "enhanced_gap_promotion_cache_key",
    "enhanced_gap_promotion_policy_key",
    "separator_profile_cache_key",
    "separator_profile_full_cache_key",
]
