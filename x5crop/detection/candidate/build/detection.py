from __future__ import annotations

from dataclasses import asdict, replace
from typing import Optional

import numpy as np

from ....domain import Box, Detection
from ....formats import FormatSpec
from ....geometry.boxes import map_work_box
from ....geometry.frame_fit import fit_frame_boxes_from_gaps
from ....geometry.layout import work_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...evidence.separator_width import separator_width_evidence_detail
from ...gap_profiles import WIDTH_AWARE_GAP_PROFILE
from ...physical.outer.grid_refine import grid_refined_outer_box
from ...physical.outer.plan import outer_candidate_strategy
from ...physical.separator.hints import SeparatorGapHintSet
from .partial_edge import partial_edge_hint
from .separator_gaps import (
    SeparatorGapBuildResult,
    apply_late_separator_refinements,
    build_primary_separator_gaps_for_outer,
)


def build_detection_for_outer(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float = 0.0,
    outer_candidate_name: str = "unknown",
    outer_candidate_strategy_name: str | None = None,
    cache: Optional[AnalysisCache] = None,
    allow_outer_refine: bool = True,
    gap_max_width_ratio_override: Optional[float] = None,
    gap_search_profile: str = WIDTH_AWARE_GAP_PROFILE,
    separator_gap_hints: Optional[SeparatorGapHintSet] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    if gap_search_profile != WIDTH_AWARE_GAP_PROFILE:
        raise ValueError(f"Unsupported separator gap search profile: {gap_search_profile!r}")
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    candidate_strategy = outer_candidate_strategy_name or outer_candidate_strategy(outer_candidate_name)
    h, w = gray.shape
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    separator_gaps = _build_separator_gap_lifecycle(
        gray_work,
        config,
        fmt,
        count,
        strip_mode,
        outer,
        offset_fraction,
        cache,
        allow_outer_refine,
        gap_max_width_ratio_override,
        policy,
        ww,
        explicit_count=bool(config.count_override is not None),
        gap_hints=separator_gap_hints,
    )
    outer = separator_gaps.outer
    profile = separator_gaps.profile
    origin = separator_gaps.origin
    pitch = separator_gaps.pitch
    gaps = separator_gaps.gaps
    boxes_work, frame_size_detail = fit_frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        ww,
        wh,
        config.bleed_x,
        config.bleed_y,
        origin=origin,
        pitch=pitch,
        frame_fit=policy.frame_fit,
    )
    boxes = [map_work_box(box, config.layout, w, h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, w, h)
    separator_width_evidence = separator_width_evidence_detail(
        gaps,
        float(outer.height),
        float(policy.partial_holder.broad_separator_width_min_ratio),
        max(
            int(policy.partial_holder.requires_broad_separator_width_gaps),
            int(policy.separator.gate.min_broad_separator_width_gaps_for_auto),
        ),
    )
    detail: dict[str, object] = {}
    detail.update(
        {
            "candidate_build": {
                "owner": "candidate.build",
                "role": "physical_detection_geometry",
                "base_scoring_applied": False,
            },
            "candidate_count": count,
            "offset_fraction": float(offset_fraction),
            "origin": float(origin),
            "pitch": float(pitch),
            "layout": config.layout,
            "outer_candidate": outer_candidate_name,
            "outer_candidate_strategy": candidate_strategy,
            "work_outer": asdict(outer),
            "work_frame_boxes": [asdict(box) for box in boxes_work],
            "grid": separator_gaps.grid_detail,
            "grid_residual": separator_gaps.grid_detail.get("grid_residual"),
            "grid_used": bool(separator_gaps.grid_detail.get("grid_used", False)),
            "standard_gap_search": separator_gaps.standard_gap_search_detail,
            "separator_width_profile_gap_search": separator_gaps.separator_width_profile_gap_search_detail,
            "separator_gap_hints": (
                separator_gap_hints.summary()
                if separator_gap_hints is not None
                else {"used": False, "reason": "no_gap_hints"}
            ),
            "edge_pair_correction": separator_gaps.edge_pair_correction_detail,
            "frame_size_fit": frame_size_detail,
            "nearby_separator_refinement": separator_gaps.nearby_refinement_detail,
            "separator_width_evidence": separator_width_evidence,
            "broad_separator_width_gaps": int(separator_width_evidence.get("broad_separator_width_gaps", 0) or 0),
            "broad_separator_width_gap_indexes": list(separator_width_evidence.get("broad_separator_width_gap_indexes", [])),
            "separator_width_min_px": float(separator_width_evidence.get("separator_width_min_px", 0.0) or 0.0),
            "gap_max_width_ratio_override": gap_max_width_ratio_override,
            "gap_search_profile_id": str(gap_search_profile),
            "partial_edge_hint": partial_edge_hint(profile, origin, pitch, count, policy.partial_edge_hint) if strip_mode == "partial" else {},
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
        }
    )
    if separator_gaps.pre_nearby_gaps is not None:
        detail["pre_nearby_gaps"] = [asdict(gap) for gap in separator_gaps.pre_nearby_gaps]
    return Detection(fmt.name, config.layout, strip_mode, count, outer_original, boxes, gaps, 0.0, [], detail)


def _build_separator_gap_lifecycle(
    gray_work: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    cache: Optional[AnalysisCache],
    allow_outer_refine: bool,
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
    work_width: int,
    *,
    explicit_count: bool,
    gap_hints: Optional[SeparatorGapHintSet] = None,
) -> SeparatorGapBuildResult:
    separator_gaps = build_primary_separator_gaps_for_outer(
        gray_work,
        fmt,
        count,
        strip_mode,
        outer,
        offset_fraction,
        cache,
        gap_max_width_ratio_override,
        policy,
        explicit_count=explicit_count,
        gap_hints=gap_hints,
    )
    if not allow_outer_refine or strip_mode != "full":
        return apply_late_separator_refinements(
            count,
            strip_mode,
            separator_gaps,
            policy,
            explicit_count=explicit_count,
        )

    refined_outer = grid_refined_outer_box(
        separator_gaps.outer,
        separator_gaps.grid_detail,
        count,
        separator_gaps.pitch,
        work_width,
        policy.outer.proposal.geometry.grid_refine,
    )
    if refined_outer is None:
        return apply_late_separator_refinements(
            count,
            strip_mode,
            separator_gaps,
            policy,
            explicit_count=explicit_count,
        )

    refined_separator_gaps = build_primary_separator_gaps_for_outer(
        gray_work,
        fmt,
        count,
        strip_mode,
        refined_outer,
        offset_fraction,
        cache,
        gap_max_width_ratio_override,
        policy,
        explicit_count=explicit_count,
        force_standard_gap_search=True,
        gap_hints=gap_hints,
    )
    grid_detail = dict(refined_separator_gaps.grid_detail)
    grid_detail["outer_refined"] = True
    refined_separator_gaps = replace(refined_separator_gaps, grid_detail=grid_detail)
    return apply_late_separator_refinements(
        count,
        strip_mode,
        refined_separator_gaps,
        policy,
        explicit_count=explicit_count,
    )
