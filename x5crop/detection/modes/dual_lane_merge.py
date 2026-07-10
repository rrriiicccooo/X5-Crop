from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...constants import CANDIDATE_SOURCE_DUAL_LANE
from ...domain import Box, DetectionCandidate, Gap
from ...geometry.boxes import map_work_box
from ...run_config import RunConfig
from ...utils import box_from_dict
from ..candidate.signals import (
    SIGNAL_DUAL_LANE_BELOW_THRESHOLD,
    SIGNAL_DUAL_LANE_DETECTION_FAILED,
    SIGNAL_DUAL_LANE_OUTER_DETECTION_FAILED,
    SIGNAL_FRAME_COUNT_MISMATCH,
    add_candidate_signals,
    normalized_candidate_signals,
)
from ..detail import candidate_signals_from_detail
from ..candidate.proposal.hard_safety import hard_safety_detection
from ..candidate.assessment.mode import apply_mode_candidate_assessment
from .dual_lane_context import DualLaneDetectionContext


def dual_lane_review_detection(
    gray: np.ndarray,
    config: RunConfig,
    context: DualLaneDetectionContext,
    mode_signal: str,
) -> DetectionCandidate:
    parent_spec = context.policy.physical_spec
    detection = hard_safety_detection(
        gray,
        config,
        parent_spec,
        parent_spec.default_count,
        context.lane_policy.frame_fit,
    )
    add_candidate_signals(detection, [mode_signal])
    mode_diagnostics = detection.detail.setdefault("mode_diagnostics", [])
    if isinstance(mode_diagnostics, list):
        mode_diagnostics.append(mode_signal)
    return apply_mode_candidate_assessment(
        detection,
        source=CANDIDATE_SOURCE_DUAL_LANE,
        source_auto_allowed=False,
        component_candidate_gates=[],
    )


def merge_dual_lane_detections(
    gray: np.ndarray,
    config: RunConfig,
    lanes: list[Box],
    lane_detections: list[DetectionCandidate | None],
    context: DualLaneDetectionContext,
) -> DetectionCandidate:
    parent_spec = context.policy.physical_spec
    lane_spec = context.lane_policy.physical_spec
    if any(detection is None for detection in lane_detections):
        return dual_lane_review_detection(gray, config, context, SIGNAL_DUAL_LANE_DETECTION_FAILED)

    confirmed_lanes = [detection for detection in lane_detections if detection is not None]
    lane_work_outers = [
        box_from_dict(detection.detail["work_outer"])
        for detection in confirmed_lanes
        if isinstance(detection.detail.get("work_outer"), dict)
    ]
    if len(lane_work_outers) != parent_spec.lane_count:
        return dual_lane_review_detection(gray, config, context, SIGNAL_DUAL_LANE_OUTER_DETECTION_FAILED)

    combined_work_outer = Box(
        min(box.left for box in lane_work_outers),
        min(box.top for box in lane_work_outers),
        max(box.right for box in lane_work_outers),
        max(box.bottom for box in lane_work_outers),
    )
    frames = [box for detection in confirmed_lanes for box in detection.frames]
    gaps = _merged_dual_lane_gaps(confirmed_lanes, lane_spec.default_count)

    lane_confidences = [float(detection.confidence) for detection in confirmed_lanes]
    confidence = min(lane_confidences)
    mode_signals = normalized_candidate_signals(
        [
            signal
            for detection in confirmed_lanes
            for signal in candidate_signals_from_detail(detection)
        ]
    )
    if any(conf < config.confidence_threshold for conf in lane_confidences):
        confidence = min(
            confidence,
            context.lane_policy.scoring.calibration.dual_lane_below_threshold_cap,
        )
        mode_signals.append(SIGNAL_DUAL_LANE_BELOW_THRESHOLD)
    if len(frames) != parent_spec.default_count:
        confidence = min(
            confidence,
            context.lane_policy.scoring.calibration.dual_lane_frame_count_mismatch_cap,
        )
        mode_signals.append(SIGNAL_FRAME_COUNT_MISMATCH)

    source_h, source_w = gray.shape
    outer_original = map_work_box(combined_work_outer, config.layout, source_w, source_h)
    detection = DetectionCandidate(
        format_id=parent_spec.format_id,
        layout=config.layout,
        strip_mode="full",
        count=parent_spec.default_count,
        outer=outer_original,
        frames=frames,
        gaps=gaps,
        confidence=float(max(0.0, min(1.0, confidence))),
        detail=_dual_lane_detail(
            config,
            context,
            lanes,
            combined_work_outer,
            gaps,
            confirmed_lanes,
            mode_signals,
        ),
    )
    component_gates = [
        dict(detection.detail["candidate_assessment"]["candidate_gate"])
        for detection in confirmed_lanes
    ]
    return apply_mode_candidate_assessment(
        detection,
        source=CANDIDATE_SOURCE_DUAL_LANE,
        source_auto_allowed=True,
        component_candidate_gates=component_gates,
    )


def _merged_dual_lane_gaps(lane_detections: list[DetectionCandidate], lane_count: int) -> list[Gap]:
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
    config: RunConfig,
    context: DualLaneDetectionContext,
    lanes: list[Box],
    combined_work_outer: Box,
    gaps: list[Gap],
    lane_detections: list[DetectionCandidate],
    mode_signals: list[str],
) -> dict:
    parent_spec = context.policy.physical_spec
    lane_spec = context.lane_policy.physical_spec
    lane_summaries = [
        {
            "lane": index,
            "lane_format": lane_spec.format_id,
            "lane_count": lane_spec.default_count,
            "total_format": parent_spec.format_id,
            "total_count": parent_spec.default_count,
            "confidence": float(detection.confidence),
            "candidate_signals": candidate_signals_from_detail(detection),
            "work_outer": detection.detail.get("work_outer"),
            "content_evidence": detection.detail.get("content_evidence", {}),
            "outer_content_alignment": detection.detail.get("outer_content_alignment", {}),
            "candidate_assessment": detection.detail.get("candidate_assessment", {}),
        }
        for index, detection in enumerate(lane_detections, start=1)
    ]
    return {
        "candidate_signals": sorted(set(mode_signals)),
        "candidate_source": CANDIDATE_SOURCE_DUAL_LANE,
        "mode_diagnostics": sorted(set(mode_signals)),
        "layout": config.layout,
        "candidate_count": parent_spec.default_count,
        "work_outer": asdict(combined_work_outer),
        "dual_lane_work_boxes": [asdict(lane) for lane in lanes],
        "dual_lane_detections": lane_summaries,
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
        "dual_lane_composition": {
            "lane_count": parent_spec.lane_count,
            "lanes": lane_summaries,
        },
    }
