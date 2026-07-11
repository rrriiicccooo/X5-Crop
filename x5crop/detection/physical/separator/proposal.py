from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, SeparatorBandObservation
from ....gap_methods import is_detected_gap_method
from ....geometry.detection_parameters import (
    GapSearchParameters,
    SeparatorWidthProfileSearchParameters,
)
from ....geometry.gap_search import find_detected_gap
from ....geometry.model_gaps import equal_model_gap
from ....geometry.separator_width_profile import (
    separator_width_gap_at_with_detail,
    TheoreticalSeparatorWidth,
    theoretical_separator_width,
)
from ....policies.runtime.separator import SeparatorWidthProfilePolicy
from ....utils import clamp_int
from ..photo_size import photo_size_consistency_from_gap_edges
from .hints import SeparatorGapHintSet


@dataclass(frozen=True)
class SeparatorGapSearchResult:
    gaps: list[SeparatorBandObservation]
    search_detail: dict[str, Any]


@dataclass(frozen=True)
class SeparatorGapProposal:
    gap: SeparatorBandObservation
    detail: dict[str, Any]


def _selected_gap_detail(gap: SeparatorBandObservation, *, include_width: bool = False) -> dict[str, Any]:
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
        "selected_width_relation_to_theory": selected.get("width_relation_to_theory"),
    }
    if "width_delta_to_theory" in selected:
        detail["selected_width_delta_to_theory"] = selected.get("width_delta_to_theory")
    return detail


def _observed_width_relation_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "narrower_than_theory": 0,
        "matches_theory": 0,
        "broader_than_theory": 0,
        "theory_unavailable": 0,
    }
    for entry in entries:
        if entry.get("selected_source") != "observed_width_profile":
            continue
        relation = entry.get("selected_width_relation_to_theory")
        if relation not in counts:
            relation = "theory_unavailable"
        counts[relation] += 1
    return counts


def _gap_hint_search_detail(
    gap_hints: Optional[SeparatorGapHintSet],
    *,
    index: int,
    expected: float,
    pitch: float,
) -> tuple[float, dict[str, Any]]:
    if gap_hints is None:
        return expected, {"used": False, "reason": "no_gap_hints"}
    hint = gap_hints.hint_for_index(index)
    if hint is None:
        return expected, {
            "used": False,
            "source": gap_hints.source,
            "role": gap_hints.role,
            "reason": "missing_index_hint",
        }
    max_offset = clamp_int(
        float(pitch) * float(gap_hints.max_offset_ratio),
        int(gap_hints.max_offset_min),
        int(gap_hints.max_offset_max),
    )
    offset = float(hint.center) - float(expected)
    applied = abs(offset) <= float(max_offset)
    detail = {
        "used": True,
        "source": gap_hints.source,
        "role": gap_hints.role,
        "index": int(index),
        "standard_expected_center": float(expected),
        "hint_center": float(hint.center),
        "hint_offset": float(offset),
        "max_offset": int(max_offset),
        "applied": bool(applied),
        "reason": "applied" if applied else "hint_too_far_from_geometry",
    }
    if not applied:
        return expected, detail
    return float(hint.center), detail


def _propose_standard_separator_gap_with_detail(
    profile: np.ndarray,
    width_profile: np.ndarray,
    search_expected: float,
    model_expected: float,
    pitch: float,
    index: int,
    short_axis: float,
    separator_width_theory: TheoreticalSeparatorWidth,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
) -> SeparatorGapProposal:
    standard_result = find_detected_gap(
        profile,
        search_expected,
        pitch,
        index,
        gap_search,
        max_width_ratio_override=max_width_ratio_override,
    )
    width_result = (
        separator_width_gap_at_with_detail(
            width_profile,
            search_expected,
            pitch,
            index,
            short_axis,
            width_profile_search,
            theory=separator_width_theory,
        )
        if width_profile_policy.mode != "off"
        else None
    )
    detail: dict[str, Any] = {
        "index": int(index),
        "search_method": "standard_and_observed_width",
        "reason": standard_result.reason,
        "standard_expected_center": float(model_expected),
        "search_expected_center": float(search_expected),
        "model_gap_score": float(standard_result.model_gap_score),
        "theoretical_separator_width": separator_width_theory.detail(),
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
        gap = equal_model_gap(index, model_expected, standard_result.model_gap_score)
        detail["selected_source"] = "equal_model"
    detail.update(_selected_gap_detail(gap, include_width=detail.get("selected_source") == "observed_width_profile"))
    return SeparatorGapProposal(gap=gap, detail=detail)


def propose_separator_gaps_with_detail(
    outer: Box,
    profile: np.ndarray,
    width_profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    frame_aspect: float | None,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
    width_profile_policy: SeparatorWidthProfilePolicy,
    width_profile_search: SeparatorWidthProfileSearchParameters,
    gap_hints: Optional[SeparatorGapHintSet] = None,
) -> SeparatorGapSearchResult:
    separator_width_theory = theoretical_separator_width(
        float(outer.width),
        float(outer.height),
        count,
        frame_aspect,
    )
    gaps: list[SeparatorBandObservation] = []
    entries: list[dict[str, Any]] = []
    applied_hint_count = 0
    for index in range(1, count):
        standard_expected = origin + pitch * index
        search_expected, hint_detail = _gap_hint_search_detail(
            gap_hints,
            index=index,
            expected=standard_expected,
            pitch=pitch,
        )
        if bool(hint_detail.get("applied", False)):
            applied_hint_count += 1
        proposal = _propose_standard_separator_gap_with_detail(
            profile,
            width_profile,
            search_expected,
            standard_expected,
            pitch,
            index,
            float(outer.height),
            separator_width_theory,
            max_width_ratio_override,
            gap_search,
            width_profile_policy,
            width_profile_search,
        )
        proposal.detail["gap_hint"] = hint_detail
        gaps.append(proposal.gap)
        entries.append(proposal.detail)
    target_photo_width = float(outer.height) * float(frame_aspect) if frame_aspect is not None and frame_aspect > 0.0 else None
    photo_size_consistency = photo_size_consistency_from_gap_edges(
        gaps,
        origin,
        pitch,
        count,
        target_photo_width=target_photo_width,
    )
    return SeparatorGapSearchResult(
        gaps=gaps,
        search_detail={
            "used": True,
            "search_method": "standard_and_observed_width",
            "origin": float(origin),
            "pitch": float(pitch),
            "count": int(count),
            "max_width_ratio_override": max_width_ratio_override,
            "theoretical_separator_width": separator_width_theory.detail(),
            "photo_size_consistency": photo_size_consistency.detail(),
            "gap_hint_guidance": (
                {
                    "used": bool(gap_hints is not None and gap_hints.hints),
                    "source": gap_hints.source,
                    "role": gap_hints.role,
                    "hint_count": len(gap_hints.hints),
                    "applied_hint_count": int(applied_hint_count),
                }
                if gap_hints is not None
                else {"used": False, "reason": "no_gap_hints"}
            ),
            "observed_width_profile_role": "measured_width_gap_when_standard_missing",
            "observed_width_profile_scope": "narrower_matching_or_broader_than_theoretical_mean",
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


def separator_gap_search_detail(
    width_profile_policy: SeparatorWidthProfilePolicy,
) -> dict[str, Any]:
    width_measurement_enabled = width_profile_policy.mode != "off"
    return {
        "used": True,
        "search_method": "standard_and_observed_width",
        "standard_search": True,
        "theoretical_width_search": width_measurement_enabled,
        "observed_width_search": width_measurement_enabled,
    }
