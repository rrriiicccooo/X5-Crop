from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from .....constants import GAP_DETECTED
from .....domain import Box, Gap
from .....geometry.detection_parameters import (
    GapSearchParameters,
    SeparatorWidthProfileSearchParameters,
)
from .....geometry.gap_search import find_detected_gap
from .....geometry.separator_width_profile import (
    separator_width_gap_at_with_detail,
    separator_width_profile as make_separator_width_profile,
)
from .....policies.runtime.separator import SeparatorWidthProfilePolicy
from ....gap_profiles import (
    BROAD_WIDTH_GAP_PROFILE,
    STANDARD_GAP_PROFILE,
)
from .model import propose_equal_model_gap


@dataclass(frozen=True)
class SeparatorGapProfileProposal:
    profile: str
    gaps: list[Gap]
    detail: dict[str, Any]


def _propose_standard_separator_gap_with_detail(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> tuple[Gap, dict[str, Any]]:
    result = find_detected_gap(
        profile,
        expected,
        pitch,
        index,
        max_width_ratio_override,
        gap_search,
    )
    detail: dict[str, Any] = {
        "index": int(index),
        "reason": result.reason,
        "fallback_score": float(result.fallback_score),
        "search": result.detail,
    }
    if result.detected_gap is not None:
        gap = result.detected_gap
        detail["selected_method"] = gap.method
        detail["selected_center"] = float(gap.center)
        detail["selected_score"] = float(gap.score)
        return gap, detail
    gap = propose_equal_model_gap(index, expected, result.fallback_score)
    detail["selected_method"] = gap.method
    detail["selected_center"] = float(gap.center)
    detail["selected_score"] = float(gap.score)
    return gap, detail


def _propose_standard_separator_gaps_with_detail(
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> SeparatorGapProfileProposal:
    gaps: list[Gap] = []
    entries: list[dict[str, Any]] = []
    for index in range(1, count):
        gap, detail = _propose_standard_separator_gap_with_detail(
            profile,
            origin + pitch * index,
            pitch,
            index,
            max_width_ratio_override,
            gap_search,
        )
        gaps.append(gap)
        entries.append(detail)
    return SeparatorGapProfileProposal(
        profile=STANDARD_GAP_PROFILE,
        gaps=gaps,
        detail={
            "used": True,
            "profile": STANDARD_GAP_PROFILE,
            "origin": float(origin),
            "pitch": float(pitch),
            "count": int(count),
            "max_width_ratio_override": max_width_ratio_override,
            "detected_count": sum(1 for gap in gaps if gap.method == GAP_DETECTED),
            "fallback_count": sum(1 for gap in gaps if gap.method != GAP_DETECTED),
            "entries": entries,
        },
    )


def _propose_separator_width_profile_gaps_with_detail(
    gray_work: np.ndarray,
    outer: Box,
    count: int,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> SeparatorGapProfileProposal:
    required_count = int(width_profile_policy.required_count)
    if (
        width_profile_policy.mode == "off"
        or count <= 1
        or (required_count > 0 and count != required_count)
        or not outer.valid()
    ):
        return SeparatorGapProfileProposal(
            profile=BROAD_WIDTH_GAP_PROFILE,
            gaps=[],
            detail={
                "used": False,
                "profile": BROAD_WIDTH_GAP_PROFILE,
                "reason": "not_eligible",
                "mode": width_profile_policy.mode,
                "count": int(count),
                "required_count": int(required_count),
                "outer_valid": bool(outer.valid()),
            },
        )
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0:
        return SeparatorGapProfileProposal(
            profile=BROAD_WIDTH_GAP_PROFILE,
            gaps=[],
            detail={
                "used": False,
                "profile": BROAD_WIDTH_GAP_PROFILE,
                "reason": "empty_outer_crop",
                "mode": width_profile_policy.mode,
                "count": int(count),
                "required_count": int(required_count),
            },
        )
    width_profile = make_separator_width_profile(crop, width_profile_search)
    pitch = outer.width / float(max(1, count))
    gaps: list[Gap] = []
    entries: list[dict[str, Any]] = []
    for index in range(1, count):
        expected = pitch * index
        result = separator_width_gap_at_with_detail(
            width_profile,
            expected,
            pitch,
            index,
            float(outer.height),
            width_profile_search,
        )
        entry: dict[str, Any] = {
            "index": int(index),
            "reason": result.reason,
            "search": result.detail,
        }
        gap = result.gap
        if gap is not None:
            gaps.append(gap)
            entry["selected_method"] = gap.method
            entry["selected_center"] = float(gap.center)
            entry["selected_score"] = float(gap.score)
            entry["selected_width"] = float(gap.width)
        entries.append(entry)
    expected_count = max(0, int(count) - 1)
    detected_count = int(len(gaps))
    return SeparatorGapProfileProposal(
        profile=BROAD_WIDTH_GAP_PROFILE,
        gaps=gaps,
        detail={
            "used": True,
            "profile": BROAD_WIDTH_GAP_PROFILE,
            "reason": "complete" if detected_count >= expected_count else "too_few_width_profile_gaps",
            "mode": width_profile_policy.mode,
            "count": int(count),
            "required_count": int(required_count),
            "pitch": float(pitch),
            "outer": {
                "left": int(outer.left),
                "top": int(outer.top),
                "right": int(outer.right),
                "bottom": int(outer.bottom),
            },
            "detected_count": detected_count,
            "expected_count": expected_count,
            "profile_length": int(len(width_profile)),
            "entries": entries,
        },
    )


def propose_separator_gap_profile_gaps_with_detail(
    gray_work: np.ndarray,
    outer: Box,
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    gap_search_profile: str,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> SeparatorGapProfileProposal:
    if gap_search_profile == STANDARD_GAP_PROFILE:
        return _propose_standard_separator_gaps_with_detail(
            profile,
            origin,
            pitch,
            count,
            max_width_ratio_override,
            gap_search,
        )
    if gap_search_profile == BROAD_WIDTH_GAP_PROFILE:
        return _propose_separator_width_profile_gaps_with_detail(
            gray_work,
            outer,
            count,
            width_profile_policy,
            width_profile_search,
        )
    raise ValueError(f"Unsupported separator gap search profile: {gap_search_profile!r}")


__all__ = [
    "SeparatorGapProfileProposal",
    "propose_separator_gap_profile_gaps_with_detail",
]
