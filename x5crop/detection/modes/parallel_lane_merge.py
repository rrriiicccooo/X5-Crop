from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...constants import ANALYSIS_SOURCE_PARALLEL_LANE
from ...domain import Box, Detection, Gap
from ...formats import FORMATS
from ...geometry.boxes import map_work_box
from ...policies.runtime_policy import DetectionPolicy
from ...runtime_config import RuntimeConfig
from ...utils import box_from_dict
from ..candidate.fallback import hard_fallback_detection


def parallel_lane_review_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    policy: DetectionPolicy,
    reason: str,
) -> Detection:
    detection = hard_fallback_detection(gray, config, FORMATS[policy.format_id])
    detection.review_reasons.append(reason)
    detection.review_reasons = sorted(set(detection.review_reasons))
    return detection


def merge_parallel_lane_detections(
    gray: np.ndarray,
    config: RuntimeConfig,
    lanes: list[Box],
    lane_detections: list[Detection | None],
    policy: DetectionPolicy,
) -> Detection:
    if any(detection is None for detection in lane_detections):
        return parallel_lane_review_detection(gray, config, policy, "parallel_lane_detection_failed")

    confirmed_lanes = [detection for detection in lane_detections if detection is not None]
    lane_work_outers = [
        box_from_dict(detection.detail["work_outer"])
        for detection in confirmed_lanes
        if isinstance(detection.detail.get("work_outer"), dict)
    ]
    if len(lane_work_outers) != policy.detector.dual_lane.lane_count:
        return parallel_lane_review_detection(gray, config, policy, "parallel_lane_outer_detection_failed")

    combined_work_outer = Box(
        min(box.left for box in lane_work_outers),
        min(box.top for box in lane_work_outers),
        max(box.right for box in lane_work_outers),
        max(box.bottom for box in lane_work_outers),
    )
    lane_format = policy.detector.dual_lane.lane_format
    lane_count = FORMATS[lane_format].default_count
    total_count = FORMATS[policy.format_id].default_count
    frames = [box for detection in confirmed_lanes for box in detection.frames]
    gaps = _merged_parallel_lane_gaps(confirmed_lanes, lane_count)

    lane_confidences = [float(detection.confidence) for detection in confirmed_lanes]
    confidence = min(lane_confidences)
    review_reasons = sorted(set(reason for detection in confirmed_lanes for reason in detection.review_reasons))
    if any(conf < config.confidence_threshold for conf in lane_confidences):
        confidence = min(confidence, 0.84)
        review_reasons.append("parallel_lane_below_threshold")
    if len(frames) != total_count:
        confidence = min(confidence, 0.82)
        review_reasons.append("frame_count_mismatch")

    source_h, source_w = gray.shape
    outer_original = map_work_box(combined_work_outer, config.layout, source_w, source_h)
    return Detection(
        policy.format_id,
        config.layout,
        "full",
        total_count,
        outer_original,
        frames,
        gaps,
        float(max(0.0, min(1.0, confidence))),
        sorted(set(review_reasons)),
        _parallel_lane_detail(
            config,
            policy,
            lanes,
            combined_work_outer,
            gaps,
            confirmed_lanes,
            confidence,
            review_reasons,
            lane_count,
            total_count,
        ),
    )


def _merged_parallel_lane_gaps(lane_detections: list[Detection], lane_count: int) -> list[Gap]:
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


def _parallel_lane_detail(
    config: RuntimeConfig,
    policy: DetectionPolicy,
    lanes: list[Box],
    combined_work_outer: Box,
    gaps: list[Gap],
    lane_detections: list[Detection],
    confidence: float,
    review_reasons: list[str],
    lane_count: int,
    total_count: int,
) -> dict:
    lane_format = policy.detector.dual_lane.lane_format
    lane_summaries = [
        {
            "lane": index,
            "lane_format": lane_format,
            "lane_count": lane_count,
            "total_format": policy.format_id,
            "total_count": total_count,
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
        "analysis_source": ANALYSIS_SOURCE_PARALLEL_LANE,
        "layout": config.layout,
        "candidate_count": total_count,
        "work_outer": asdict(combined_work_outer),
        "dual_lane_work_boxes": [asdict(lane) for lane in lanes],
        "dual_lane_detections": lane_summaries,
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
        "candidate_competition": {
            "candidate_count": policy.detector.dual_lane.lane_count,
            "formats": [policy.format_id],
            "selected_candidate": {
                "format": policy.format_id,
                "count": total_count,
                "strip_mode": "full",
                "confidence": float(confidence),
                "review_reasons": sorted(set(review_reasons)),
            },
            "selection_override": None,
            "top_candidates": lane_summaries,
        },
    }


__all__ = [
    "merge_parallel_lane_detections",
    "parallel_lane_review_detection",
]
