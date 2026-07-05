from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....cache import AnalysisCache
from ....domain import Box, Gap
from ....geometry.edge_pairs import refine_gaps_with_edge_profiles
from ....geometry.enhanced_separator import (
    promote_enhanced_separator_gaps,
    should_run_enhanced_gap_promotion,
)
from ....geometry.nearby_separator import apply_nearby_separator_corrections
from ....geometry.robust_grid import apply_robust_grid
from ....geometry.separator_cache import cached_edge_refine_profiles
from ....policies.runtime.policy import DetectionPolicy


EDGE_PAIR_REFINEMENT_FAMILY = "edge_pair"
ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY = "enhanced_gap_promotion"
NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY = "nearby_separator_correction"
LATE_REFINEMENT_PENDING_REASON = "pending_late_refinement"


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


def pending_gap_refinement_detail(family: str) -> dict[str, Any]:
    return _gap_refinement_detail(
        family,
        {"used": False, "reason": LATE_REFINEMENT_PENDING_REASON},
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
    outer: Box,
    profile: np.ndarray,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    allow_enhanced_gap_promotion: bool,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> LateSeparatorRefinementResult:
    enhanced_gap_promotion = apply_enhanced_gap_promotion(
        gray_work,
        outer,
        gaps,
        count,
        strip_mode,
        origin,
        pitch,
        allow_enhanced_gap_promotion,
        analysis_mode,
        cache,
        policy,
    )
    nearby_correction = apply_nearby_separator_refinement(
        profile,
        enhanced_gap_promotion.gaps,
        count,
        strip_mode,
        origin,
        pitch,
        policy,
    )
    return LateSeparatorRefinementResult(
        gaps=nearby_correction.gaps,
        enhanced_gap_promotion_detail=enhanced_gap_promotion.detail,
        nearby_correction_detail=nearby_correction.detail,
        pre_nearby_gaps=nearby_correction.pre_refinement_gaps,
    )


__all__ = [
    "EDGE_PAIR_REFINEMENT_FAMILY",
    "ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY",
    "GapRefinementResult",
    "LATE_REFINEMENT_PENDING_REASON",
    "LateSeparatorRefinementResult",
    "NEARBY_SEPARATOR_CORRECTION_REFINEMENT_FAMILY",
    "PrimarySeparatorRefinementResult",
    "apply_edge_pair_refinement",
    "apply_enhanced_gap_promotion",
    "apply_late_separator_refinement_chain",
    "apply_nearby_separator_refinement",
    "apply_primary_separator_refinements",
    "pending_gap_refinement_detail",
]
