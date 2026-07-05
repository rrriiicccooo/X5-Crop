from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, Gap
from ....formats import FormatSpec
from ....geometry.separator_cache import cached_edge_refine_profiles, cached_separator_profile
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...gap_profiles import BROAD_WIDTH_GAP_PROFILE
from ..proposal.outer.grid_refine import grid_refined_outer_box
from ..proposal.separator.proposal import propose_separator_width_profile_gaps, propose_standard_separator_gaps
from ..proposal.separator.refinement import (
    apply_grid_gap_model,
    promote_enhanced_separator_gaps_for_candidate,
    refine_with_edge_profiles,
    refine_with_nearby_separator,
    should_run_enhanced_gap_promotion_for_candidate,
)


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
        gaps = [
            Gap(i, origin + pitch * i, float(profile[min(len(profile) - 1, max(0, int(round(origin + pitch * i))))]), "equal")
            for i in range(1, count)
        ]
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
        gaps, edge_pair_correction_detail = refine_with_edge_profiles(
            edge,
            background,
            gaps,
            count,
            policy.separator.edge_pair,
        )
    gaps, grid_detail = apply_grid_gap_model(
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
    if should_run_enhanced_gap_promotion_for_candidate(config.analysis, gaps, count, policy.separator.enhanced):
        return promote_enhanced_separator_gaps_for_candidate(
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
    refined_gaps, detail = refine_with_nearby_separator(
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
    allow_outer_refine: bool,
    gap_max_width_ratio_override: Optional[float],
    gap_search_profile: str,
    policy: DetectionPolicy,
) -> SeparatorGapBuildResult:
    work_height, work_width = gray_work.shape
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0:
        outer = Box(0, 0, work_width, work_height)
        crop = gray_work
    profile = cached_separator_profile(cache, gray_work, outer, policy.separator.profile)
    origin, pitch = separator_origin_pitch(outer, fmt, count, strip_mode, offset_fraction)
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
    if allow_outer_refine and strip_mode == "full":
        refined_outer = grid_refined_outer_box(
            outer,
            grid_detail,
            count,
            pitch,
            work_width,
            policy.outer.proposal.geometry.grid_refine,
        )
        if refined_outer is not None:
            outer = refined_outer
            crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
            profile = cached_separator_profile(cache, gray_work, outer, policy.separator.profile)
            origin, pitch = separator_origin_pitch(outer, fmt, count, strip_mode, offset_fraction)
            gaps = propose_standard_separator_gaps(
                profile,
                origin,
                pitch,
                count,
                gap_max_width_ratio_override,
                policy.separator.gap_search,
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
            grid_detail["outer_refined"] = True
    gaps, enhanced_gap_promotion_detail = apply_enhanced_gap_promotion(
        gray_work,
        outer,
        gaps,
        fmt,
        count,
        strip_mode,
        origin,
        pitch,
        allow_enhanced_gap_promotion,
        config,
        cache,
        policy,
    )
    gaps, nearby_correction_detail, pre_nearby_gaps = apply_nearby_separator_refinement(
        profile,
        gaps,
        count,
        strip_mode,
        origin,
        pitch,
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
        enhanced_gap_promotion_detail=enhanced_gap_promotion_detail,
        nearby_correction_detail=nearby_correction_detail,
        pre_nearby_gaps=pre_nearby_gaps,
    )


__all__ = [
    "SeparatorGapBuildResult",
    "apply_enhanced_gap_promotion",
    "apply_nearby_separator_refinement",
    "apply_primary_separator_refinements",
    "build_separator_gaps_for_outer",
    "initial_separator_gaps",
    "separator_origin_pitch",
]
