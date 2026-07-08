from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import AnalysisCache
from ..domain import Box
from ..geometry.boxes import box_cache_key, crop_work_outer, full_work_box, is_full_work_box
from ..geometry.detection_parameters import (
    EdgeRefineProfileParameters,
    SeparatorProfileParameters,
)
from ..geometry.edge_refine_profile import edge_refine_profiles
from ..geometry.separator_profile import separator_profile
from ..image.evidence import (
    SeparatorEvidenceImageParameters,
    make_separator_evidence_gray,
)


def cached_full_separator_evidence(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(gray_work, params)
    if cache.separator_evidence_work_full is None:
        cache.separator_evidence_work_full = make_separator_evidence_gray(cache.gray_work, params)
        cache.separator_evidence_crops[box_cache_key(full_work_box(cache.gray_work))] = cache.separator_evidence_work_full
    return cache.separator_evidence_work_full


def separator_profile_cache_key(
    outer: Box,
    profile_config: SeparatorProfileParameters,
) -> tuple[Any, ...]:
    return (profile_config, *box_cache_key(outer))


def separator_profile_full_cache_key(
    profile_config: SeparatorProfileParameters,
) -> tuple[Any, ...]:
    return (profile_config,)


def edge_refine_profile_cache_key(
    outer: Box,
    edge_refine_config: EdgeRefineProfileParameters,
) -> tuple[Any, ...]:
    return (edge_refine_config, *box_cache_key(outer))


def cached_separator_profile(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    profile_config: SeparatorProfileParameters,
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


def cached_separator_evidence_crop(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(crop_work_outer(gray_work, outer), params)
    if is_full_work_box(cache.gray_work, outer):
        return cached_full_separator_evidence(cache, cache.gray_work, params)
    key = box_cache_key(outer)
    evidence = cache.separator_evidence_crops.get(key)
    if evidence is None:
        evidence = make_separator_evidence_gray(crop_work_outer(cache.gray_work, outer), params)
        cache.separator_evidence_crops[key] = evidence
    return evidence


def cached_edge_refine_profiles(
    cache: Optional[AnalysisCache],
    crop: np.ndarray,
    outer: Box,
    edge_refine_config: EdgeRefineProfileParameters,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if cache is None:
        return edge_refine_profiles(crop, edge_refine_config)
    key = edge_refine_profile_cache_key(outer, edge_refine_config)
    profiles = cache.edge_refine_profiles.get(key)
    if profiles is None:
        profiles = edge_refine_profiles(crop_work_outer(cache.gray_work, outer), edge_refine_config)
        cache.edge_refine_profiles[key] = profiles
    return profiles


__all__ = [
    "cached_edge_refine_profiles",
    "cached_full_separator_evidence",
    "cached_separator_evidence_crop",
    "cached_separator_profile",
    "edge_refine_profile_cache_key",
    "separator_profile_cache_key",
    "separator_profile_full_cache_key",
]
