from __future__ import annotations

from typing import Protocol

from ..domain import Box, FinalDetection
from ..geometry.boxes import map_work_box, original_box_to_work
from .protection import AxisBleedParameters, OutputProtectionPlan


class OutputBleedPolicy(Protocol):
    detection_long_axis_bleed: int
    detection_short_axis_bleed: int


def detection_bleed_parameters(output_policy: OutputBleedPolicy) -> AxisBleedParameters:
    return AxisBleedParameters(
        long_axis=int(output_policy.detection_long_axis_bleed),
        short_axis=int(output_policy.detection_short_axis_bleed),
    )


def apply_output_bleed(
    detection: FinalDetection,
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
            raise ValueError("output bleed cannot be applied to an invalid raw frame")
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
    }


def apply_output_protection_plan(
    detection: FinalDetection,
    detection_bleed: AxisBleedParameters,
    plan: OutputProtectionPlan,
    image_w: int,
    image_h: int,
) -> None:
    apply_output_bleed(
        detection,
        detection_bleed,
        plan.output_bleed,
        image_w,
        image_h,
    )
    detection.detail["output_protection_plan"] = {
        **plan.report_detail(),
        "applied": True,
    }


__all__ = [
    "apply_output_bleed",
    "apply_output_protection_plan",
    "detection_bleed_parameters",
]
