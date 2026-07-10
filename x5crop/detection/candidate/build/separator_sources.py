from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, Gap
from ....formats import FormatPhysicalSpec
from ....policies.runtime.policy import DetectionPolicy
from ...physical.separator.hints import SeparatorGapHintSet
from ...physical.separator.model import propose_equal_model_gaps_from_profile
from ...physical.separator.proposal import (
    propose_separator_gaps_with_detail,
)


GEOMETRY_EQUAL_MODEL_SOURCE = "geometry_equal_model"


@dataclass(frozen=True)
class InitialSeparatorGapResult:
    gaps: list[Gap]
    standard_gap_search_detail: dict[str, Any]


def selected_gap_source_detail(
    detail: dict[str, Any],
    source: str,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    result = dict(detail)
    result["selected_gap_source"] = source
    if extra:
        result.update(extra)
    return result


def with_selected_gap_source(
    result: InitialSeparatorGapResult,
    source: str,
    *,
    gaps: Optional[list[Gap]] = None,
    extra_standard_detail: Optional[dict[str, Any]] = None,
) -> InitialSeparatorGapResult:
    return InitialSeparatorGapResult(
        gaps=result.gaps if gaps is None else gaps,
        standard_gap_search_detail=selected_gap_source_detail(
            result.standard_gap_search_detail,
            source,
            extra_standard_detail,
        ),
    )


def standard_separator_gap_result(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    outer: Box,
    profile: np.ndarray,
    count: int,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
    *,
    forced: bool = False,
    gap_hints: Optional[SeparatorGapHintSet] = None,
) -> InitialSeparatorGapResult:
    frame_aspect = float(fmt.horizontal_content_aspect)
    standard_gap_proposal = propose_separator_gaps_with_detail(
        gray_work,
        outer,
        profile,
        origin,
        pitch,
        count,
        frame_aspect,
        gap_max_width_ratio_override,
        policy.separator.gap_search,
        policy.separator.width_profile,
        policy.separator.width_profile_search,
        gap_hints,
    )
    standard_gap_search_detail = selected_gap_source_detail(
        standard_gap_proposal.search_detail,
        "standard_and_observed_width",
    )
    if forced:
        standard_gap_search_detail["forced"] = True
    return InitialSeparatorGapResult(
        gaps=standard_gap_proposal.gaps,
        standard_gap_search_detail=standard_gap_search_detail,
    )


def model_gap_proposal_detail(
    result: InitialSeparatorGapResult,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    gap_max_width_ratio_override: Optional[float],
) -> dict[str, Any]:
    expected_gaps = max(0, int(count) - 1)
    hard_gaps = int(result.standard_gap_search_detail.get("detected_count", 0) or 0)
    if strip_mode != "full":
        block_reason = "requires_full_strip"
    elif int(count) != int(fmt.default_count):
        block_reason = "non_default_count"
    elif gap_max_width_ratio_override is not None:
        block_reason = "width_override_active"
    elif expected_gaps <= 0:
        block_reason = "single_frame"
    elif hard_gaps >= expected_gaps:
        block_reason = "hard_gaps_complete"
    else:
        block_reason = None
    return {
        "family": GEOMETRY_EQUAL_MODEL_SOURCE,
        "available": block_reason is None,
        "reason": "available" if block_reason is None else block_reason,
        "expected_gaps": int(expected_gaps),
        "hard_gaps": int(hard_gaps),
        "eligibility": "full_default_count",
    }


def with_model_gap_proposal_detail(
    result: InitialSeparatorGapResult,
    detail: dict[str, Any],
) -> InitialSeparatorGapResult:
    standard_detail = dict(result.standard_gap_search_detail)
    standard_detail["model_gap_proposal"] = detail
    return InitialSeparatorGapResult(
        gaps=result.gaps,
        standard_gap_search_detail=standard_detail,
    )


def select_geometry_equal_model_gaps(
    result: InitialSeparatorGapResult,
    profile: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: Optional[float],
) -> InitialSeparatorGapResult:
    model_detail = model_gap_proposal_detail(
        result,
        fmt,
        count,
        strip_mode,
        gap_max_width_ratio_override,
    )
    result = with_model_gap_proposal_detail(result, model_detail)
    if not bool(model_detail.get("available", False)):
        return result
    return with_selected_gap_source(
        result,
        GEOMETRY_EQUAL_MODEL_SOURCE,
        gaps=propose_equal_model_gaps_from_profile(profile, origin, pitch, count),
        extra_standard_detail={
            "model_gap_proposal": {
                **model_detail,
                "selected": True,
            }
        },
    )


def initial_separator_gaps(
    gray_work: np.ndarray,
    outer: Box,
    profile: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
) -> InitialSeparatorGapResult:
    result = standard_separator_gap_result(
        gray_work,
        fmt,
        outer,
        profile,
        count,
        origin,
        pitch,
        gap_max_width_ratio_override,
        policy,
    )
    return select_geometry_equal_model_gaps(
        result,
        profile,
        fmt,
        count=count,
        strip_mode=strip_mode,
        origin=origin,
        pitch=pitch,
        gap_max_width_ratio_override=gap_max_width_ratio_override,
    )
