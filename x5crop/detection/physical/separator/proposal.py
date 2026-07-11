from __future__ import annotations

from dataclasses import replace

import numpy as np

from ....domain import Box, SeparatorBandObservation
from ....geometry.detection_parameters import (
    GapSearchParameters,
    SeparatorWidthProfileSearchParameters,
)
from ....geometry.gap_search import find_detected_gap
from ....geometry.model_gaps import equal_model_gap
from ....geometry.separator_width_profile import (
    SeparatorWidthGapSearchResult,
    separator_width_gap_at,
)
from ....policies.runtime.separator import SeparatorWidthProfilePolicy
from ....units import ScanCalibration
from ....utils import clamp_int
from ....gap_methods import is_hard_gap_method
from .hints import SeparatorGapHintSet

def _same_observed_band(
    left: SeparatorBandObservation,
    right: SeparatorBandObservation,
    pitch: float,
    center_tolerance_ratio: float,
) -> bool:
    if (
        left.start is not None
        and left.end is not None
        and right.start is not None
        and right.end is not None
        and max(float(left.start), float(right.start))
        < min(float(left.end), float(right.end))
    ):
        return True
    tolerance = max(1.0, float(pitch) * float(center_tolerance_ratio))
    return abs(float(left.center) - float(right.center)) <= tolerance


def _deduplicated_observations(
    gaps: list[SeparatorBandObservation],
    model_fallbacks: dict[int, SeparatorBandObservation],
    origin: float,
    pitch: float,
    center_tolerance_ratio: float,
) -> tuple[SeparatorBandObservation, ...]:
    measured = [gap for gap in gaps if is_hard_gap_method(gap.method)]
    ordered = sorted(
        measured,
        key=lambda gap: (
            abs(float(gap.center) - (float(origin) + float(pitch) * gap.index)),
            -float(gap.score),
            int(gap.index),
        ),
    )
    kept: list[SeparatorBandObservation] = []
    kept_indexes: set[int] = set()
    for gap in ordered:
        if any(
            _same_observed_band(
                gap,
                existing,
                pitch,
                center_tolerance_ratio,
            )
            for existing in kept
        ):
            continue
        kept.append(gap)
        kept_indexes.add(int(gap.index))
    return tuple(
        gap
        if not is_hard_gap_method(gap.method) or gap.index in kept_indexes
        else model_fallbacks[gap.index]
        for gap in gaps
    )


def _guided_center(
    hints: SeparatorGapHintSet | None,
    index: int,
    expected: float,
    pitch: float,
    outer_left: float,
) -> tuple[float, str | None]:
    if hints is None:
        return expected, None
    hint = hints.hint_for_index(index)
    if hint is None:
        return expected, None
    maximum_offset = clamp_int(
        pitch * hints.max_offset_ratio,
        hints.max_offset_min,
        hints.max_offset_max,
    )
    hint_center = float(hint.work_center) - float(outer_left)
    if abs(hint_center - expected) > maximum_offset:
        return expected, None
    return hint_center, hints.provenance.root_measurement


def _with_guidance_dependency(
    observation: SeparatorBandObservation,
    guidance_root: str | None,
) -> SeparatorBandObservation:
    if guidance_root is None:
        return observation
    provenance = observation.provenance
    return replace(
        observation,
        provenance=replace(
            provenance,
            dependencies=tuple(
                dict.fromkeys((*provenance.dependencies, guidance_root))
            ),
        ),
    )


def _observed_width_result(
    width_profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    short_axis: float,
    search: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapSearchResult | None:
    if not width_profile.size:
        return None
    return separator_width_gap_at(
        width_profile,
        expected,
        pitch,
        index,
        short_axis,
        search,
    )


def propose_separator_gaps(
    outer: Box,
    profile: np.ndarray,
    width_profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    max_width_ratio_override: float | None,
    gap_search: GapSearchParameters,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
    calibration: ScanCalibration,
    long_axis: str,
    gap_hints: SeparatorGapHintSet | None = None,
) -> tuple[SeparatorBandObservation, ...]:
    gaps: list[SeparatorBandObservation] = []
    model_fallbacks: dict[int, SeparatorBandObservation] = {}
    for index in range(1, count):
        model_center = origin + pitch * index
        search_center, guidance_root = _guided_center(
            gap_hints,
            index,
            model_center,
            pitch,
            float(outer.left),
        )
        standard = find_detected_gap(
            profile,
            search_center,
            pitch,
            index,
            gap_search,
            calibration,
            long_axis,
            max_width_ratio_override=max_width_ratio_override,
        )
        observed = (
            _observed_width_result(
                width_profile,
                search_center,
                pitch,
                index,
                float(outer.height),
                width_profile_search,
            )
            if width_profile_policy.mode != "off"
            else None
        )
        model_fallbacks[index] = equal_model_gap(
            index,
            model_center,
            standard.model_gap_score,
        )
        if standard.detected_gap is not None:
            gaps.append(
                _with_guidance_dependency(
                    standard.detected_gap,
                    guidance_root,
                )
            )
        elif observed is not None and observed.gap is not None:
            gaps.append(
                _with_guidance_dependency(observed.gap, guidance_root)
            )
        else:
            gaps.append(model_fallbacks[index])
    return _deduplicated_observations(
        gaps,
        model_fallbacks,
        origin,
        pitch,
        gap_search.observation_dedup_center_tolerance_ratio,
    )
