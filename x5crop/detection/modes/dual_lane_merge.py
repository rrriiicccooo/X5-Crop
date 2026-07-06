from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...constants import CANDIDATE_SOURCE_DUAL_LANE
from ...domain import Box, Detection, Gap
from ...geometry.boxes import map_work_box
from ...runtime.config import RuntimeConfig
from ...utils import box_from_dict
from ..candidate.proposal.safety import hard_safety_detection
from .dual_lane_context import DualLaneDetectionContext


def dual_lane_review_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    context: DualLaneDetectionContext,
    reason: str,
) -> Detection:
    detection = hard_safety_detection(gray, config, context.format_spec)
    detection.review_reasons.append(reason)
    detection.review_reasons = sorted(set(detection.review_reasons))
    return detection


def merge_dual_lane_detections(
    gray: np.ndarray,
    config: RuntimeConfig,
    lanes: list[Box],
    lane_detections: list[Detection | None],
    context: DualLaneDetectionContext,
) -> Detection:
    if any(detection is None for detection in lane_detections):
        return dual_lane_review_detection(gray, config, context, "dual_lane_detection_failed")

    confirmed_lanes = [detection for detection in lane_detections if detection is not None]
    lane_work_outers = [
        box_from_dict(detection.detail["work_outer"])
        for detection in confirmed_lanes
        if isinstance(detection.detail.get("work_outer"), dict)
    ]
    if len(lane_work_outers) != context.lane_count:
        return dual_lane_review_detection(gray, config, context, "dual_lane_outer_detection_failed")

    combined_work_outer = Box(
        min(box.left for box in lane_work_outers),
        min(box.top for box in lane_work_outers),
        max(box.right for box in lane_work_outers),
        max(box.bottom for box in lane_work_outers),
    )
    frames = [box for detection in confirmed_lanes for box in detection.frames]
    gaps = _merged_dual_lane_gaps(confirmed_lanes, context.lane_format_spec.default_count)

    lane_confidences = [float(detection.confidence) for detection in confirmed_lanes]
    confidence = min(lane_confidences)
    review_reasons = sorted(set(reason for detection in confirmed_lanes for reason in detection.review_reasons))
    if any(conf < config.confidence_threshold for conf in lane_confidences):
        confidence = min(confidence, 0.84)
        review_reasons.append("dual_lane_below_threshold")
    if len(frames) != context.total_count:
        confidence = min(confidence, 0.82)
        review_reasons.append("frame_count_mismatch")

    source_h, source_w = gray.shape
    outer_original = map_work_box(combined_work_outer, config.layout, source_w, source_h)
    return Detection(
        context.format_id,
        config.layout,
        "full",
        context.total_count,
        outer_original,
        frames,
        gaps,
        float(max(0.0, min(1.0, confidence))),
        sorted(set(review_reasons)),
        _dual_lane_detail(
            config,
            context,
            lanes,
            combined_work_outer,
            gaps,
            confirmed_lanes,
            confidence,
            review_reasons,
        ),
    )


def _merged_dual_lane_gaps(lane_detections: list[Detection], lane_count: int) -> list[Gap]:
    gaps: list[Gap] = []
    for lane_number, detection in enumerate(lane_detections, start=1):
        lane_work_outer = box_from_dict(detection.detail["work_outer"])
        for gap in detection.gaps:
            gaps.append(
                Gap(
                    index=(lane_number - 1) * lane_count + int(gap.index),
                    center=float(gap.center),
                    score=float(gap.score),
                    method=gap.method,
                    start=gap.start,
                    end=gap.end,
                    lane_box=asdict(lane_work_outer),
                )
            )
    return gaps


def _dual_lane_detail(
    config: RuntimeConfig,
    context: DualLaneDetectionContext,
    lanes: list[Box],
    combined_work_outer: Box,
    gaps: list[Gap],
    lane_detections: list[Detection],
    confidence: float,
    review_reasons: list[str],
) -> dict:
    lane_summaries = [
        {
            "lane": index,
            "lane_format": context.lane_format_id,
            "lane_count": context.lane_format_spec.default_count,
            "total_format": context.format_id,
            "total_count": context.total_count,
            "confidence": float(detection.confidence),
            "review_reasons": list(detection.review_reasons),
            "work_outer": detection.detail.get("work_outer"),
            "content_evidence": detection.detail.get("content_evidence", {}),
            "outer_content_alignment": detection.detail.get("outer_content_alignment", {}),
            "candidate_assessment": detection.detail.get("candidate_assessment", {}),
        }
        for index, detection in enumerate(lane_detections, start=1)
    ]
    return {
        "candidate_source": CANDIDATE_SOURCE_DUAL_LANE,
        "layout": config.layout,
        "candidate_count": context.total_count,
        "work_outer": asdict(combined_work_outer),
        "dual_lane_work_boxes": [asdict(lane) for lane in lanes],
        "dual_lane_detections": lane_summaries,
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
        "candidate_competition": {
            "candidate_count": context.lane_count,
            "formats": [context.format_id],
            "selected_candidate": {
                "format": context.format_id,
                "count": context.total_count,
                "strip_mode": "full",
                "confidence": float(confidence),
                "review_reasons": sorted(set(review_reasons)),
            },
            "selection_override": None,
            "top_candidates": lane_summaries,
        },
    }


__all__ = [
    "merge_dual_lane_detections",
    "dual_lane_review_detection",
]
