from __future__ import annotations

import numpy as np

from . import MeasurementCache, MeasurementParametersKey, MeasurementRegionKey
from ..domain import Box
from ..geometry.boxes import crop_work_box, full_work_box, is_full_work_box
from ..geometry.detection_parameters import (
    SeparatorProfileParameters,
)
from ..geometry.separator_profile import separator_profile


def separator_profile_cache_key(
    corridor: Box,
    profile_parameters: SeparatorProfileParameters,
) -> MeasurementRegionKey:
    return MeasurementRegionKey(profile_parameters, corridor)


def separator_profile_full_cache_key(
    profile_parameters: SeparatorProfileParameters,
) -> MeasurementParametersKey:
    return MeasurementParametersKey(profile_parameters)


def cached_separator_profile(
    cache: MeasurementCache,
    corridor: Box,
    profile_parameters: SeparatorProfileParameters,
) -> np.ndarray:
    if is_full_work_box(cache.gray_work, corridor):
        full_key = separator_profile_full_cache_key(profile_parameters)
        profile = cache.separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(
                cache.gray_work,
                cache.image_statistics,
                profile_parameters,
            )
            cache.separator_profiles_full[full_key] = profile
            cache.separator_profiles[
                separator_profile_cache_key(
                    full_work_box(cache.gray_work),
                    profile_parameters,
                )
            ] = profile
        return profile
    key = separator_profile_cache_key(corridor, profile_parameters)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        profile = separator_profile(
            crop_work_box(cache.gray_work, corridor),
            cache.image_statistics,
            profile_parameters,
        )
        cache.separator_profiles[key] = profile
    return profile
