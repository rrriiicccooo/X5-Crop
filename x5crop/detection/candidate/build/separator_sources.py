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
    standard_gap_search_detail = dict(standard_gap_proposal.detail)
    standard_gap_search_detail["selected_gap_source"] = STANDARD_GAP_PROFILE
    if forced:
        standard_gap_search_detail["forced"] = True
    return InitialSeparatorGapResult(
        gaps=standard_gap_proposal.gaps,
        standard_gap_search_detail=standard_gap_search_detail,
        separator_width_profile_gap_search_detail=skipped_separator_width_profile_gap_search_detail(),
    )


def separator_width_profile_gap_requested(candidate_strategy: str, gap_search_profile: str) -> bool:
    return candidate_strategy == "separator_outer" and gap_search_profile == BROAD_WIDTH_GAP_PROFILE


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
    gaps = result.gaps
    standard_gap_search_detail = dict(result.standard_gap_search_detail)
    separator_width_profile_gaps = separator_width_profile_proposal.gaps
    if len(separator_width_profile_gaps) >= max(1, count - 1):
        gaps = separator_width_profile_gaps
        standard_gap_search_detail["selected_gap_source"] = BROAD_WIDTH_GAP_PROFILE
    return InitialSeparatorGapResult(
        gaps=gaps,
        standard_gap_search_detail=standard_gap_search_detail,
        separator_width_profile_gap_search_detail=dict(separator_width_profile_proposal.detail),
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
    model_gap_proposal = policy.separator.model_gap_proposal
    if not model_gap_proposal.detected_geometry_equal_model_available(
        strip_mode=strip_mode,
        count=count,
        default_count=fmt.default_count,
        gap_max_width_ratio_override=gap_max_width_ratio_override,
    ):
        return result
    standard_gap_search_detail = dict(result.standard_gap_search_detail)
    standard_gap_search_detail["selected_gap_source"] = "detected_geometry_equal_model"
    standard_gap_search_detail["model_gap_proposal"] = {
        "family": "detected_geometry_equal_model",
        "policy_enabled": True,
    }
    return InitialSeparatorGapResult(
        gaps=propose_equal_model_gaps_from_profile(profile, origin, pitch, count),
        standard_gap_search_detail=standard_gap_search_detail,
        separator_width_profile_gap_search_detail=result.separator_width_profile_gap_search_detail,
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
    "InitialSeparatorGapResult",
    "initial_separator_gaps",
    "select_detected_geometry_equal_model_gaps",
    "select_separator_width_profile_gaps",
    "separator_width_profile_gap_requested",
    "skipped_separator_width_profile_gap_search_detail",
    "standard_separator_gap_result",
]
