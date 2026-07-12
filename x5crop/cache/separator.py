from __future__ import annotations

import numpy as np

from . import MeasurementCache, MeasurementRegionKey
from ..domain import Box
from ..image.separator_profile import SeparatorProfileParameters, separator_profile


def separator_profile_cache_key(
    corridor: Box,
    profile_parameters: SeparatorProfileParameters,
) -> MeasurementRegionKey:
    return MeasurementRegionKey(profile_parameters, corridor)


def cached_separator_profile(
    cache: MeasurementCache,
    corridor: Box,
    profile_parameters: SeparatorProfileParameters,
) -> np.ndarray:
    width = int(cache.gray_work.shape[1])
    height = int(cache.gray_work.shape[0])
    measured_corridor = corridor.clamp(width, height)
    if not measured_corridor.valid():
        raise ValueError("separator corridor does not intersect the workspace")
    key = separator_profile_cache_key(measured_corridor, profile_parameters)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        pixels = cache.gray_work[
            measured_corridor.top:measured_corridor.bottom,
            measured_corridor.left:measured_corridor.right,
        ]
        profile = separator_profile(
            pixels,
            cache.image_statistics,
            profile_parameters,
        )
        cache.separator_profiles[key] = profile
    return profile
