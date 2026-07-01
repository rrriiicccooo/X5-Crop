from __future__ import annotations

from dataclasses import asdict, replace
from typing import Optional

import numpy as np

from ...config import RuntimeConfig
from ...constants import (
    ANALYSIS_SOURCE_PARALLEL_LANE,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
)
from ...domain import Box, Detection, Gap
from ...formats import FORMATS
from ...geometry.boxes import map_work_box
from ...policies.registry import get_detection_policy
from ...runtime import AnalysisCache
from ...utils import bbox_from_mask, box_from_dict
from ..candidate.selection import calibrated_candidate_rank
from ..outer.base import base_outer_candidates
from .unsupported import unsupported_parallel_lane_partial_detection


def translate_box(box: Box, dx: int, dy: int) -> Box:
    return Box(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy)


def split_parallel_strip_lanes(gray_work: np.ndarray) -> list[Box]:
    h, w = gray_work.shape
    content = bbox_from_mask(gray_work < 246, min_row_fraction=0.010, min_col_fraction=0.010)
    if content is None or not content.valid():
        content = Box(0, 0, w, h)
    split_y = int(round((content.top + content.bottom) / 2.0))
    guard = max(2, min(80, int(round(content.height * 0.006))))
    lanes = [
        Box(content.left, content.top, content.right, max(content.top + 1, split_y - guard)).clamp(w, h),
        Box(content.left, min(content.bottom - 1, split_y + guard), content.right, content.bottom).clamp(w, h),
    ]
    if any(not lane.valid() or lane.height < max(20, h * 0.10) for lane in lanes):
        split_y = h // 2
        lanes = [Box(0, 0, w, split_y), Box(0, split_y, w, h)]
    return lanes


def detect_parallel_strip_lane(
    gray: np.ndarray,
    config: RuntimeConfig,
    lane: Box,
    lane_index: int,
    cache,
) -> Optional[Detection]:
    from ..candidate.decision import apply_candidate_decision_policy
    from ..candidate.build import build_detection_for_outer
    from ..evidence.content import content_evidence_detail
    from ..outer.alignment import outer_content_alignment_detail

    lane_crop = cache.gray_work[lane.top:lane.bottom, lane.left:lane.right]
    if lane_crop.size == 0:
        return None
    dual_policy = get_detection_policy(config.film_format, config.strip_mode)
    lane_format = dual_policy.detector.dual_lane.lane_format
    lane_policy = get_detection_policy(lane_format, "full")
    lane_format_spec = FORMATS[lane_format]
    lane_config = replace(
        config,
        film_format=lane_format,
        count=lane_format_spec.default_count,
        count_override=lane_format_spec.default_count,
    )
    candidates: list[Detection] = []
    for outer_candidate in base_outer_candidates(lane_crop, lane_policy.outer.base_candidates):
        lane_outer = translate_box(outer_candidate.box, lane.left, lane.top)
        raw = build_detection_for_outer(
            gray,
            lane_config,
            lane_format_spec,
            lane_format_spec.default_count,
            "full",
            lane_outer,
            0.0,
            f"parallel_lane_{lane_index}_{outer_candidate.name}",
            outer_candidate.strategy,
            cache=cache,
        )
        calibrated = apply_candidate_decision_policy(
            gray,
            raw,
            lane_config,
            lane_format_spec,
            "separator",
            cache,
            policy=lane_policy,
        )
        calibrated.detail["dual_lane_index"] = lane_index
        calibrated.detail["dual_lane_work_box"] = asdict(lane)
        candidates.append(calibrated)
    if not candidates:
        return None
    best = max(candidates, key=lambda d: calibrated_candidate_rank(d, config.confidence_threshold))
    content_detail = content_evidence_detail(gray, best, cache, lane_policy.content)
    outer_alignment = outer_content_alignment_detail(gray, best, cache, policy=lane_policy)
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


