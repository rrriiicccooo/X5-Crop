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
    found = key in cache.separator_profiles
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        pixels = cache.gray_work[
            measured_corridor.top:measured_corridor.bottom,
            measured_corridor.left:measured_corridor.right,
        ]
        cache.separator_profiles[key] = separator_profile(
            pixels,
            cache.image_statistics,
            profile_parameters,
        )
    return cache.separator_profiles[key]
