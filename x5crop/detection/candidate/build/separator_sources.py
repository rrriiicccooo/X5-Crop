from __future__ import annotations

import numpy as np

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_width_profile
from ....domain import Box, SeparatorBandObservation
from ....formats import FormatPhysicalSpec
from ....gap_methods import is_hard_gap_method
from ....policies.runtime.separator import SeparatorPolicy
from ....units import ScanCalibration
from ...physical.separator.hints import SeparatorGapHintSet
from ...physical.separator.model import propose_equal_model_gaps_from_profile
from ...physical.separator.proposal import propose_separator_gaps

def standard_separator_gap_result(
    outer: Box,
    profile: np.ndarray,
    count: int,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: float | None,
    separator_policy: SeparatorPolicy,
    cache: MeasurementCache,
    calibration: ScanCalibration,
    long_axis: str,
    *,
    gap_hints: SeparatorGapHintSet | None = None,
) -> tuple[SeparatorBandObservation, ...]:
    width_profile = (
        cached_separator_width_profile(
            cache,
            outer,
            separator_policy.width_profile_search,
        )
        if separator_policy.width_profile.mode != "off"
        else np.array([], dtype=np.float32)
    )
    result = propose_separator_gaps(
        outer,
        profile,
        width_profile,
        origin,
        pitch,
        count,
        gap_max_width_ratio_override,
        separator_policy.gap_search,
        separator_policy.width_profile,
        separator_policy.width_profile_search,
        calibration,
        long_axis,
        gap_hints,
    )
    return tuple(result)


def _equal_model_available(
    gaps: tuple[SeparatorBandObservation, ...],
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    gap_max_width_ratio_override: float | None,
) -> bool:
    expected = max(0, count - 1)
    hard = sum(is_hard_gap_method(gap.method) for gap in gaps)
    return bool(
        strip_mode == "full"
        and count == fmt.default_count
        and gap_max_width_ratio_override is None
        and expected > 0
        and hard < expected
    )


def select_geometry_equal_model_gaps(
    gaps: tuple[SeparatorBandObservation, ...],
    profile: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: float | None,
) -> tuple[SeparatorBandObservation, ...]:
    if not _equal_model_available(
        gaps,
        fmt,
        count,
        strip_mode,
        gap_max_width_ratio_override,
    ):
        return gaps
    model_gaps = propose_equal_model_gaps_from_profile(
        profile,
        origin,
        pitch,
        count,
    )
    measured_by_index = {gap.index: gap for gap in gaps}
    return tuple(
        measured_by_index.get(gap.index, gap) for gap in model_gaps
    )


def initial_separator_gaps(
    outer: Box,
    profile: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: float | None,
    separator_policy: SeparatorPolicy,
    cache: MeasurementCache,
    calibration: ScanCalibration,
    long_axis: str,
    *,
    gap_hints: SeparatorGapHintSet | None = None,
) -> tuple[SeparatorBandObservation, ...]:
    result = standard_separator_gap_result(
        outer,
        profile,
        count,
        origin,
        pitch,
        gap_max_width_ratio_override,
        separator_policy,
        cache,
        calibration,
        long_axis,
        gap_hints=gap_hints,
    )
    return select_geometry_equal_model_gaps(
        result,
        profile,
        fmt,
        count,
        strip_mode,
        origin,
        pitch,
        gap_max_width_ratio_override,
    )
