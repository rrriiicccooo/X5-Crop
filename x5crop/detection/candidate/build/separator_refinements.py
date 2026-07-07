from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....cache import AnalysisCache
from ....cache.separator import cached_edge_refine_profiles
from ....domain import Box, Gap
from ....geometry.detection_parameters import (
    GapGeometryConstraintParameters,
    RobustGridExecutionParameters,
    RobustGridParameters,
)
from ....geometry.edge_pairs import refine_gaps_with_edge_profiles
from ....geometry.nearby_separator import apply_nearby_separator_refinement as refine_nearby_separator_gaps
from ....geometry.robust_grid import apply_robust_grid
from ....policies.runtime.policy import DetectionPolicy
from ....policies.runtime.separator import SeparatorRefinementFamilyPolicy


EDGE_PAIR_REFINEMENT_FAMILY = "edge_pair"
NEARBY_SEPARATOR_REFINEMENT_FAMILY = "nearby_separator_refinement"
NEARBY_REFINEMENT_PENDING_REASON = "pending_nearby_separator_refinement"


@dataclass(frozen=True)
class PrimarySeparatorRefinementResult:
    gaps: list[Gap]
    edge_pair_correction_detail: dict[str, Any]
    grid_detail: dict[str, Any]


@dataclass(frozen=True)
class NearbySeparatorRefinementChainResult:
    gaps: list[Gap]
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
    family_policy: Optional[SeparatorRefinementFamilyPolicy] = None,
    *,
    eligible: Optional[bool] = None,
    skipped_reason: Optional[str] = None,
) -> dict[str, Any]:
    result_detail = dict(detail)
    result_detail.setdefault("family", family)
    if family_policy is not None:
        result_detail.setdefault("phase", family_policy.phase)
        result_detail.setdefault("mode", family_policy.mode)
        result_detail.setdefault("strip_modes", list(family_policy.strip_modes))
        result_detail.setdefault(
            "requires_explicit_count_for_partial",
            bool(family_policy.requires_explicit_count_for_partial),
        )
        result_detail.setdefault("target_gap_methods", list(family_policy.target_gap_methods))
        if family_policy.model_promotion_gap_methods:
            result_detail.setdefault(
                "model_promotion_gap_methods",
                list(family_policy.model_promotion_gap_methods),
            )
            result_detail.setdefault(
                "evidence_roles",
                {
                    "hard_gap_refresh": list(family_policy.target_gap_methods),
                    "model_gap_promotion": list(family_policy.model_promotion_gap_methods),
                },
            )
    if eligible is not None:
        result_detail.setdefault("eligible", bool(eligible))
    if skipped_reason is not None:
        result_detail.setdefault("skipped_reason", skipped_reason)
        result_detail.setdefault("reason", skipped_reason)
    if "accepted" in result_detail:
        result_detail.setdefault("accepted_count", len(result_detail.get("accepted") or []))
    if "rejected" in result_detail:
        result_detail.setdefault("rejected_count", len(result_detail.get("rejected") or []))
    return result_detail


def _gap_refinement_result(
    family: str,
    gaps: list[Gap],
    detail: dict[str, Any],
    *,
    family_policy: Optional[SeparatorRefinementFamilyPolicy] = None,
    eligible: bool = True,
    skipped_reason: Optional[str] = None,
    pre_refinement_gaps: Optional[list[Gap]] = None,
) -> GapRefinementResult:
    return GapRefinementResult(
        family=family,
        gaps=gaps,
        detail=_gap_refinement_detail(
            family,
            detail,
            family_policy,
            eligible=eligible,
            skipped_reason=skipped_reason,
        ),
        pre_refinement_gaps=pre_refinement_gaps,
    )


def _skipped_gap_refinement_result(
    family: str,
    gaps: list[Gap],
    reason: str,
    *,
    family_policy: Optional[SeparatorRefinementFamilyPolicy] = None,
    eligible: bool = False,
) -> GapRefinementResult:
    return _gap_refinement_result(
        family,
        gaps,
        {"used": False, "reason": reason},
        family_policy=family_policy,
        eligible=eligible,
        skipped_reason=reason,
    )


