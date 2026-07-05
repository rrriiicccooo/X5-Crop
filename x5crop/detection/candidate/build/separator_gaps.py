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
from ....runtime.config import RuntimeConfig
from ...gap_profiles import BROAD_WIDTH_GAP_PROFILE
from ..proposal.separator.model import propose_equal_model_gaps_from_profile
from ..proposal.separator.proposal import propose_separator_width_profile_gaps, propose_standard_separator_gaps


@dataclass(frozen=True)
class SeparatorGapBuildResult:
    outer: Box
    profile: np.ndarray
    origin: float
    pitch: float
    gaps: list[Gap]
    grid_detail: dict[str, Any]
    edge_pair_correction_detail: dict[str, Any]
    enhanced_gap_promotion_detail: dict[str, Any]
    nearby_correction_detail: dict[str, Any]
    pre_nearby_gaps: Optional[list[Gap]]


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
) -> list[Gap]:
    gaps = propose_standard_separator_gaps(
        profile,
        origin,
        pitch,
        count,
        gap_max_width_ratio_override,
        policy.separator.gap_search,
    )
    if candidate_strategy == "separator_outer" and gap_search_profile == BROAD_WIDTH_GAP_PROFILE:
        separator_width_profile_gaps = propose_separator_width_profile_gaps(
            gray_work,
            outer,
            count,
            policy.separator.width_profile,
        )
        if len(separator_width_profile_gaps) >= max(1, count - 1):
            gaps = separator_width_profile_gaps
    if (
        strip_mode == "full"
        and policy.separator.geometry_support.detected_geometry.enabled
        and count == fmt.default_count
        and gap_max_width_ratio_override is None
    ):
        gaps = propose_equal_model_gaps_from_profile(profile, origin, pitch, count)
    return gaps


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
) -> tuple[list[Gap], dict[str, Any], dict[str, Any]]:
    edge_pair_correction_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    if strip_mode == "full" and count > 1:
        edge, background, _activity = cached_edge_refine_profiles(
            cache,
            crop,
            outer,
            policy.separator.edge_refine_profile,
        )
        gaps, edge_pair_correction_detail = refine_gaps_with_edge_profiles(
            edge,
            background,
            gaps,
            count,
            policy.separator.edge_pair,
        )
    gaps, grid_detail = apply_robust_grid(
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
    return gaps, edge_pair_correction_detail, grid_detail


def apply_enhanced_gap_promotion(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    allow_enhanced_gap_promotion: bool,
    config: RuntimeConfig,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> tuple[list[Gap], dict[str, Any]]:
    detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    promotion_allowed = (
        allow_enhanced_gap_promotion
        and strip_mode == "full"
        and not policy.separator.geometry_support.detected_geometry.enabled
    )
    if not promotion_allowed:
        return gaps, detail
    if should_run_enhanced_gap_promotion(config.analysis, gaps, count, policy.separator.enhanced):
        return promote_enhanced_separator_gaps(
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
    if config.analysis == "auto":
        detail = {"used": False, "reason": "auto_not_needed"}
    return gaps, detail


def apply_nearby_separator_refinement(
    profile: np.ndarray,
    gaps: list[Gap],
    count: int,
    strip_mode: str,
    origin: float,
    pitch: float,
    policy: DetectionPolicy,
) -> tuple[list[Gap], dict[str, Any], Optional[list[Gap]]]:
    detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    if strip_mode != "full" or not policy.separator.nearby_correction.enabled:
        return gaps, detail, None
    pre_nearby_gaps = list(gaps)
    refined_gaps, detail = apply_nearby_separator_corrections(
        profile,
        gaps,
        origin,
        pitch,
        count,
        strip_mode,
        policy.separator.nearby_correction,
    )
    if int(detail.get("accepted_count", 0) or 0) > 0:
        return refined_gaps, detail, pre_nearby_gaps
    return refined_gaps, detail, None


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
        gaps = propose_standard_separator_gaps(
            profile,
            origin,
            pitch,
            count,
            gap_max_width_ratio_override,
            policy.separator.gap_search,
        )
    else:
        gaps = initial_separator_gaps(
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
    gaps, edge_pair_correction_detail, grid_detail = apply_primary_separator_refinements(
        gray_work,
        outer,
        crop,
        profile,
        gaps,
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
        gaps=gaps,
        grid_detail=grid_detail,
        edge_pair_correction_detail=edge_pair_correction_detail,
        enhanced_gap_promotion_detail={"used": False, "reason": "pending_late_refinement"},
        nearby_correction_detail={"used": False, "reason": "pending_late_refinement"},
        pre_nearby_gaps=None,
    )


def apply_late_separator_refinements(
    gray_work: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    separator_gaps: SeparatorGapBuildResult,
    allow_enhanced_gap_promotion: bool,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> SeparatorGapBuildResult:
    gaps, enhanced_gap_promotion_detail = apply_enhanced_gap_promotion(
        gray_work,
        separator_gaps.outer,
        separator_gaps.gaps,
        fmt,
        count,
        strip_mode,
        separator_gaps.origin,
        separator_gaps.pitch,
        allow_enhanced_gap_promotion,
        config,
        cache,
        policy,
    )
    gaps, nearby_correction_detail, pre_nearby_gaps = apply_nearby_separator_refinement(
        separator_gaps.profile,
        gaps,
        count,
        strip_mode,
        separator_gaps.origin,
        separator_gaps.pitch,
        policy,
    )
    return SeparatorGapBuildResult(
        outer=separator_gaps.outer,
        profile=separator_gaps.profile,
        origin=separator_gaps.origin,
        pitch=separator_gaps.pitch,
        gaps=gaps,
        grid_detail=separator_gaps.grid_detail,
        edge_pair_correction_detail=separator_gaps.edge_pair_correction_detail,
        enhanced_gap_promotion_detail=enhanced_gap_promotion_detail,
        nearby_correction_detail=nearby_correction_detail,
        pre_nearby_gaps=pre_nearby_gaps,
    )


def build_separator_gaps_for_outer(
    gray_work: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    candidate_strategy: str,
    allow_enhanced_gap_promotion: bool,
    cache: Optional[AnalysisCache],
    gap_max_width_ratio_override: Optional[float],
    gap_search_profile: str,
    policy: DetectionPolicy,
) -> SeparatorGapBuildResult:
    primary = build_primary_separator_gaps_for_outer(
        gray_work,
        fmt,
        count,
        strip_mode,
        outer,
        offset_fraction,
        candidate_strategy,
        cache,
        gap_max_width_ratio_override,
        gap_search_profile,
        policy,
    )
    return apply_late_separator_refinements(
        gray_work,
        config,
        fmt,
        count,
        strip_mode,
        primary,
        allow_enhanced_gap_promotion,
        cache,
        policy,
    )


__all__ = [
    "SeparatorGapBuildResult",
    "apply_enhanced_gap_promotion",
    "apply_late_separator_refinements",
    "apply_nearby_separator_refinement",
    "apply_primary_separator_refinements",
    "build_primary_separator_gaps_for_outer",
    "build_separator_gaps_for_outer",
    "initial_separator_gaps",
    "separator_origin_pitch",
]
