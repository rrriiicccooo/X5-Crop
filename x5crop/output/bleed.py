from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain import Box, Detection
from ..geometry.boxes import map_work_box, original_box_to_work


class OutputBleedPolicy(Protocol):
    detection_long_axis_bleed: int
    detection_short_axis_bleed: int
    output_overlap_long_axis_bleed_capacity: int


@dataclass(frozen=True)
class AxisBleedParameters:
    long_axis: int
    short_axis: int


def detection_bleed_parameters(output_policy: OutputBleedPolicy) -> AxisBleedParameters:
    return AxisBleedParameters(
        long_axis=int(output_policy.detection_long_axis_bleed),
        short_axis=int(output_policy.detection_short_axis_bleed),
    )


def detection_has_output_overlap_evidence(detection: Detection) -> bool:
    output_overlap = detection.detail.get("output_overlap_evidence")
    if not isinstance(output_overlap, dict):
        return False
    if bool(output_overlap.get("output_overlap_unresolved", False)):
        return False
    if (
        bool(output_overlap.get("output_overlap_protected_by_bleed", False))
        and required_output_overlap_bleed_px(detection) > 0
    ):
        return True
    return False


def required_output_overlap_bleed_px(detection: Detection) -> int:
    output_overlap = detection.detail.get("output_overlap_evidence")
    if not isinstance(output_overlap, dict):
        return 0
    try:
        required = int(output_overlap["required_output_bleed_px"])
    except (KeyError, TypeError, ValueError):
        return 0
    return max(0, required)


def output_bleed_parameters_for_detection(
    current_bleed: AxisBleedParameters,
    detection: Detection,
    output_policy: OutputBleedPolicy,
) -> AxisBleedParameters:
    if not detection_has_output_overlap_evidence(detection):
        return current_bleed
    required_bleed = required_output_overlap_bleed_px(detection)
    target_long_axis = max(
        int(current_bleed.long_axis),
        min(
            int(output_policy.output_overlap_long_axis_bleed_capacity),
            int(required_bleed),
        ),
    )
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
    frames_work = [
        original_box_to_work(frame, detection.layout, image_w, image_h)
        for frame in detection.frames
    ]
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
        adjusted_work.append(
            raw.expand(
                int(output_bleed.long_axis),
                int(output_bleed.short_axis),
                work_w,
                work_h,
            )
        )
    detection.frames = [
        map_work_box(frame, detection.layout, image_w, image_h)
        for frame in adjusted_work
    ]
    detection.detail["output_bleed"] = {
        "used": True,
        "detection_long_axis_bleed": int(detection_bleed.long_axis),
        "detection_short_axis_bleed": int(detection_bleed.short_axis),
        "output_long_axis_bleed": int(output_bleed.long_axis),
        "output_short_axis_bleed": int(output_bleed.short_axis),
        "output_overlap_protected_by_bleed": bool(
            detection_has_output_overlap_evidence(detection)
        ),
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
            long_axis=int(
                output_bleed.get("output_long_axis_bleed", target_bleed.long_axis)
            ),
            short_axis=int(
                output_bleed.get("output_short_axis_bleed", target_bleed.short_axis)
            ),
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
    "detection_has_output_overlap_evidence",
    "output_bleed_parameters_for_detection",
    "required_output_overlap_bleed_px",
    "reapply_cached_output_bleed",
]
