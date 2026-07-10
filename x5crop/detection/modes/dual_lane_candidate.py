from __future__ import annotations

from dataclasses import asdict, replace
from typing import Optional

import numpy as np

from ...cache import AnalysisCache
from ...domain import Box, DetectionCandidate
from ...formats import FormatPhysicalSpec
from ...geometry.boxes import translate_box
from ...policies.runtime.policy import DetectionPolicy
from ...runtime.config import RuntimeConfig
from ..candidate.assessment.candidate import apply_candidate_assessment_policy
from ..candidate.assessment.dual_lane import apply_dual_lane_content_assessment
from ..candidate.build.detection import build_detection_geometry_for_outer, enrich_detection_geometry_evidence
from ..candidate.selection.choose import select_source_candidate
from ..physical.outer.base import base_outer_candidates


def select_dual_lane_candidate(
    gray: np.ndarray,
    config: RuntimeConfig,
    lane: Box,
    lane_index: int,
    cache: AnalysisCache,
    lane_format_id: str,
    lane_format_spec: FormatPhysicalSpec,
    lane_policy: DetectionPolicy,
) -> Optional[DetectionCandidate]:
    lane_crop = cache.gray_work[lane.top:lane.bottom, lane.left:lane.right]
    if lane_crop.size == 0:
        return None

    lane_config = replace(
        config,
        film_format=lane_format_id,
        count=lane_format_spec.default_count,
        count_override=lane_format_spec.default_count,
    )

    candidates = [
        _assessed_lane_candidate(
            gray,
            lane_config,
            lane,
            lane_index,
            cache,
            lane_format_spec,
            lane_policy,
            outer_candidate,
        )
        for outer_candidate in base_outer_candidates(
            lane_crop,
            lane_policy.outer.proposal.base.candidates,
        )
    ]
    if not candidates:
        return None

    best = select_source_candidate(candidates, config.confidence_threshold)
    apply_dual_lane_content_assessment(
        gray,
        best,
        cache,
        lane_policy,
        config.confidence_threshold,
        lane_format_spec.horizontal_content_aspect,
    )
    return best


def _assessed_lane_candidate(
    gray: np.ndarray,
    lane_config: RuntimeConfig,
    lane: Box,
    lane_index: int,
    cache: AnalysisCache,
    lane_format_spec: FormatPhysicalSpec,
    lane_policy: DetectionPolicy,
    outer_candidate,
) -> DetectionCandidate:
    lane_outer = translate_box(outer_candidate.box, lane.left, lane.top)
    raw = build_detection_geometry_for_outer(
        gray,
        lane_config,
        lane_format_spec,
        lane_format_spec.default_count,
        "full",
        lane_outer,
        0.0,
        f"dual_lane_{lane_index}_{outer_candidate.name}",
        outer_candidate.strategy,
        outer_candidate_detail={
            **outer_candidate.detail,
            "dual_lane_index": int(lane_index),
            "lane_box": asdict(lane),
        },
        cache=cache,
        policy=lane_policy,
    )
    raw = enrich_detection_geometry_evidence(gray, raw, lane_config, lane_format_spec, cache, policy=lane_policy)
    assessed = apply_candidate_assessment_policy(
        gray,
        raw,
        lane_config,
        lane_format_spec,
        "separator",
        cache,
        policy=lane_policy,
    )
    assessed.detail["dual_lane_index"] = lane_index
    assessed.detail["dual_lane_work_box"] = asdict(lane)
    return assessed


__all__ = ["select_dual_lane_candidate"]
