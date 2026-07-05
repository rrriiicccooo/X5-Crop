from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, Gap
from ....formats import FormatSpec
from ....geometry.edge_pairs import refine_gaps_with_edge_profiles
from ....geometry.enhanced_separator import (
    promote_enhanced_separator_gaps,
    should_run_enhanced_gap_promotion,
)
from ....geometry.nearby_separator import apply_nearby_separator_corrections
from ....geometry.robust_grid import apply_robust_grid
from ....geometry.separator_cache import cached_edge_refine_profiles, cached_separator_profile
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ...gap_profiles import BROAD_WIDTH_GAP_PROFILE, STANDARD_GAP_PROFILE
from ..proposal.separator.model import propose_equal_model_gaps_from_profile
from ..proposal.separator.proposal import (
    propose_separator_gap_profile_gaps_with_detail,
)


EDGE_PAIR_REFINEMENT_FAMILY = "edge_pair"
ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY = "enhanced_gap_promotion"
NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY = "nearby_separator_correction"
LATE_REFINEMENT_PENDING_REASON = "pending_late_refinement"


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


@dataclass(frozen=True)
class PrimarySeparatorRefinementResult:
    gaps: list[Gap]
    edge_pair_correction_detail: dict[str, Any]
    grid_detail: dict[str, Any]


@dataclass(frozen=True)
class LateSeparatorRefinementResult:
    gaps: list[Gap]
    enhanced_gap_promotion_detail: dict[str, Any]
    nearby_correction_detail: dict[str, Any]
    pre_nearby_gaps: Optional[list[Gap]]


@dataclass(frozen=True)
class GapRefinementResult:
    family: str
    gaps: list[Gap]
    detail: dict[str, Any]
    pre_refinement_gaps: Optional[list[Gap]] = None


