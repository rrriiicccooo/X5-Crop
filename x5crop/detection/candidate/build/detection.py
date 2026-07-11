from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np

from ....domain import Box, DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....geometry.boxes import map_work_box
from ....geometry.frame_fit import fit_frame_boxes_from_gaps
from ....geometry.layout import work_gray
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....run_config import RunConfig
from ....utils import box_from_dict
from ...evidence.frame_topology import frame_topology_evidence
from ...evidence.separator_continuity import separator_cross_axis_continuity_evidence
from ...physical.photo_size import photo_size_consistency_from_gap_edges
from ...physical.separator.hints import SeparatorGapHintSet
from .partial_edge import partial_edge_hint
from .separator_gaps import (
    SeparatorGapBuildResult,
    apply_nearby_separator_refinements,
    build_primary_separator_gaps_for_outer,
)


def build_detection_geometry_for_outer(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    outer_candidate_name: str,
    outer_candidate_strategy: str,
    outer_candidate_detail: Optional[dict] = None,
    gap_max_width_ratio_override: Optional[float] = None,
    separator_gap_hints: Optional[SeparatorGapHintSet] = None,
    *,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> DetectionCandidate:
    h, w = gray.shape
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    separator_gaps = _build_separator_gap_lifecycle(
        gray_work,
        fmt,
        count,
        strip_mode,
        outer,
        offset_fraction,
        cache,
        gap_max_width_ratio_override,
        policy,
        explicit_count=bool(config.requested_count is not None),
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
    detail: dict[str, object] = {}
    detail.update(
        {
            "candidate_build": {
                "owner": "candidate.build",
                "role": "physical_detection_geometry",
            },
            "candidate_count": count,
            "offset_fraction": float(offset_fraction),
            "origin": float(origin),
            "pitch": float(pitch),
            "layout": config.layout,
            "outer_candidate": outer_candidate_name,
            "outer_candidate_strategy": outer_candidate_strategy,
            "outer_candidate_detail": dict(outer_candidate_detail or {}),
            "work_outer": asdict(outer),
            "work_frame_boxes": [asdict(box) for box in boxes_work],
            "standard_gap_search": separator_gaps.standard_gap_search_detail,
            "separator_gap_hints": (
                separator_gap_hints.summary()
                if separator_gap_hints is not None
                else {"used": False, "reason": "no_gap_hints"}
            ),
            "edge_pair_correction": separator_gaps.edge_pair_correction_detail,
            "frame_size_fit": frame_size_detail,
            "nearby_separator_refinement": separator_gaps.nearby_refinement_detail,
            "gap_max_width_ratio_override": gap_max_width_ratio_override,
            "partial_edge_hint": partial_edge_hint(profile, origin, pitch, count, policy.partial_edge_hint) if strip_mode == "partial" else {},
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
        }
    )
    if separator_gaps.pre_nearby_gaps is not None:
        detail["pre_nearby_gaps"] = [asdict(gap) for gap in separator_gaps.pre_nearby_gaps]
    return DetectionCandidate(
        format_id=fmt.format_id,
        layout=config.layout,
        strip_mode=strip_mode,
        count=count,
        outer=outer_original,
        frames=boxes,
        gaps=gaps,
        confidence=0.0,
        detail=detail,
    )


def enrich_detection_geometry_evidence(
    gray: np.ndarray,
    detection: DetectionCandidate,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    cache: Optional[AnalysisCache],
    *,
    policy: DetectionPolicy,
) -> DetectionCandidate:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = box_from_dict(detection.detail.get("work_outer", {}))
    origin = float(detection.detail.get("origin", 0.0))
    pitch = float(detection.detail.get("pitch", 0.0))
    topology_boxes_work, _topology_fit_detail = fit_frame_boxes_from_gaps(
        outer,
        detection.gaps,
        detection.count,
        ww,
        wh,
        0,
        0,
        origin=origin,
        pitch=pitch,
        frame_fit=policy.frame_fit,
    )
    frame_aspect = float(fmt.horizontal_content_aspect or 0.0)
    target_photo_width = float(outer.height) * frame_aspect if frame_aspect > 0.0 else None
    photo_size_consistency = photo_size_consistency_from_gap_edges(
        detection.gaps,
        origin,
        pitch,
        detection.count,
        target_photo_width=target_photo_width,
    )
    detection.detail.update(
        {
            "frame_topology_evidence": frame_topology_evidence(topology_boxes_work, detection.count),
            "photo_size_consistency": photo_size_consistency.detail(),
            "separator_cross_axis_continuity": separator_cross_axis_continuity_evidence(
                gray_work,
                outer,
                detection.gaps,
                pitch,
                policy.separator.hard_gap_trust,
            ),
        }
    )
    return detection


def _build_separator_gap_lifecycle(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float,
    cache: Optional[AnalysisCache],
    gap_max_width_ratio_override: Optional[float],
    policy: DetectionPolicy,
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
    return apply_nearby_separator_refinements(
        count,
        strip_mode,
        separator_gaps,
        policy,
        explicit_count=explicit_count,
    )