def choose_parallel_lane_detection(gray: np.ndarray, config: RuntimeConfig, cache) -> Detection:
    from ..candidate.fallback import hard_fallback_detection

    if config.strip_mode != "full":
        return unsupported_parallel_lane_partial_detection(gray, config)

    gray_work = cache.gray_work
    source_h, source_w = gray.shape
    lanes = split_parallel_strip_lanes(gray_work)
    lane_detections = [
        detect_parallel_strip_lane(gray, config, lane, index, cache)
        for index, lane in enumerate(lanes, start=1)
    ]
    if any(detection is None for detection in lane_detections):
        detection = hard_fallback_detection(gray, config, FORMATS["135-dual"])
        detection.review_reasons.append("parallel_lane_detection_failed")
        detection.review_reasons = sorted(set(detection.review_reasons))
        return detection

    confirmed_lanes = [detection for detection in lane_detections if detection is not None]
    lane_work_outers = [
        box_from_dict(detection.detail["work_outer"])
        for detection in confirmed_lanes
        if isinstance(detection.detail.get("work_outer"), dict)
    ]
    if len(lane_work_outers) != 2:
        detection = hard_fallback_detection(gray, config, FORMATS["135-dual"])
        detection.review_reasons.append("parallel_lane_outer_detection_failed")
        detection.review_reasons = sorted(set(detection.review_reasons))
        return detection

    combined_work_outer = Box(
        min(box.left for box in lane_work_outers),
        min(box.top for box in lane_work_outers),
        max(box.right for box in lane_work_outers),
        max(box.bottom for box in lane_work_outers),
    )
    frames = [box for detection in confirmed_lanes for box in detection.frames]
    gaps: list[Gap] = []
    for lane_number, detection in enumerate(confirmed_lanes, start=1):
        lane_work_outer = box_from_dict(detection.detail["work_outer"])
        for gap in detection.gaps:
            gaps.append(
                Gap(
                    index=(lane_number - 1) * 6 + int(gap.index),
                    center=float(gap.center),
                    score=float(gap.score),
                    method=gap.method,
                    start=gap.start,
                    end=gap.end,
                    lane_box=asdict(lane_work_outer),
                )
            )

    lane_confidences = [float(detection.confidence) for detection in confirmed_lanes]
    confidence = min(lane_confidences)
    review_reasons = sorted(set(reason for detection in confirmed_lanes for reason in detection.review_reasons))
    if any(conf < config.confidence_threshold for conf in lane_confidences):
        confidence = min(confidence, 0.84)
        review_reasons.append("parallel_lane_below_threshold")
    if len(frames) != 12:
        confidence = min(confidence, 0.82)
        review_reasons.append("frame_count_mismatch")

    lane_summaries = [
        {
            "lane": index,
            "lane_format": "135",
            "lane_count": 6,
            "total_format": "135-dual",
            "total_count": 12,
            "confidence": float(detection.confidence),
            "review_reasons": list(detection.review_reasons),
            "work_outer": detection.detail.get("work_outer"),
            "content_evidence": detection.detail.get("content_evidence", {}),
            "outer_content_alignment": detection.detail.get("outer_content_alignment", {}),
            "candidate_decision": detection.detail.get("candidate_decision", {}),
        }
        for index, detection in enumerate(confirmed_lanes, start=1)
    ]
    detail = {
        "analysis_source": ANALYSIS_SOURCE_PARALLEL_LANE,
        "layout": config.layout,
        "candidate_count": 12,
        "work_outer": asdict(combined_work_outer),
        "dual_lane_work_boxes": [asdict(lane) for lane in lanes],
        "dual_lane_detections": lane_summaries,
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
        "candidate_competition": {
            "candidate_count": 2,
            "formats": ["135-dual"],
            "selected_candidate": {
                "format": "135-dual",
                "count": 12,
                "strip_mode": "full",
                "confidence": float(confidence),
                "review_reasons": sorted(set(review_reasons)),
            },
            "selection_override": None,
            "top_candidates": lane_summaries,
        },
    }
    outer_original = map_work_box(combined_work_outer, config.layout, source_w, source_h)
    return Detection(
        "135-dual",
        config.layout,
        "full",
        12,
        outer_original,
        frames,
        gaps,
        float(max(0.0, min(1.0, confidence))),
        sorted(set(review_reasons)),
        detail,
    )
