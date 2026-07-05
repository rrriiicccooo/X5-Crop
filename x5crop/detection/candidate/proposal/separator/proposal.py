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
from .model import propose_equal_model_gap


@dataclass(frozen=True)
class StandardSeparatorGapProposal:
    gaps: list[Gap]
    detail: dict[str, Any]


@dataclass(frozen=True)
class SeparatorWidthProfileGapProposal:
    gaps: list[Gap]
    detail: dict[str, Any]


def propose_standard_separator_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> Gap:
    gap, _detail = propose_standard_separator_gap_with_detail(
        profile,
        expected,
        pitch,
        index,
        max_width_ratio_override,
        gap_search,
    )
    return gap


def propose_standard_separator_gap_with_detail(
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


def propose_standard_separator_gaps(
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> list[Gap]:
    return propose_standard_separator_gaps_with_detail(
        profile,
        origin,
        pitch,
        count,
        max_width_ratio_override,
        gap_search,
    ).gaps


def propose_standard_separator_gaps_with_detail(
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> StandardSeparatorGapProposal:
    gaps: list[Gap] = []
    entries: list[dict[str, Any]] = []
    for index in range(1, count):
        gap, detail = propose_standard_separator_gap_with_detail(
            profile,
            origin + pitch * index,
            pitch,
            index,
            max_width_ratio_override,
            gap_search,
        )
        gaps.append(gap)
        entries.append(detail)
    return StandardSeparatorGapProposal(
        gaps=gaps,
        detail={
            "used": True,
            "origin": float(origin),
            "pitch": float(pitch),
            "count": int(count),
            "max_width_ratio_override": max_width_ratio_override,
            "detected_count": sum(1 for gap in gaps if gap.method == GAP_DETECTED),
            "fallback_count": sum(1 for gap in gaps if gap.method != GAP_DETECTED),
            "entries": entries,
        },
    )


def propose_separator_width_profile_gaps(
    gray_work: np.ndarray,
    outer: Box,
    count: int,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> list[Gap]:
    return propose_separator_width_profile_gaps_with_detail(
        gray_work,
        outer,
        count,
        width_profile_policy,
        width_profile_search,
    ).gaps


def propose_separator_width_profile_gaps_with_detail(
    gray_work: np.ndarray,
    outer: Box,
    count: int,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthProfileGapProposal:
    required_count = int(width_profile_policy.required_count)
    if (
        width_profile_policy.mode == "off"
        or count <= 1
        or (required_count > 0 and count != required_count)
        or not outer.valid()
    ):
        return SeparatorWidthProfileGapProposal(
            gaps=[],
            detail={
                "used": False,
                "reason": "not_eligible",
                "mode": width_profile_policy.mode,
                "count": int(count),
                "required_count": int(required_count),
                "outer_valid": bool(outer.valid()),
            },
        )
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0:
        return SeparatorWidthProfileGapProposal(
            gaps=[],
            detail={
                "used": False,
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
    return SeparatorWidthProfileGapProposal(
        gaps=gaps,
        detail={
            "used": True,
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


__all__ = [
    "SeparatorWidthProfileGapProposal",
    "StandardSeparatorGapProposal",
    "propose_standard_separator_gap",
    "propose_standard_separator_gap_with_detail",
    "propose_separator_width_profile_gaps",
    "propose_separator_width_profile_gaps_with_detail",
    "propose_standard_separator_gaps",
    "propose_standard_separator_gaps_with_detail",
]
