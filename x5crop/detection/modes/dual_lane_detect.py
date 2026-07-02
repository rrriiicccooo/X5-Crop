from __future__ import annotations

from dataclasses import asdict, replace
from typing import Optional

import numpy as np

from ...constants import (
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
)
from ...domain import Box, Detection
from ...runtime import AnalysisCache
from ...runtime_config import RuntimeConfig
from ..candidate.selection import calibrated_candidate_rank
from ..outer.proposal.base import base_outer_candidates
from .dual_lane_context import DualLaneDetectionContext
from .dual_lane_split import translate_work_box


def detect_dual_lane(
    gray: np.ndarray,
    config: RuntimeConfig,
    lane: Box,
    lane_index: int,
    cache: AnalysisCache,
    context: DualLaneDetectionContext,
) -> Optional[Detection]:
    from ..candidate.build import build_detection_for_outer
    from ..candidate.candidate_assessment import apply_candidate_assessment_policy
    from ..evidence.content_evidence import content_evidence_detail
    from ..evidence.outer_alignment import outer_content_alignment_detail

    lane_crop = cache.gray_work[lane.top:lane.bottom, lane.left:lane.right]
    if lane_crop.size == 0:
        return None

    lane_config = replace(
        config,
        film_format=context.lane_format_id,
        count=context.lane_format_spec.default_count,
        count_override=context.lane_format_spec.default_count,
    )

    candidates: list[Detection] = []
    for outer_candidate in base_outer_candidates(lane_crop, context.lane_policy.outer.base_candidates):
        lane_outer = translate_work_box(outer_candidate.box, lane.left, lane.top)
        raw = build_detection_for_outer(
            gray,
            lane_config,
            context.lane_format_spec,
            context.lane_format_spec.default_count,
            "full",
            lane_outer,
            0.0,
            f"dual_lane_{lane_index}_{outer_candidate.name}",
            outer_candidate.strategy,
            cache=cache,
        )
        calibrated = apply_candidate_assessment_policy(
            gray,
            raw,
            lane_config,
            context.lane_format_spec,
            "separator",
            cache,
            policy=context.lane_policy,
        )
        calibrated.detail["dual_lane_index"] = lane_index
        calibrated.detail["dual_lane_work_box"] = asdict(lane)
        candidates.append(calibrated)

    if not candidates:
        return None

    best = max(candidates, key=lambda d: calibrated_candidate_rank(d, config.confidence_threshold))
    content_detail = content_evidence_detail(gray, best, cache, context.lane_policy.content)
    outer_alignment = outer_content_alignment_detail(gray, best, cache, policy=context.lane_policy)
    best.detail["content_evidence"] = content_detail
    best.detail["outer_content_alignment"] = outer_alignment

    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            best.confidence = min(best.confidence, 0.82)
            best.review_reasons.append(REASON_CONTENT_ASPECT_CONFLICT)
        elif support in {"low_content", "weak"} and best.confidence >= config.confidence_threshold:
            best.confidence = min(best.confidence, 0.84)
            best.review_reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        best.confidence = min(best.confidence, 0.84)
        best.review_reasons.append(REASON_OUTER_CONTENT_BBOX_MISMATCH)

    best.review_reasons = sorted(set(best.review_reasons))
    return best


__all__ = ["detect_dual_lane"]
