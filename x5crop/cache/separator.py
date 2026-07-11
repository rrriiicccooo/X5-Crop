from __future__ import annotations

from typing import Any

import numpy as np

from . import MeasurementCache
from ..domain import Box
from ..geometry.boxes import box_cache_key, crop_work_outer, full_work_box, is_full_work_box
from ..geometry.detection_parameters import (
    EdgeRefineProfileParameters,
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
)
from ..geometry.edge_refine_profile import edge_refine_profiles
from ..geometry.separator_profile import separator_profile
from ..geometry.separator_width_profile import separator_width_profile
from ..image.evidence import (
    SeparatorEvidenceImageParameters,
    make_separator_evidence_gray,
)


def cached_full_separator_evidence(
    cache: MeasurementCache,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    key = (params, *box_cache_key(full_work_box(cache.gray_work)))
    evidence = cache.separator_evidence_crops.get(key)
    if evidence is None:
        evidence = make_separator_evidence_gray(
            cache.gray_work,
            params,
        )
        cache.separator_evidence_crops[key] = evidence
    return evidence


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
    cache: MeasurementCache,
    outer: Box,
    profile_config: SeparatorProfileParameters,
) -> np.ndarray:
    if is_full_work_box(cache.gray_work, outer):
        full_key = separator_profile_full_cache_key(profile_config)
        profile = cache.separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(cache.gray_work, profile_config)
            cache.separator_profiles_full[full_key] = profile
            cache.separator_profiles[
                separator_profile_cache_key(
                    full_work_box(cache.gray_work),
                    profile_config,
                )
            ] = profile
        return profile
    key = separator_profile_cache_key(outer, profile_config)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        profile = separator_profile(crop_work_outer(cache.gray_work, outer), profile_config)
        cache.separator_profiles[key] = profile
    return profile


def cached_separator_width_profile(
    cache: MeasurementCache,
    outer: Box,
    params: SeparatorWidthProfileSearchParameters,
) -> np.ndarray:
    key = (params, *box_cache_key(outer))
    profile = cache.separator_width_profiles.get(key)
    if profile is None:
        profile = separator_width_profile(crop_work_outer(cache.gray_work, outer), params)
        cache.separator_width_profiles[key] = profile
    return profile


def cached_separator_evidence_crop(
    cache: MeasurementCache,
    outer: Box,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    if is_full_work_box(cache.gray_work, outer):
        return cached_full_separator_evidence(cache, params)
    key = (params, *box_cache_key(outer))
    evidence = cache.separator_evidence_crops.get(key)
    if evidence is None:
        evidence = make_separator_evidence_gray(crop_work_outer(cache.gray_work, outer), params)
        cache.separator_evidence_crops[key] = evidence
    return evidence


def cached_edge_refine_profiles(
    cache: MeasurementCache,
    outer: Box,
    edge_refine_config: EdgeRefineProfileParameters,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key = edge_refine_profile_cache_key(outer, edge_refine_config)
    profiles = cache.edge_refine_profiles.get(key)
    if profiles is None:
        profiles = edge_refine_profiles(crop_work_outer(cache.gray_work, outer), edge_refine_config)
        cache.edge_refine_profiles[key] = profiles
    return profiles
