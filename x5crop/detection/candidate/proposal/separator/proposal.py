from __future__ import annotations

from typing import Optional

import numpy as np

from .....domain import Box, Gap
from .....geometry.detection_parameters import (
    GapSearchParameters,
    SeparatorWidthProfileSearchParameters,
)
from .....geometry.gap_search import find_detected_gap
from .....geometry.separator_width_profile import (
    separator_width_gap_at,
    separator_width_profile as make_separator_width_profile,
)
from .....policies.runtime.separator import SeparatorWidthProfilePolicy
from .model import propose_equal_model_gap


def propose_standard_separator_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> Gap:
    result = find_detected_gap(
        profile,
        expected,
        pitch,
        index,
        max_width_ratio_override,
        gap_search,
    )
    if result.detected_gap is not None:
        return result.detected_gap
    return propose_equal_model_gap(index, expected, result.fallback_score)


def propose_standard_separator_gaps(
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> list[Gap]:
    return [
        propose_standard_separator_gap(
            profile,
            origin + pitch * index,
            pitch,
            index,
            max_width_ratio_override,
            gap_search,
        )
        for index in range(1, count)
    ]


def propose_separator_width_profile_gaps(
    gray_work: np.ndarray,
    outer: Box,
    count: int,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> list[Gap]:
    required_count = int(width_profile_policy.required_count)
    if (
        width_profile_policy.mode == "off"
        or count <= 1
        or (required_count > 0 and count != required_count)
        or not outer.valid()
    ):
        return []
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0:
        return []
    width_profile = make_separator_width_profile(crop, width_profile_search)
    pitch = outer.width / float(max(1, count))
    gaps: list[Gap] = []
    for index in range(1, count):
        expected = pitch * index
        gap = separator_width_gap_at(
            width_profile,
            expected,
            pitch,
            index,
            float(outer.height),
            width_profile_search,
        )
        if gap is not None:
            gaps.append(gap)
    return gaps


__all__ = [
    "propose_standard_separator_gap",
    "propose_separator_width_profile_gaps",
    "propose_standard_separator_gaps",
]
