from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, Gap
from ....formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ...gap_profiles import WIDTH_AWARE_GAP_PROFILE
from ..proposal.separator.model import propose_equal_model_gaps_from_profile
from ..proposal.separator.proposal import (
    propose_separator_gap_profile_gaps_with_detail,
)


DETECTED_GEOMETRY_EQUAL_MODEL_SOURCE = "detected_geometry_equal_model"


@dataclass(frozen=True)
class InitialSeparatorGapResult:
    gaps: list[Gap]
    standard_gap_search_detail: dict[str, Any]
    separator_width_profile_gap_search_detail: dict[str, Any]


def skipped_separator_width_profile_gap_search_detail(reason: str = "not_requested") -> dict[str, Any]:
    return {
        "used": False,
        "profile": WIDTH_AWARE_GAP_PROFILE,
        "reason": reason,
    }


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
        separator_width_profile_gap_search_detail=result.separator_width_profile_gap_search_detail,
    )


def standard_separator_gap_result(
    gray_work: np.ndarray,
    fmt: FormatSpec,
    outer: Box,
    profile: np.ndarray,
    count: int,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
    *,
    forced: bool = False,
) -> InitialSeparatorGapResult:
    frame_aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    standard_gap_proposal = propose_separator_gap_profile_gaps_with_detail(
        gray_work,
        outer,
        profile,
        origin,
        pitch,
        count,
        WIDTH_AWARE_GAP_PROFILE,
        frame_aspect,
        gap_max_width_ratio_override,
        policy.separator.gap_search,
        policy.separator.width_profile,
        policy.separator.width_profile_search,
    )
    standard_gap_search_detail = selected_gap_source_detail(
        standard_gap_proposal.detail,
        WIDTH_AWARE_GAP_PROFILE,
    )
    if forced:
        standard_gap_search_detail["forced"] = True
    return InitialSeparatorGapResult(
        gaps=standard_gap_proposal.gaps,
        standard_gap_search_detail=standard_gap_search_detail,
        separator_width_profile_gap_search_detail=skipped_separator_width_profile_gap_search_detail(
            "merged_into_width_aware_proposal"
        ),
    )


def detected_geometry_equal_model_source_available(
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
) -> bool:
    return policy.separator.model_gap_proposal.detected_geometry_equal_model_available(
        strip_mode=strip_mode,
        count=count,
        default_count=fmt.default_count,
        gap_max_width_ratio_override=gap_max_width_ratio_override,
    )


def select_detected_geometry_equal_model_gaps(
    result: InitialSeparatorGapResult,
    profile: np.ndarray,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
) -> InitialSeparatorGapResult:
    if not detected_geometry_equal_model_source_available(
        fmt,
        count,
        strip_mode,
        gap_max_width_ratio_override,
        policy,
    ):
        return result
    return with_selected_gap_source(
        result,
        DETECTED_GEOMETRY_EQUAL_MODEL_SOURCE,
        gaps=propose_equal_model_gaps_from_profile(profile, origin, pitch, count),
        extra_standard_detail={
            "model_gap_proposal": {
                "family": DETECTED_GEOMETRY_EQUAL_MODEL_SOURCE,
                "policy_enabled": True,
            }
        },
    )


def initial_separator_gaps(
    gray_work: np.ndarray,
    outer: Box,
    profile: np.ndarray,
    fmt: FormatSpec,
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
    return select_detected_geometry_equal_model_gaps(
        result,
        profile,
        fmt,
        count=count,
        strip_mode=strip_mode,
        origin=origin,
        pitch=pitch,
        gap_max_width_ratio_override=gap_max_width_ratio_override,
        policy=policy,
    )


__all__ = [
    "DETECTED_GEOMETRY_EQUAL_MODEL_SOURCE",
    "InitialSeparatorGapResult",
    "detected_geometry_equal_model_source_available",
    "initial_separator_gaps",
    "select_detected_geometry_equal_model_gaps",
    "selected_gap_source_detail",
    "skipped_separator_width_profile_gap_search_detail",
    "standard_separator_gap_result",
    "with_selected_gap_source",
]
