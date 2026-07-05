from __future__ import annotations

from dataclasses import asdict, replace
from typing import Optional

import numpy as np

from ....domain import Box, Detection
from ....formats import FormatSpec
from ....geometry.boxes import map_work_box
from ....geometry.frame_fit import fit_frame_boxes_from_gaps, frame_boxes_from_gaps
from ....geometry.layout import work_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...gap_profiles import STANDARD_GAP_PROFILE
from ..proposal.separator.evidence import separator_width_evidence_detail
from ..assessment.partial_edge import partial_edge_hint
from ..assessment.scoring import score_detection
from ..proposal.outer.grid_refine import grid_refined_outer_box
from ..proposal.outer.plan import outer_candidate_strategy
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
    allow_enhanced_gap_promotion: bool = True,
    cache: Optional[AnalysisCache] = None,
    allow_outer_refine: bool = True,
    gap_max_width_ratio_override: Optional[float] = None,
    gap_search_profile: str = STANDARD_GAP_PROFILE,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
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
        candidate_strategy,
        allow_enhanced_gap_promotion,
        cache,
        allow_outer_refine,
        gap_max_width_ratio_override,
        gap_search_profile,
        policy,
        ww,
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
    score_boxes_work = frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        ww,
        wh,
        config.bleed_x,
        config.bleed_y,
        origin=origin,
        pitch=pitch,
        apply_geometry_fit=policy.frame_fit.geometry_fallback,
        geometry_config=policy.frame_fit,
    )
    boxes = [map_work_box(box, config.layout, w, h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, w, h)
    confidence, reasons, detail = score_detection(gray_work, outer, gaps, boxes_work, count, fmt, strip_mode, policy)
    separator_width_evidence = separator_width_evidence_detail(
        gaps,
        float(outer.height),
        float(policy.partial_holder.broad_separator_width_min_ratio),
        max(
            int(policy.partial_holder.requires_broad_separator_width_gaps),
            int(policy.separator.gate.min_broad_separator_width_gaps_for_auto),
        ),
    )
    pre_nearby_confidence = None
    if separator_gaps.pre_nearby_gaps is not None:
        pre_nearby_boxes_work = frame_boxes_from_gaps(
            outer,
            separator_gaps.pre_nearby_gaps,
            count,
            ww,
            wh,
            config.bleed_x,
            config.bleed_y,
            origin=origin,
            pitch=pitch,
        )
        pre_nearby_confidence, _pre_nearby_reasons, _pre_nearby_detail = score_detection(
            gray_work,
            outer,
            separator_gaps.pre_nearby_gaps,
            pre_nearby_boxes_work,
            count,
            fmt,
            strip_mode,
            policy,
        )
        geometry_confidence, _geometry_reasons, _geometry_detail = score_detection(
            gray_work,
            outer,
            gaps,
            score_boxes_work,
            count,
            fmt,
            strip_mode,
            policy,
        )
        confidence = min(confidence, geometry_confidence)
    detail.update(
        {
            "candidate_count": count,
            "offset_fraction": float(offset_fraction),
            "origin": float(origin),
            "pitch": float(pitch),
            "layout": config.layout,
            "outer_candidate": outer_candidate_name,
            "outer_candidate_strategy": candidate_strategy,
            "work_outer": asdict(outer),
            "grid": separator_gaps.grid_detail,
            "grid_residual": separator_gaps.grid_detail.get("grid_residual"),
            "grid_used": bool(separator_gaps.grid_detail.get("grid_used", False)),
            "edge_pair_correction": separator_gaps.edge_pair_correction_detail,
            "frame_size_fit": frame_size_detail,
            "enhanced_gap_promotion": separator_gaps.enhanced_gap_promotion_detail,
            "nearby_separator_correction": separator_gaps.nearby_correction_detail,
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
    if pre_nearby_confidence is not None:
        detail["nearby_separator_correction_confidence_cap"] = float(pre_nearby_confidence)
    return Detection(fmt.name, config.layout, strip_mode, count, outer_original, boxes, gaps, confidence, reasons, detail)


def _build_separator_gap_lifecycle(
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
    work_width: int,
) -> SeparatorGapBuildResult:
    separator_gaps = build_primary_separator_gaps_for_outer(
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
    if not allow_outer_refine or strip_mode != "full":
        return apply_late_separator_refinements(
            gray_work,
            config,
            fmt,
            count,
            strip_mode,
            separator_gaps,
            allow_enhanced_gap_promotion,
            cache,
            policy,
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
            gray_work,
            config,
            fmt,
            count,
            strip_mode,
            separator_gaps,
            allow_enhanced_gap_promotion,
            cache,
            policy,
        )

    refined_separator_gaps = build_primary_separator_gaps_for_outer(
        gray_work,
        fmt,
        count,
        strip_mode,
        refined_outer,
        offset_fraction,
        candidate_strategy,
        cache,
        gap_max_width_ratio_override,
        gap_search_profile,
        policy,
        force_standard_gap_search=True,
    )
    grid_detail = dict(refined_separator_gaps.grid_detail)
    grid_detail["outer_refined"] = True
    refined_separator_gaps = replace(refined_separator_gaps, grid_detail=grid_detail)
    return apply_late_separator_refinements(
        gray_work,
        config,
        fmt,
        count,
        strip_mode,
        refined_separator_gaps,
        allow_enhanced_gap_promotion,
        cache,
        policy,
    )
