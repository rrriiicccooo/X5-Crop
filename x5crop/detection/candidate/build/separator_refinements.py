from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....cache import AnalysisCache
from ....cache.separator import cached_edge_refine_profiles, cached_promote_enhanced_separator_gaps
from ....domain import Box, Gap
from ....geometry.detection_parameters import (
    EnhancedSeparatorParameters,
    GapGeometryConstraintParameters,
    RobustGridExecutionParameters,
    RobustGridParameters,
)
from ....geometry.edge_pairs import refine_gaps_with_edge_profiles
from ....geometry.enhanced_separator import should_run_enhanced_gap_promotion
from ....geometry.nearby_separator import apply_nearby_separator_refinement as refine_nearby_separator_gaps
from ....geometry.robust_grid import apply_robust_grid
from ....policies.runtime.policy import DetectionPolicy


EDGE_PAIR_REFINEMENT_FAMILY = "edge_pair"
ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY = "enhanced_gap_promotion"
NEARBY_SEPARATOR_REFINEMENT_FAMILY = "nearby_separator_refinement"
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
    nearby_refinement_detail: dict[str, Any]
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


def gap_geometry_parameters_for_strip_mode(
    parameters: RobustGridParameters,
    strip_mode: str,
) -> GapGeometryConstraintParameters:
    shift_ratio = (
        parameters.constrain_full_shift_ratio
        if strip_mode == "full"
        else parameters.constrain_partial_shift_ratio
    )
    return GapGeometryConstraintParameters(
        shift_ratio=float(shift_ratio),
        shift_min=float(parameters.constrain_shift_min),
        shift_max=float(parameters.constrain_shift_max),
    )


def robust_grid_execution_parameters_for_strip_mode(
    parameters: RobustGridParameters,
    strip_mode: str,
) -> RobustGridExecutionParameters:
    return RobustGridExecutionParameters(
        constrain=gap_geometry_parameters_for_strip_mode(parameters, strip_mode),
        reliable_min_score=float(parameters.reliable_min_score),
        min_reliable=int(parameters.min_reliable),
        pitch_min_ratio=float(parameters.pitch_min_ratio),
        pitch_max_ratio=float(parameters.pitch_max_ratio),
        fit_tolerance_ratio=(
            float(parameters.full_tolerance_ratio)
            if strip_mode == "full"
            else float(parameters.partial_tolerance_ratio)
        ),
        tolerance_min=float(parameters.tolerance_min),
        tolerance_max=float(parameters.tolerance_max),
        reject_residual_ratio=float(parameters.reject_residual_ratio),
        shift_ratio=(
            float(parameters.full_shift_ratio)
            if strip_mode == "full"
            else float(parameters.partial_shift_ratio)
        ),
        shift_min=float(parameters.shift_min),
        shift_max=float(parameters.shift_max),
        hard_keep_ratio=float(parameters.hard_keep_ratio),
        hard_keep_min=float(parameters.hard_keep_min),
        hard_keep_max=float(parameters.hard_keep_max),
        hard_protect_ratio=float(parameters.hard_protect_ratio),
        hard_protect_min=float(parameters.hard_protect_min),
        hard_protect_max=float(parameters.hard_protect_max),
    )


def edge_pair_refinement_skip_reason(count: int, strip_mode: str) -> Optional[str]:
    if strip_mode != "full":
        return "not_full_strip"
    if count <= 1:
        return "single_frame"
    return None


