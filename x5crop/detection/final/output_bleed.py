from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...domain import Box, Detection
from ...geometry.boxes import map_work_box, original_box_to_work


class OutputBleedPolicy(Protocol):
    detection_long_axis_bleed: int
    detection_short_axis_bleed: int
    overlap_risk_long_axis_bleed: int


@dataclass(frozen=True)
class AxisBleedParameters:
    long_axis: int
    short_axis: int


def detection_bleed_parameters(output_policy: OutputBleedPolicy) -> AxisBleedParameters:
    return AxisBleedParameters(
        long_axis=int(output_policy.detection_long_axis_bleed),
        short_axis=int(output_policy.detection_short_axis_bleed),
    )


def detection_has_overlap_bleed_risk(detection: Detection) -> bool:
    overlap_bleed = detection.detail.get("overlap_bleed_risk")
    if isinstance(overlap_bleed, dict) and bool(overlap_bleed.get("risk", False)):
        return True

    lucky = detection.detail.get("lucky_pass_risk_score")
    if isinstance(lucky, dict):
        if bool(lucky.get("risk", False)):
            return True
        counts = lucky.get("overlap_risk_counts")
        if isinstance(counts, dict):
            if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                return True

    diagnostics = detection.detail.get("diagnostics")
    if isinstance(diagnostics, dict):
        summary = diagnostics.get("summary")
        if isinstance(summary, dict):
            if int(summary.get("overlap_like_model_gaps", 0) or 0) > 0:
                return True
            counts = summary.get("overlap_risk_counts")
            if isinstance(counts, dict):
                if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                    return True
    return False


def output_bleed_parameters_for_detection(
    current_bleed: AxisBleedParameters,
    detection: Detection,
    output_policy: OutputBleedPolicy,
) -> AxisBleedParameters:
    if not detection_has_overlap_bleed_risk(detection):
        return current_bleed
    target_long_axis = max(int(current_bleed.long_axis), int(output_policy.overlap_risk_long_axis_bleed))
    if target_long_axis == int(current_bleed.long_axis):
        return current_bleed
    return AxisBleedParameters(long_axis=target_long_axis, short_axis=int(current_bleed.short_axis))


def apply_output_bleed(
    detection: Detection,
    detection_bleed: AxisBleedParameters,
    output_bleed: AxisBleedParameters,
    image_w: int,
    image_h: int,
) -> None:
    if (
        int(detection_bleed.long_axis) == int(output_bleed.long_axis)
        and int(detection_bleed.short_axis) == int(output_bleed.short_axis)
    ):
        return
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    work_w = image_w if detection.layout == "horizontal" else image_h
    work_h = image_h if detection.layout == "horizontal" else image_w
    adjusted_work: list[Box] = []
    for frame in frames_work:
        raw = Box(
            frame.left + int(detection_bleed.long_axis),
            frame.top + int(detection_bleed.short_axis),
            frame.right - int(detection_bleed.long_axis),
            frame.bottom - int(detection_bleed.short_axis),
        )
        if not raw.valid():
            return
        adjusted_work.append(raw.expand(int(output_bleed.long_axis), int(output_bleed.short_axis), work_w, work_h))
    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in adjusted_work]
    detection.detail["output_bleed"] = {
        "used": True,
        "detection_long_axis_bleed": int(detection_bleed.long_axis),
        "detection_short_axis_bleed": int(detection_bleed.short_axis),
        "output_long_axis_bleed": int(output_bleed.long_axis),
        "output_short_axis_bleed": int(output_bleed.short_axis),
        "overlap_risk_long_axis_bleed": bool(detection_has_overlap_bleed_risk(detection)),
    }


def reapply_cached_output_bleed(
    detection: Detection,
    target_bleed: AxisBleedParameters,
    image_w: int,
    image_h: int,
) -> None:
    output_bleed = detection.detail.get("output_bleed")
    if not isinstance(output_bleed, dict):
        return
    try:
        cached_bleed = AxisBleedParameters(
            long_axis=int(output_bleed.get("output_long_axis_bleed", target_bleed.long_axis)),
            short_axis=int(output_bleed.get("output_short_axis_bleed", target_bleed.short_axis)),
        )
    except (TypeError, ValueError):
        return
    if cached_bleed == target_bleed:
        return
    apply_output_bleed(detection, cached_bleed, target_bleed, image_w, image_h)
    detection.detail["reused_output_bleed_adjustment"] = {
        "from_long_axis_bleed": int(cached_bleed.long_axis),
        "from_short_axis_bleed": int(cached_bleed.short_axis),
        "to_long_axis_bleed": int(target_bleed.long_axis),
        "to_short_axis_bleed": int(target_bleed.short_axis),
    }


__all__ = [
    "AxisBleedParameters",
    "apply_output_bleed",
    "detection_bleed_parameters",
    "detection_has_overlap_bleed_risk",
    "output_bleed_parameters_for_detection",
    "reapply_cached_output_bleed",
]
