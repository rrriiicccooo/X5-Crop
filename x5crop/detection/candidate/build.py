from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ...runtime_config import RuntimeConfig
from ...domain import Box, Detection, Gap
from ...formats import FormatSpec
from ...geometry.boxes import map_work_box
from ...geometry.edge_pairs import refine_gaps_by_edge_pairs
from ...geometry.enhanced_separator import (
    merge_enhanced_separator_gaps,
    should_run_enhanced_separator_analysis,
)
from ...geometry.frame_fit import fit_frame_boxes_from_gaps, frame_boxes_from_gaps
from ...geometry.gap_search import find_gap
from ...geometry.layout import work_gray
from ...geometry.nearby_separator import apply_nearby_separator_corrections
from ...geometry.robust_grid import apply_robust_grid
from ...geometry.separator_cache import cached_separator_profile
from ...policies.runtime_policy import DetectionPolicy
from ...policies.registry import get_detection_policy
from ...runtime import AnalysisCache
from ...utils import clamp_int
from ..outer.plan import outer_candidate_strategy
from .partial import partial_edge_hint
from .scoring import score_detection
from ..evidence.separator import dark_band_gaps_for_outer


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
    allow_separator_analysis: bool = True,
    cache: Optional[AnalysisCache] = None,
    allow_outer_refine: bool = True,
    gap_max_width_ratio_override: Optional[float] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    candidate_strategy = outer_candidate_strategy_name or outer_candidate_strategy(outer_candidate_name)
    h, w = gray.shape
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0:
        outer = Box(0, 0, ww, wh)
        crop = gray_work
    profile = cached_separator_profile(cache, gray_work, outer, fmt.name, policy.separator.profile)
    if strip_mode == "partial" and count < fmt.default_count:
        pitch = outer.width / float(max(1, fmt.default_count))
        total_width = pitch * count
        origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
    else:
        pitch = outer.width / float(max(1, count))
        origin = 0.0
    gaps = [
        find_gap(
            profile,
            origin + pitch * i,
            pitch,
            i,
            fmt.name,
            gap_max_width_ratio_override,
            policy.separator.gap_search,
        )
        for i in range(1, count)
    ]
    if candidate_strategy == "dark_band_outer":
        dark_band_gaps = dark_band_gaps_for_outer(gray_work, outer, count, fmt, policy)
        if len(dark_band_gaps) >= max(1, count - 1):
            gaps = dark_band_gaps
    if (
        strip_mode == "full"
        and policy.separator.geometry_support.wide_geometry.enabled
        and count == fmt.default_count
        and gap_max_width_ratio_override is None
    ):
        gaps = [
            Gap(i, origin + pitch * i, float(profile[min(len(profile) - 1, max(0, int(round(origin + pitch * i))))]), "equal")
            for i in range(1, count)
        ]
    edge_refine_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    if strip_mode == "full" and count > 1:
        gaps, edge_refine_detail = refine_gaps_by_edge_pairs(
            crop,
            gaps,
            count,
            fmt.name,
            cache,
            outer,
            policy.separator.edge_pair,
            policy.separator.edge_refine_profile,
        )
    gaps, grid_detail = apply_robust_grid(
        gaps,
        origin,
        pitch,
        strip_mode,
        fmt.name,
        profile,
        gray_work,
        outer,
        policy.separator.hard_gap_trust,
        policy.separator.nearby_correction,
        policy.separator.robust_grid,
    )
    if allow_outer_refine and strip_mode == "full" and bool(grid_detail.get("grid_used", False)):
        grid_refine = policy.outer.grid_refine
        model_origin = float(grid_detail.get("grid_origin", 0.0))
        model_pitch = float(grid_detail.get("grid_pitch", pitch))
        proposed_left = int(round(outer.left + model_origin))
        proposed_right = int(round(outer.left + model_origin + model_pitch * count))
        max_shift = clamp_int(pitch * grid_refine.shift_ratio, grid_refine.shift_min, grid_refine.shift_max)
        width_change = abs((proposed_right - proposed_left) - outer.width) / max(1.0, float(outer.width))
        if (
            proposed_right > proposed_left
            and abs(proposed_left - outer.left) <= max_shift
            and abs(proposed_right - outer.right) <= max_shift
            and width_change <= grid_refine.max_width_change
            and 0 <= proposed_left < proposed_right <= ww
        ):
            outer = Box(proposed_left, outer.top, proposed_right, outer.bottom)
            crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
            profile = cached_separator_profile(cache, gray_work, outer, fmt.name, policy.separator.profile)
            pitch = outer.width / float(max(1, count))
            origin = 0.0
            gaps = [
                find_gap(
                    profile,
                    pitch * i,
                    pitch,
                    i,
                    fmt.name,
                    gap_max_width_ratio_override,
                    policy.separator.gap_search,
                )
                for i in range(1, count)
            ]
            if strip_mode == "full" and count > 1:
                gaps, edge_refine_detail = refine_gaps_by_edge_pairs(
                    crop,
                    gaps,
                    count,
                    fmt.name,
                    cache,
                    outer,
                    policy.separator.edge_pair,
                    policy.separator.edge_refine_profile,
                )
            gaps, grid_detail = apply_robust_grid(
                gaps,
                origin,
                pitch,
                strip_mode,
                fmt.name,
                profile,
                gray_work,
                outer,
                policy.separator.hard_gap_trust,
                policy.separator.nearby_correction,
                policy.separator.robust_grid,
            )
            grid_detail["outer_refined"] = True
    separator_analysis_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    separator_analysis_allowed = (
        allow_separator_analysis
        and strip_mode == "full"
        and not policy.separator.geometry_support.wide_geometry.enabled
    )
    if separator_analysis_allowed:
        if should_run_enhanced_separator_analysis(config.analysis, gaps, count, policy.separator.enhanced):
            gaps, separator_analysis_detail = merge_enhanced_separator_gaps(
                gray_work,
                outer,
                gaps,
                origin,
                pitch,
                strip_mode,
                fmt.name,
                cache,
                policy.separator.robust_grid,
                policy.separator.gap_search,
                policy.separator.profile,
                policy.separator.enhanced,
            )
        elif config.analysis == "auto":
            separator_analysis_detail = {"used": False, "reason": "auto_not_needed"}
    nearby_correction_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    confidence_cap_after_nearby: Optional[float] = None
    if strip_mode == "full" and policy.separator.nearby_correction.enabled:
        pre_correction_boxes = frame_boxes_from_gaps(
            outer, gaps, count, ww, wh, config.bleed_x, config.bleed_y, origin=origin, pitch=pitch
        )
        pre_correction_confidence, _pre_reasons, _pre_detail = score_detection(
            gray_work, outer, gaps, pre_correction_boxes, count, fmt, strip_mode, policy
        )
        gaps, nearby_correction_detail = apply_nearby_separator_corrections(
            profile,
            gaps,
            origin,
            pitch,
            count,
            strip_mode,
            policy.separator.nearby_correction,
        )
        if int(nearby_correction_detail.get("accepted_count", 0) or 0) > 0:
            confidence_cap_after_nearby = float(pre_correction_confidence)
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
    if confidence_cap_after_nearby is not None:
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
            "grid": grid_detail,
            "grid_residual": grid_detail.get("grid_residual"),
            "grid_used": bool(grid_detail.get("grid_used", False)),
            "edge_refine": edge_refine_detail,
            "frame_size_fit": frame_size_detail,
            "separator_analysis": separator_analysis_detail,
            "nearby_separator_correction": nearby_correction_detail,
            "gap_max_width_ratio_override": gap_max_width_ratio_override,
            "partial_edge_hint": partial_edge_hint(profile, origin, pitch, count, policy.partial_edge_hint) if strip_mode == "partial" else {},
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
        }
    )
    if confidence_cap_after_nearby is not None:
        detail["nearby_separator_correction_confidence_cap"] = float(confidence_cap_after_nearby)
    return Detection(fmt.name, config.layout, strip_mode, count, outer_original, boxes, gaps, confidence, reasons, detail)
