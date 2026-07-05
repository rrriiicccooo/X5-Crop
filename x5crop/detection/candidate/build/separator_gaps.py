from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, Gap
from ....formats import FormatSpec
from ....geometry.separator_cache import cached_separator_profile
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ...gap_profiles import BROAD_WIDTH_GAP_PROFILE, STANDARD_GAP_PROFILE
from ..proposal.separator.model import propose_equal_model_gaps_from_profile
from ..proposal.separator.proposal import (
    propose_separator_gap_profile_gaps_with_detail,
)
from .separator_refinements import (
    ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY,
    NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY,
    apply_late_separator_refinement_chain,
    apply_primary_separator_refinements,
    pending_gap_refinement_detail,
)


@dataclass(frozen=True)
class SeparatorGapBuildResult:
    outer: Box
    profile: np.ndarray
    origin: float
    pitch: float
    gaps: list[Gap]
    grid_detail: dict[str, Any]
    standard_gap_search_detail: dict[str, Any]
    separator_width_profile_gap_search_detail: dict[str, Any]
    edge_pair_correction_detail: dict[str, Any]
    enhanced_gap_promotion_detail: dict[str, Any]
    nearby_correction_detail: dict[str, Any]
    pre_nearby_gaps: Optional[list[Gap]]


@dataclass(frozen=True)
class InitialSeparatorGapResult:
    gaps: list[Gap]
    standard_gap_search_detail: dict[str, Any]
    separator_width_profile_gap_search_detail: dict[str, Any]


def separator_origin_pitch(
    outer: Box,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float,
) -> tuple[float, float]:
    if strip_mode == "partial" and count < fmt.default_count:
        pitch = outer.width / float(max(1, fmt.default_count))
        total_width = pitch * count
        origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
        return float(origin), float(pitch)
    return 0.0, float(outer.width / float(max(1, count)))


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


def build_primary_separator_gaps_for_outer(
    gray_work: np.ndarray,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    candidate_strategy: str,
    cache: Optional[AnalysisCache],
    gap_max_width_ratio_override: Optional[float],
    gap_search_profile: str,
    policy: DetectionPolicy,
    force_standard_gap_search: bool = False,
) -> SeparatorGapBuildResult:
    work_height, work_width = gray_work.shape
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0:
        outer = Box(0, 0, work_width, work_height)
        crop = gray_work
    profile = cached_separator_profile(cache, gray_work, outer, policy.separator.profile)
    origin, pitch = separator_origin_pitch(outer, fmt, count, strip_mode, offset_fraction)
    if force_standard_gap_search:
        initial_gaps = standard_separator_gap_result(
            gray_work,
            outer,
            profile,
            count,
            origin,
            pitch,
            gap_max_width_ratio_override,
            policy,
            forced=True,
        )
    else:
        initial_gaps = initial_separator_gaps(
            gray_work,
            outer,
            profile,
            fmt,
            count,
            strip_mode,
            origin,
            pitch,
            candidate_strategy,
            gap_search_profile,
            gap_max_width_ratio_override,
            policy,
        )
    primary_refinement = apply_primary_separator_refinements(
        gray_work,
        outer,
        crop,
        profile,
        initial_gaps.gaps,
        count,
        strip_mode,
        origin,
        pitch,
        cache,
        policy,
    )
    return SeparatorGapBuildResult(
        outer=outer,
        profile=profile,
        origin=origin,
        pitch=pitch,
        gaps=primary_refinement.gaps,
        grid_detail=primary_refinement.grid_detail,
        standard_gap_search_detail=initial_gaps.standard_gap_search_detail,
        separator_width_profile_gap_search_detail=initial_gaps.separator_width_profile_gap_search_detail,
        edge_pair_correction_detail=primary_refinement.edge_pair_correction_detail,
        enhanced_gap_promotion_detail=pending_gap_refinement_detail(ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY),
        nearby_correction_detail=pending_gap_refinement_detail(NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY),
        pre_nearby_gaps=None,
    )


def apply_late_separator_refinements(
    gray_work: np.ndarray,
    analysis_mode: str,
    count: int,
    strip_mode: str,
    separator_gaps: SeparatorGapBuildResult,
    allow_enhanced_gap_promotion: bool,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> SeparatorGapBuildResult:
    late_refinement = apply_late_separator_refinement_chain(
        gray_work,
        analysis_mode,
        count,
        strip_mode,
        separator_gaps.outer,
        separator_gaps.profile,
        separator_gaps.gaps,
        separator_gaps.origin,
        separator_gaps.pitch,
        allow_enhanced_gap_promotion,
        cache,
        policy,
    )
    return SeparatorGapBuildResult(
        outer=separator_gaps.outer,
        profile=separator_gaps.profile,
        origin=separator_gaps.origin,
        pitch=separator_gaps.pitch,
        gaps=late_refinement.gaps,
        grid_detail=separator_gaps.grid_detail,
        standard_gap_search_detail=separator_gaps.standard_gap_search_detail,
        separator_width_profile_gap_search_detail=separator_gaps.separator_width_profile_gap_search_detail,
        edge_pair_correction_detail=separator_gaps.edge_pair_correction_detail,
        enhanced_gap_promotion_detail=late_refinement.enhanced_gap_promotion_detail,
        nearby_correction_detail=late_refinement.nearby_correction_detail,
        pre_nearby_gaps=late_refinement.pre_nearby_gaps,
    )

__all__ = [
    "InitialSeparatorGapResult",
    "SeparatorGapBuildResult",
    "apply_late_separator_refinements",
    "build_primary_separator_gaps_for_outer",
    "initial_separator_gaps",
    "separator_origin_pitch",
]
