from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ....domain import Box, SeparatorBandObservation
from ....formats import FormatPhysicalSpec
from ....cache.separator import cached_separator_profile
from ....policies.runtime.separator import SeparatorPolicy
from ....units import ScanCalibration
from ....cache import MeasurementCache
from ...physical.separator.hints import SeparatorGapHintSet
from .separator_refinements import (
    apply_nearby_separator_refinements as refine_nearby_separators,
    apply_primary_separator_refinements,
)
from .separator_sources import (
    initial_separator_gaps,
)


@dataclass(frozen=True)
class SeparatorGapBuildResult:
    outer: Box
    profile: np.ndarray
    origin: float
    pitch: float
    gaps: list[SeparatorBandObservation]


def separator_origin_pitch(
    outer: Box,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
) -> tuple[float, float]:
    if strip_mode == "partial" and count < fmt.default_count:
        pitch = outer.width / float(max(1, fmt.default_count))
        total_width = pitch * count
        origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
        return float(origin), float(pitch)
    return 0.0, float(outer.width / float(max(1, count)))


def build_primary_separator_gaps_for_outer(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    cache: MeasurementCache,
    gap_max_width_ratio_override: float | None,
    separator_policy: SeparatorPolicy,
    calibration: ScanCalibration,
    long_axis: str,
    *,
    explicit_count: bool,
    gap_hints: SeparatorGapHintSet | None = None,
) -> SeparatorGapBuildResult:
    work_height, work_width = gray_work.shape
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0:
        outer = Box(0, 0, work_width, work_height)
        crop = gray_work
    profile = cached_separator_profile(cache, outer, separator_policy.profile)
    origin, pitch = separator_origin_pitch(outer, fmt, count, strip_mode, offset_fraction)
    initial_gaps = initial_separator_gaps(
        outer,
        profile,
        fmt,
        count,
        strip_mode,
        origin,
        pitch,
        gap_max_width_ratio_override,
        separator_policy,
        cache,
        calibration,
        long_axis,
        gap_hints=gap_hints,
    )
    refined_gaps = apply_primary_separator_refinements(
        outer,
        list(initial_gaps),
        count,
        strip_mode,
        explicit_count,
        cache,
        separator_policy,
    )
    return SeparatorGapBuildResult(
        outer=outer,
        profile=profile,
        origin=origin,
        pitch=pitch,
        gaps=refined_gaps,
    )


def apply_nearby_separator_lifecycle(
    count: int,
    strip_mode: str,
    separator_gaps: SeparatorGapBuildResult,
    separator_policy: SeparatorPolicy,
    *,
    explicit_count: bool,
) -> SeparatorGapBuildResult:
    refined_gaps = refine_nearby_separators(
        separator_gaps.gaps,
        separator_gaps.profile,
        separator_gaps.pitch,
        count,
        strip_mode,
        explicit_count,
        separator_policy,
    )
    return SeparatorGapBuildResult(
        outer=separator_gaps.outer,
        profile=separator_gaps.profile,
        origin=separator_gaps.origin,
        pitch=separator_gaps.pitch,
        gaps=refined_gaps,
    )