def apply_edge_pair_refinement(
    outer: Box,
    crop: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> GapRefinementResult:
    skip_reason = edge_pair_refinement_skip_reason(count, strip_mode)
    if skip_reason is not None:
        return _skipped_gap_refinement_result(EDGE_PAIR_REFINEMENT_FAMILY, gaps, skip_reason)
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
    robust_grid_parameters = robust_grid_execution_parameters_for_strip_mode(
        policy.separator.robust_grid,
        strip_mode,
    )
    grid = apply_robust_grid(
        gaps,
        origin,
        pitch,
        profile,
        gray_work,
        outer,
        policy.separator.hard_gap_trust,
        policy.separator.nearby_refinement,
        robust_grid_parameters,
    )
    return PrimarySeparatorRefinementResult(
        gaps=grid.gaps,
        edge_pair_correction_detail=edge_pair_refinement.detail,
        grid_detail=grid.detail,
    )


def enhanced_gap_promotion_skip_reason(
    *,
    allow_enhanced_gap_promotion: bool,
    strip_mode: str,
    analysis_mode: str,
    gaps: list[Gap],
    count: int,
    geometry_equal_model_selected: bool,
    enhanced_config: EnhancedSeparatorParameters,
) -> Optional[str]:
    if not allow_enhanced_gap_promotion:
        return "disabled"
    if strip_mode != "full":
        return "not_full_strip"
    if geometry_equal_model_selected:
        return "geometry_equal_model_selected"
    if should_run_enhanced_gap_promotion(analysis_mode, gaps, count, enhanced_config):
        return None
    if analysis_mode == "auto":
        return "auto_not_needed"
    return "disabled"


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
    geometry_equal_model_selected: bool,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> GapRefinementResult:
    skip_reason = enhanced_gap_promotion_skip_reason(
        allow_enhanced_gap_promotion=allow_enhanced_gap_promotion,
        strip_mode=strip_mode,
        analysis_mode=analysis_mode,
        gaps=gaps,
        count=count,
        geometry_equal_model_selected=geometry_equal_model_selected,
        enhanced_config=policy.separator.enhanced,
    )
    if skip_reason is not None:
        return _skipped_gap_refinement_result(ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY, gaps, skip_reason)
    robust_grid_parameters = robust_grid_execution_parameters_for_strip_mode(
        policy.separator.robust_grid,
        strip_mode,
    )
    promotion = cached_promote_enhanced_separator_gaps(
        gray_work,
        outer,
        gaps,
        origin,
        pitch,
        strip_mode,
        cache,
        robust_grid_parameters.constrain,
        robust_grid_parameters,
        policy.separator.gap_search,
        policy.separator.profile,
        policy.separator.enhanced,
    )
    return _gap_refinement_result(
        ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY,
        promotion.gaps,
        promotion.detail,
    )


def nearby_separator_refinement_skip_reason(strip_mode: str, enabled: bool) -> Optional[str]:
    if strip_mode != "full":
        return "not_full_strip"
    if not enabled:
        return "disabled"
    return None


def apply_nearby_separator_refinement(
    profile: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    policy: DetectionPolicy,
) -> GapRefinementResult:
    skip_reason = nearby_separator_refinement_skip_reason(
        strip_mode,
        policy.separator.nearby_refinement.enabled,
    )
    if skip_reason is not None:
        return _skipped_gap_refinement_result(NEARBY_SEPARATOR_REFINEMENT_FAMILY, gaps, skip_reason)
    pre_nearby_gaps = list(gaps)
    refinement = refine_nearby_separator_gaps(
        profile,
        gaps,
        origin,
        pitch,
        count,
        policy.separator.nearby_refinement,
    )
    refined_gaps = refinement.gaps
    detail = refinement.detail
    if int(detail.get("accepted_count", 0) or 0) > 0:
        return _gap_refinement_result(
            NEARBY_SEPARATOR_REFINEMENT_FAMILY,
            refined_gaps,
            detail,
            pre_refinement_gaps=pre_nearby_gaps,
        )
    return _gap_refinement_result(
        NEARBY_SEPARATOR_REFINEMENT_FAMILY,
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
    geometry_equal_model_selected: bool,
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
        geometry_equal_model_selected,
        cache,
        policy,
    )
    nearby_refinement = apply_nearby_separator_refinement(
        profile,
        enhanced_gap_promotion.gaps,
        count,
        strip_mode,
        origin,
        pitch,
        policy,
    )
    return LateSeparatorRefinementResult(
        gaps=nearby_refinement.gaps,
        enhanced_gap_promotion_detail=enhanced_gap_promotion.detail,
        nearby_refinement_detail=nearby_refinement.detail,
        pre_nearby_gaps=nearby_refinement.pre_refinement_gaps,
    )


__all__ = [
    "EDGE_PAIR_REFINEMENT_FAMILY",
    "ENHANCED_GAP_PROMOTION_REFINEMENT_FAMILY",
    "GapRefinementResult",
    "LATE_REFINEMENT_PENDING_REASON",
    "LateSeparatorRefinementResult",
    "NEARBY_SEPARATOR_REFINEMENT_FAMILY",
    "PrimarySeparatorRefinementResult",
    "apply_edge_pair_refinement",
    "apply_enhanced_gap_promotion",
    "apply_late_separator_refinement_chain",
    "apply_nearby_separator_refinement",
    "apply_primary_separator_refinements",
    "edge_pair_refinement_skip_reason",
    "enhanced_gap_promotion_skip_reason",
    "gap_geometry_parameters_for_strip_mode",
    "nearby_separator_refinement_skip_reason",
    "pending_gap_refinement_detail",
    "robust_grid_execution_parameters_for_strip_mode",
]
