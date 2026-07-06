from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from .....domain import Box, Gap
from .....gap_methods import is_detected_gap_method
from .....geometry.detection_parameters import (
    GapSearchParameters,
    SeparatorWidthProfileSearchParameters,
)
from .....geometry.gap_search import find_detected_gap
from .....geometry.separator_width_profile import (
    SeparatorPhysicalWidthPrior,
    separator_physical_width_prior,
    separator_width_gap_at_with_detail,
    separator_width_profile as make_separator_width_profile,
)
from .....policies.runtime.separator import SeparatorWidthProfilePolicy
from ....gap_profiles import WIDTH_AWARE_GAP_PROFILE
from .model import propose_equal_model_gap


@dataclass(frozen=True)
class SeparatorGapProfileProposal:
    profile: str
    gaps: list[Gap]
    detail: dict[str, Any]


@dataclass(frozen=True)
class SeparatorGapProposal:
    gap: Gap
    detail: dict[str, Any]


def _selected_gap_detail(gap: Gap, *, include_width: bool = False) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "selected_method": gap.method,
        "selected_center": float(gap.center),
        "selected_score": float(gap.score),
    }
    if include_width:
        detail["selected_width"] = float(gap.width)
    return detail


def _observed_width_selection_detail(width_search_detail: dict[str, Any]) -> dict[str, Any]:
    selected = width_search_detail.get("selected")
    if not isinstance(selected, dict):
        return {}
    detail: dict[str, Any] = {
        "selected_observed_width": selected.get("width"),
        "selected_width_relation_to_prior": selected.get("width_relation_to_prior"),
    }
    if "width_delta_to_prior" in selected:
        detail["selected_width_delta_to_prior"] = selected.get("width_delta_to_prior")
    return detail


def _observed_width_relation_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "narrower_than_prior": 0,
        "matches_prior": 0,
        "broader_than_prior": 0,
        "prior_unavailable": 0,
    }
    for entry in entries:
        if entry.get("selected_source") != "observed_width_profile":
            continue
        relation = entry.get("selected_width_relation_to_prior")
        if relation not in counts:
            relation = "prior_unavailable"
        counts[relation] += 1
    return counts


def _propose_standard_separator_gap_with_detail(
    profile: np.ndarray,
    width_profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    short_axis: float,
    physical_width_prior: SeparatorPhysicalWidthPrior,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> SeparatorGapProposal:
    standard_result = find_detected_gap(
        profile,
        expected,
        pitch,
        index,
        max_width_ratio_override,
        gap_search,
    )
    width_result = (
        separator_width_gap_at_with_detail(
            width_profile,
            expected,
            pitch,
            index,
            short_axis,
            physical_width_prior,
            width_profile_search,
        )
        if width_profile_policy.mode != "off"
        else None
    )
    detail: dict[str, Any] = {
        "index": int(index),
        "profile": WIDTH_AWARE_GAP_PROFILE,
        "reason": standard_result.reason,
        "model_gap_score": float(standard_result.model_gap_score),
        "physical_width_prior": physical_width_prior.detail(),
        "standard_search": standard_result.detail,
        "observed_width_search": (
            width_result.detail
            if width_result is not None
            else {"used": False, "reason": "disabled"}
        ),
    }
    if standard_result.detected_gap is not None:
        gap = standard_result.detected_gap
        detail["selected_source"] = "standard_detected"
    elif width_result is not None and width_result.gap is not None:
        gap = width_result.gap
        detail["reason"] = width_result.reason
        detail["selected_source"] = "observed_width_profile"
        detail["selected_source_role"] = "measured_width_gap"
        detail.update(_observed_width_selection_detail(width_result.detail))
    else:
        gap = propose_equal_model_gap(index, expected, standard_result.model_gap_score)
        detail["selected_source"] = "equal_model"
    detail.update(_selected_gap_detail(gap, include_width=detail.get("selected_source") == "observed_width_profile"))
    return SeparatorGapProposal(gap=gap, detail=detail)


def _propose_standard_separator_gaps_with_detail(
    gray_work: np.ndarray,
    outer: Box,
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    frame_aspect: float | None,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> SeparatorGapProfileProposal:
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    width_profile = (
        make_separator_width_profile(crop, width_profile_search)
        if width_profile_policy.mode != "off" and crop.size > 0 and outer.valid()
        else np.array([], dtype=np.float32)
    )
    physical_width_prior = separator_physical_width_prior(
        float(outer.width),
        float(outer.height),
        count,
        frame_aspect,
    )
    gaps: list[Gap] = []
    entries: list[dict[str, Any]] = []
    for index in range(1, count):
        proposal = _propose_standard_separator_gap_with_detail(
            profile,
            width_profile,
            origin + pitch * index,
            pitch,
            index,
            float(outer.height),
            physical_width_prior,
            max_width_ratio_override,
            gap_search,
            width_profile_policy,
            width_profile_search,
        )
        gaps.append(proposal.gap)
        entries.append(proposal.detail)
    return SeparatorGapProfileProposal(
        profile=WIDTH_AWARE_GAP_PROFILE,
        gaps=gaps,
        detail={
            "used": True,
            "profile": WIDTH_AWARE_GAP_PROFILE,
            "origin": float(origin),
            "pitch": float(pitch),
            "count": int(count),
            "max_width_ratio_override": max_width_ratio_override,
            "physical_width_prior": physical_width_prior.detail(),
            "observed_width_profile_role": "measured_width_gap_when_standard_missing",
            "observed_width_profile_scope": "narrower_matching_or_broader_than_physical_prior",
            "observed_width_profile_used": bool(width_profile.size > 0 and width_profile_policy.mode != "off"),
            "detected_count": sum(1 for gap in gaps if is_detected_gap_method(gap.method)),
            "model_gap_count": sum(1 for gap in gaps if not is_detected_gap_method(gap.method)),
            "observed_width_selected_count": sum(
                1 for entry in entries if entry.get("selected_source") == "observed_width_profile"
            ),
            "observed_width_relation_counts": _observed_width_relation_counts(entries),
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
    frame_aspect: float | None,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> SeparatorGapProfileProposal:
    if gap_search_profile == WIDTH_AWARE_GAP_PROFILE:
        return _propose_standard_separator_gaps_with_detail(
            gray_work,
            outer,
            profile,
            origin,
            pitch,
            count,
            frame_aspect,
            max_width_ratio_override,
            gap_search,
            width_profile_policy,
            width_profile_search,
        )
    raise ValueError(f"Unsupported separator gap search profile: {gap_search_profile!r}")


__all__ = [
    "SeparatorGapProposal",
    "SeparatorGapProfileProposal",
    "propose_separator_gap_profile_gaps_with_detail",
]