def pending_gap_refinement_detail(family: str) -> dict[str, Any]:
    return _gap_refinement_detail(
        family,
        {"used": False, "reason": NEARBY_REFINEMENT_PENDING_REASON},
        eligible=False,
        skipped_reason=NEARBY_REFINEMENT_PENDING_REASON,
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


def edge_pair_refinement_skip_reason(
    count: int,
    strip_mode: str,
    explicit_count: bool,
    family_policy: SeparatorRefinementFamilyPolicy,
) -> Optional[str]:
    family_block_reason = family_policy.block_reason(strip_mode, explicit_count)
    if family_block_reason is not None:
        return family_block_reason
    if count <= 1:
        return "single_frame"
    return None


def apply_edge_pair_refinement(
    outer: Box,
    crop: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    explicit_count: bool,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> GapRefinementResult:
    family_policy = policy.separator.refinement.edge_pair
    skip_reason = edge_pair_refinement_skip_reason(count, strip_mode, explicit_count, family_policy)
    if skip_reason is not None:
        return _skipped_gap_refinement_result(
            EDGE_PAIR_REFINEMENT_FAMILY,
            gaps,
            skip_reason,
            family_policy=family_policy,
        )
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
        family_policy=family_policy,
    )


def apply_primary_separator_refinements(
    gray_work: np.ndarray,
    outer: Box,
    crop: np.ndarray,
    profile: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    explicit_count: bool,
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
        explicit_count,
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


def nearby_separator_refinement_skip_reason(
    strip_mode: str,
    explicit_count: bool,
    enabled: bool,
    family_policy: SeparatorRefinementFamilyPolicy,
) -> Optional[str]:
    family_block_reason = family_policy.block_reason(strip_mode, explicit_count)
    if family_block_reason is not None:
        return family_block_reason
    if not enabled:
        return "disabled"
    return None


def apply_nearby_separator_refinement(
    profile: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    explicit_count: bool,
    origin: float,
    pitch: float,
    policy: DetectionPolicy,
) -> GapRefinementResult:
    family_policy = policy.separator.refinement.nearby
    skip_reason = nearby_separator_refinement_skip_reason(
        strip_mode,
        explicit_count,
        policy.separator.nearby_refinement.enabled,
        family_policy,
    )
    if skip_reason is not None:
        return _skipped_gap_refinement_result(
            NEARBY_SEPARATOR_REFINEMENT_FAMILY,
            gaps,
            skip_reason,
            family_policy=family_policy,
        )
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
            family_policy=family_policy,
            pre_refinement_gaps=pre_nearby_gaps,
        )
    return _gap_refinement_result(
        NEARBY_SEPARATOR_REFINEMENT_FAMILY,
        refined_gaps,
        detail,
        family_policy=family_policy,
    )


def apply_nearby_separator_refinement_chain(
    count: int,
    strip_mode: str,
    explicit_count: bool,
    profile: np.ndarray,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    policy: DetectionPolicy,
) -> NearbySeparatorRefinementChainResult:
    nearby_refinement = apply_nearby_separator_refinement(
        profile,
        gaps,
        count,
        strip_mode,
        explicit_count,
        origin,
        pitch,
        policy,
    )
    return NearbySeparatorRefinementChainResult(
        gaps=nearby_refinement.gaps,
        nearby_refinement_detail=nearby_refinement.detail,
        pre_nearby_gaps=nearby_refinement.pre_refinement_gaps,
    )


__all__ = [
    "EDGE_PAIR_REFINEMENT_FAMILY",
    "GapRefinementResult",
    "NEARBY_SEPARATOR_REFINEMENT_FAMILY",
    "NEARBY_REFINEMENT_PENDING_REASON",
    "NearbySeparatorRefinementChainResult",
    "PrimarySeparatorRefinementResult",
    "apply_edge_pair_refinement",
    "apply_nearby_separator_refinement_chain",
    "apply_nearby_separator_refinement",
    "apply_primary_separator_refinements",
    "edge_pair_refinement_skip_reason",
    "gap_geometry_parameters_for_strip_mode",
    "nearby_separator_refinement_skip_reason",
    "pending_gap_refinement_detail",
    "robust_grid_execution_parameters_for_strip_mode",
]
