from __future__ import annotations

from ..domain import AxisBleedParameters, Box, FinalDetection, OutputProtectionPlan
from ..geometry.boxes import map_work_box, original_box_to_work


def apply_output_bleed(
    detection: FinalDetection,
    output_bleed: AxisBleedParameters,
    image_w: int,
    image_h: int,
) -> None:
    if int(output_bleed.long_axis) == 0 and int(output_bleed.short_axis) == 0:
        return
    frames_work = [
        original_box_to_work(frame, detection.layout, image_w, image_h)
        for frame in detection.frames
    ]
    work_w = image_w if detection.layout == "horizontal" else image_h
    work_h = image_h if detection.layout == "horizontal" else image_w
    adjusted_work: list[Box] = []
    for frame in frames_work:
        adjusted_work.append(
            frame.expand(
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
def apply_output_protection_plan(
    detection: FinalDetection,
    plan: OutputProtectionPlan,
    image_w: int,
    image_h: int,
) -> None:
    apply_output_bleed(
        detection,
        plan.output_bleed,
        image_w,
        image_h,
    )
    detection.detail["output_protection_plan"] = {
        **plan.report_detail(),
        "applied": True,
    }
