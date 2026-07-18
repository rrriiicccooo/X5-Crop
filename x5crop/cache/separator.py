from __future__ import annotations

from . import MeasurementCache, MeasurementRegionKey
from ..domain import Box
from ..image.separator_profile import (
    SeparatorProfileMeasurement,
    SeparatorProfileParameters,
    measure_separator_profile,
)


def cached_separator_profile_measurement(
    cache: MeasurementCache,
    corridor: Box,
    profile_parameters: SeparatorProfileParameters,
) -> SeparatorProfileMeasurement:
    width = int(cache.gray_work.shape[1])
    height = int(cache.gray_work.shape[0])
    measured_corridor = corridor.clamp(width, height)
    if not measured_corridor.valid():
        raise ValueError("separator corridor does not intersect the workspace")
    key = MeasurementRegionKey(profile_parameters, measured_corridor)
    found = key in cache.separator_profile_measurements
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        pixels = cache.gray_work[
            measured_corridor.top:measured_corridor.bottom,
            measured_corridor.left:measured_corridor.right,
        ]
        cache.separator_profile_measurements[key] = measure_separator_profile(
            pixels,
            cache.image_statistics,
            profile_parameters,
        )
    return cache.separator_profile_measurements[key]