def _gap_refinement_detail(
    family: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    result_detail = dict(detail)
    result_detail.setdefault("family", family)
    return result_detail


def _gap_refinement_result(
    family: str,
    gaps: list[Gap],
    detail: dict[str, Any],
    *,
    pre_refinement_gaps: Optional[list[Gap]] = None,
) -> GapRefinementResult:
    return GapRefinementResult(
        family=family,
        gaps=gaps,
        detail=_gap_refinement_detail(family, detail),
        pre_refinement_gaps=pre_refinement_gaps,
    )


def _skipped_gap_refinement_result(
    family: str,
    gaps: list[Gap],
    reason: str,
) -> GapRefinementResult:
    return _gap_refinement_result(
        family,
        gaps,
        {"used": False, "reason": reason},
    )


def _pending_gap_refinement_detail(family: str) -> dict[str, Any]:
    return _gap_refinement_detail(
        family,
        {"used": False, "reason": LATE_REFINEMENT_PENDING_REASON},
    )


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


def apply_edge_pair_refinement(
    outer: Box,
    crop: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> GapRefinementResult:
    if strip_mode != "full":
        return _skipped_gap_refinement_result(EDGE_PAIR_REFINEMENT_FAMILY, gaps, "not_full_strip")
    if count <= 1:
        return _skipped_gap_refinement_result(EDGE_PAIR_REFINEMENT_FAMILY, gaps, "single_frame")
    edge, background, _activity = cached_edge_refine_profiles(
        cache,
        crop,
        outer,
        policy.separator.edge_refine_profile,
    )
    correction = refine_gaps_with_edge_profiles(
        edge,
        background,
        gaps,
        count,
        policy.separator.edge_pair,
    )
    return _gap_refinement_result(
        EDGE_PAIR_REFINEMENT_FAMILY,
        correction.gaps,
        correction.detail,
    )


def apply_primary_separator_refinements(
    gray_work: np.ndarray,
    outer: Box,
    crop: np.ndarray,
    profile: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> PrimarySeparatorRefinementResult:
    edge_pair_refinement = apply_edge_pair_refinement(
        outer,
        crop,
        gaps,
        count,
        strip_mode,
        cache,
        policy,
    )
    gaps = edge_pair_refinement.gaps
    grid = apply_robust_grid(
        gaps,
        origin,
        pitch,
        strip_mode,
        profile,
        gray_work,
        outer,
        policy.separator.hard_gap_trust,
        policy.separator.nearby_correction,
        policy.separator.robust_grid,
    )
    return PrimarySeparatorRefinementResult(
        gaps=grid.gaps,
        edge_pair_correction_detail=edge_pair_refinement.detail,
        grid_detail=grid.detail,
    )


def apply_enhanced_gap_promotion(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    allow_enhanced_gap_promotion: bool,
    analysis_mode: str,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> GapRefinementResult:
    if not allow_enhanced_gap_promotion:
        return _skipped_gap_refinement_result(ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY, gaps, "disabled")
    if strip_mode != "full":
        return _skipped_gap_refinement_result(ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY, gaps, "not_full_strip")
    if policy.separator.model_gap_proposal.detected_geometry_equal_model_enabled:
        return _skipped_gap_refinement_result(
            ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY,
            gaps,
            "detected_geometry_equal_model_enabled",
        )
    if should_run_enhanced_gap_promotion(analysis_mode, gaps, count, policy.separator.enhanced):
        promotion = promote_enhanced_separator_gaps(
            gray_work,
            outer,
            gaps,
            origin,
            pitch,
            strip_mode,
            cache,
            policy.separator.robust_grid,
            policy.separator.gap_search,
            policy.separator.profile,
            policy.separator.enhanced,
        )
        return _gap_refinement_result(
            ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY,
            promotion.gaps,
            promotion.detail,
        )
    if analysis_mode == "auto":
        return _skipped_gap_refinement_result(ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY, gaps, "auto_not_needed")
    return _skipped_gap_refinement_result(ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY, gaps, "disabled")


def apply_nearby_separator_refinement(
    profile: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    policy: DetectionPolicy,
) -> GapRefinementResult:
    if strip_mode != "full":
        return _skipped_gap_refinement_result(NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY, gaps, "not_full_strip")
    if not policy.separator.nearby_correction.enabled:
        return _skipped_gap_refinement_result(NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY, gaps, "disabled")
    pre_nearby_gaps = list(gaps)
    correction = apply_nearby_separator_corrections(
        profile,
        gaps,
        origin,
        pitch,
        count,
        strip_mode,
        policy.separator.nearby_correction,
    )
    refined_gaps = correction.gaps
    detail = correction.detail
    if int(detail.get("accepted_count", 0) or 0) > 0:
        return _gap_refinement_result(
            NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY,
            refined_gaps,
            detail,
            pre_refinement_gaps=pre_nearby_gaps,
        )
    return _gap_refinement_result(
        NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY,
        refined_gaps,
        detail,
    )


def apply_late_separator_refinement_chain(
    gray_work: np.ndarray,
    analysis_mode: str,
    count: int,
    strip_mode: str,
    separator_gaps: SeparatorGapBuildResult,
    allow_enhanced_gap_promotion: bool,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> LateSeparatorRefinementResult:
    enhanced_gap_promotion = apply_enhanced_gap_promotion(
        gray_work,
        separator_gaps.outer,
        separator_gaps.gaps,
        count,
        strip_mode,
        separator_gaps.origin,
        separator_gaps.pitch,
        allow_enhanced_gap_promotion,
        analysis_mode,
        cache,
        policy,
    )
    nearby_correction = apply_nearby_separator_refinement(
        separator_gaps.profile,
        enhanced_gap_promotion.gaps,
        count,
        strip_mode,
        separator_gaps.origin,
        separator_gaps.pitch,
        policy,
    )
    return LateSeparatorRefinementResult(
        gaps=nearby_correction.gaps,
        enhanced_gap_promotion_detail=enhanced_gap_promotion.detail,
        nearby_correction_detail=nearby_correction.detail,
        pre_nearby_gaps=nearby_correction.pre_refinement_gaps,
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
        enhanced_gap_promotion_detail=_pending_gap_refinement_detail(ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY),
        nearby_correction_detail=_pending_gap_refinement_detail(NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY),
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
        separator_gaps,
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
    "GapRefinementResult",
    "InitialSeparatorGapResult",
    "LateSeparatorRefinementResult",
    "PrimarySeparatorRefinementResult",
    "SeparatorGapBuildResult",
    "apply_edge_pair_refinement",
    "apply_enhanced_gap_promotion",
    "apply_late_separator_refinement_chain",
    "apply_late_separator_refinements",
    "apply_nearby_separator_refinement",
    "apply_primary_separator_refinements",
    "build_primary_separator_gaps_for_outer",
    "initial_separator_gaps",
    "separator_origin_pitch",
]
