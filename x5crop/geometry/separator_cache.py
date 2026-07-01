from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..domain import Box
from ..image.evidence import make_separator_evidence_gray
from ..policies.runtime_policy import EdgeRefineProfilePolicy, SeparatorProfilePolicy
from ..runtime import AnalysisCache
from .boxes import box_cache_key, crop_work_outer, full_work_box, is_full_work_box
from .separator_profile import edge_refine_profiles, separator_profile


def cached_full_separator_evidence(cache: Optional[AnalysisCache], gray_work: np.ndarray) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(gray_work)
    if cache.separator_evidence_work_full is None:
        cache.separator_evidence_work_full = make_separator_evidence_gray(cache.gray_work)
        cache.separator_evidence_crops[box_cache_key(full_work_box(cache.gray_work))] = cache.separator_evidence_work_full
    return cache.separator_evidence_work_full


def separator_profile_cache_key(
    format_name: str,
    outer: Box,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> tuple[Any, ...]:
    return (str(format_name), profile_policy or SeparatorProfilePolicy(), *box_cache_key(outer))


def separator_profile_full_cache_key(
    format_name: str,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> tuple[Any, ...]:
    return (str(format_name), profile_policy or SeparatorProfilePolicy())


def edge_refine_profile_cache_key(
    format_name: str,
    outer: Box,
    edge_refine_policy: EdgeRefineProfilePolicy | None = None,
) -> tuple[Any, ...]:
    return (str(format_name), edge_refine_policy or EdgeRefineProfilePolicy(), *box_cache_key(outer))


def cached_separator_profile(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    format_name: str,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> np.ndarray:
    if cache is None:
        return separator_profile(crop_work_outer(gray_work, outer), profile_policy)
    if is_full_work_box(cache.gray_work, outer):
        full_key = separator_profile_full_cache_key(format_name, profile_policy)
        profile = cache.separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(cache.gray_work, profile_policy)
            cache.separator_profiles_full[full_key] = profile
            cache.separator_profiles[separator_profile_cache_key(format_name, full_work_box(cache.gray_work), profile_policy)] = profile
        return profile
    key = separator_profile_cache_key(format_name, outer, profile_policy)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        profile = separator_profile(crop_work_outer(cache.gray_work, outer), profile_policy)
        cache.separator_profiles[key] = profile
    return profile


def cached_enhanced_separator_profile(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    format_name: str,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> np.ndarray:
    if cache is None:
        crop = crop_work_outer(gray_work, outer)
        return separator_profile(make_separator_evidence_gray(crop), profile_policy)
    if is_full_work_box(cache.gray_work, outer):
        full_key = separator_profile_full_cache_key(format_name, profile_policy)
        profile = cache.enhanced_separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(cached_full_separator_evidence(cache, cache.gray_work), profile_policy)
            cache.enhanced_separator_profiles_full[full_key] = profile
            cache.enhanced_separator_profiles[
                separator_profile_cache_key(format_name, full_work_box(cache.gray_work), profile_policy)
            ] = profile
        return profile
    key = separator_profile_cache_key(format_name, outer, profile_policy)
    profile = cache.enhanced_separator_profiles.get(key)
    if profile is None:
        crop = crop_work_outer(cache.gray_work, outer)
        profile = separator_profile(make_separator_evidence_gray(crop), profile_policy)
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
    format_name: str,
    edge_refine_policy: EdgeRefineProfilePolicy | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if cache is None:
        return edge_refine_profiles(crop, edge_refine_policy)
    key = edge_refine_profile_cache_key(format_name, outer, edge_refine_policy)
    profiles = cache.edge_refine_profiles.get(key)
    if profiles is None:
        profiles = edge_refine_profiles(crop_work_outer(cache.gray_work, outer), edge_refine_policy)
        cache.edge_refine_profiles[key] = profiles
    return profiles
