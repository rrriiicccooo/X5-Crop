from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, Gap
from ....formats import FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ...gap_profiles import BROAD_WIDTH_GAP_PROFILE, STANDARD_GAP_PROFILE
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
        "profile": BROAD_WIDTH_GAP_PROFILE,
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
    standard_gap_proposal = propose_separator_gap_profile_gaps_with_detail(
        gray_work,
        outer,
        profile,
        origin,
        pitch,
        count,
        STANDARD_GAP_PROFILE,
        gap_max_width_ratio_override,
        policy.separator.gap_search,
        policy.separator.width_profile,
        policy.separator.width_profile_search,
    )
    standard_gap_search_detail = selected_gap_source_detail(
        standard_gap_proposal.detail,
        STANDARD_GAP_PROFILE,
    )
    if forced:
        standard_gap_search_detail["forced"] = True
    return InitialSeparatorGapResult(
        gaps=standard_gap_proposal.gaps,
        standard_gap_search_detail=standard_gap_search_detail,
        separator_width_profile_gap_search_detail=skipped_separator_width_profile_gap_search_detail(),
    )


def separator_width_profile_gap_requested(candidate_strategy: str, gap_search_profile: str) -> bool:
    return candidate_strategy == "separator_outer" and gap_search_profile == BROAD_WIDTH_GAP_PROFILE


def separator_width_profile_source_complete(gaps: list[Gap], count: int) -> bool:
    return len(gaps) >= max(1, count - 1)


def select_separator_width_profile_gaps(
    result: InitialSeparatorGapResult,
    gray_work: np.ndarray,
    outer: Box,
    profile: np.ndarray,
    count: int,
    origin: float,
    pitch: float,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
) -> InitialSeparatorGapResult:
    separator_width_profile_proposal = propose_separator_gap_profile_gaps_with_detail(
        gray_work,
        outer,
        profile,
        origin,
        pitch,
        count,
        BROAD_WIDTH_GAP_PROFILE,
        gap_max_width_ratio_override,
        policy.separator.gap_search,
        policy.separator.width_profile,
        policy.separator.width_profile_search,
    )
    separator_width_profile_gaps = separator_width_profile_proposal.gaps
    selected_result = result
    if separator_width_profile_source_complete(separator_width_profile_gaps, count):
        selected_result = with_selected_gap_source(
            result,
            BROAD_WIDTH_GAP_PROFILE,
            gaps=separator_width_profile_gaps,
        )
    return InitialSeparatorGapResult(
        gaps=selected_result.gaps,
        standard_gap_search_detail=selected_result.standard_gap_search_detail,
        separator_width_profile_gap_search_detail=dict(separator_width_profile_proposal.detail),
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
    candidate_strategy: str,
    gap_search_profile: str,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
) -> InitialSeparatorGapResult:
    result = standard_separator_gap_result(
        gray_work,
        outer,
        profile,
        count,
        origin,
        pitch,
        gap_max_width_ratio_override,
        policy,
    )
    if separator_width_profile_gap_requested(candidate_strategy, gap_search_profile):
        result = select_separator_width_profile_gaps(
            result,
            gray_work,
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
    "select_separator_width_profile_gaps",
    "selected_gap_source_detail",
    "separator_width_profile_source_complete",
    "separator_width_profile_gap_requested",
    "skipped_separator_width_profile_gap_search_detail",
    "standard_separator_gap_result",
    "with_selected_gap_source",
]
