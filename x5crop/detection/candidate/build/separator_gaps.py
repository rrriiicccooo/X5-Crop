from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....domain import Box, Gap
from ....formats import FormatSpec
from ....cache.separator import cached_separator_profile
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ..proposal.separator.hints import SeparatorGapHintSet
from .separator_refinements import (
    NEARBY_SEPARATOR_REFINEMENT_FAMILY,
    apply_late_separator_refinement_chain,
    apply_primary_separator_refinements,
    pending_gap_refinement_detail,
)
from .separator_sources import (
    initial_separator_gaps,
    model_gap_proposal_detail,
    standard_separator_gap_result,
    with_model_gap_proposal_detail,
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
    nearby_refinement_detail: dict[str, Any]
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


def build_primary_separator_gaps_for_outer(
    gray_work: np.ndarray,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    cache: Optional[AnalysisCache],
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
    *,
    explicit_count: bool,
    force_standard_gap_search: bool = False,
    gap_hints: Optional[SeparatorGapHintSet] = None,
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
            fmt,
            outer,
            profile,
            count,
            origin,
            pitch,
            gap_max_width_ratio_override,
            policy,
            forced=True,
            gap_hints=gap_hints,
        )
        model_detail = model_gap_proposal_detail(
            initial_gaps,
            fmt,
            count,
            strip_mode,
            gap_max_width_ratio_override,
            policy,
        )
        model_detail["available"] = False
        model_detail["reason"] = "forced_standard_gap_search"
        initial_gaps = with_model_gap_proposal_detail(initial_gaps, model_detail)
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
        explicit_count,
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
        nearby_refinement_detail=pending_gap_refinement_detail(NEARBY_SEPARATOR_REFINEMENT_FAMILY),
        pre_nearby_gaps=None,
    )


def apply_late_separator_refinements(
    count: int,
    strip_mode: str,
    separator_gaps: SeparatorGapBuildResult,
    policy: DetectionPolicy,
    *,
    explicit_count: bool,
) -> SeparatorGapBuildResult:
    late_refinement = apply_late_separator_refinement_chain(
        count,
        strip_mode,
        explicit_count,
        separator_gaps.profile,
        separator_gaps.gaps,
        separator_gaps.origin,
        separator_gaps.pitch,
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
        nearby_refinement_detail=late_refinement.nearby_refinement_detail,
        pre_nearby_gaps=late_refinement.pre_nearby_gaps,
    )

__all__ = [
    "SeparatorGapBuildResult",
    "apply_late_separator_refinements",
    "build_primary_separator_gaps_for_outer",
    "separator_origin_pitch",
]
