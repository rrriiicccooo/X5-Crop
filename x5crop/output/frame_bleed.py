from __future__ import annotations

from ..domain import AxisBleedParameters, Box, CropEnvelope
from ..geometry.boxes import map_work_box, original_box_to_work
from .model import (
    BoundaryOverlapProtection,
    FrameBleedPlan,
    FrameOverlapRequirement,
    FrameSideBleed,
    OutputGeometry,
)

def _long_axis_capacity(
    frame: Box,
    envelope: CropEnvelope,
    *,
    leading: bool,
    horizontal: bool,
) -> int:
    box = envelope.box
    if horizontal:
        return (
            max(0, frame.left - box.left)
            if leading
            else max(0, box.right - frame.right)
        )
    return (
        max(0, frame.top - box.top)
        if leading
        else max(0, box.bottom - frame.bottom)
    )


def frame_bleed_plan(
    *,
    frames: tuple[Box, ...],
    frame_crop_envelopes: tuple[CropEnvelope, ...],
    overlap_requirements: tuple[FrameOverlapRequirement, ...],
    user_bleed: AxisBleedParameters,
    layout: str,
) -> FrameBleedPlan:
    if len(frame_crop_envelopes) != len(frames):
        raise ValueError("each frame requires one crop envelope")
    horizontal = layout == "horizontal"
    leading = [int(user_bleed.long_axis) for _frame in frames]
    trailing = [int(user_bleed.long_axis) for _frame in frames]
    protections: list[BoundaryOverlapProtection] = []
    unresolved: list[int] = []

    for requirement in overlap_requirements:
        if requirement.right_frame_index >= len(frames):
            raise ValueError("overlap requirement references a missing frame")
        if not requirement.physically_supported:
            unresolved.append(requirement.boundary_index)
            continue
        left_index = requirement.left_frame_index
        right_index = requirement.right_frame_index
        left_capacity = _long_axis_capacity(
            frames[left_index],
            frame_crop_envelopes[left_index],
            leading=False,
            horizontal=horizontal,
        )
        right_capacity = _long_axis_capacity(
            frames[right_index],
            frame_crop_envelopes[right_index],
            leading=True,
            horizontal=horizontal,
        )
        protection = BoundaryOverlapProtection(
            boundary_index=requirement.boundary_index,
            left_frame_index=left_index,
            right_frame_index=right_index,
            required_px=requirement.required_px,
            left_trailing_available_px=left_capacity,
            right_leading_available_px=right_capacity,
            provenance=requirement.provenance,
        )
        protections.append(protection)
        trailing[left_index] = max(trailing[left_index], requirement.required_px)
        leading[right_index] = max(leading[right_index], requirement.required_px)
        if not protection.complete:
            unresolved.append(requirement.boundary_index)

    unresolved_boundaries = tuple(dict.fromkeys(unresolved))
    return FrameBleedPlan(
        user_bleed=user_bleed,
        frame_sides=tuple(
            FrameSideBleed(
                frame_index=index,
                leading_px=leading[index],
                trailing_px=trailing[index],
                short_axis_px=int(user_bleed.short_axis),
            )
            for index in range(len(frames))
        ),
        overlap_protection=tuple(protections),
        unresolved_overlap_boundaries=unresolved_boundaries,
        feasible=not unresolved_boundaries,
        reason=(
            "output_overlap_protected"
            if protections and not unresolved_boundaries
            else "output_overlap_unresolved"
            if unresolved_boundaries
            else "no_output_overlap"
        ),
    )


def _expand_frame(
    frame: Box,
    *,
    leading_px: int,
    trailing_px: int,
    short_axis_px: int,
    envelope: Box,
) -> Box:
    return Box(
        max(envelope.left, frame.left - leading_px),
        max(envelope.top, frame.top - short_axis_px),
        min(envelope.right, frame.right + trailing_px),
        min(envelope.bottom, frame.bottom + short_axis_px),
    )


def apply_frame_bleed(
    geometry: OutputGeometry,
    frame_bleed_plan: FrameBleedPlan,
    *,
    layout: str,
    image_width: int,
    image_height: int,
) -> OutputGeometry:
    if len(frame_bleed_plan.frame_sides) != len(geometry.frames):
        raise ValueError("frame bleed plan does not match output geometry")
    if tuple(side.frame_index for side in frame_bleed_plan.frame_sides) != tuple(
        range(len(geometry.frames))
    ):
        raise ValueError("frame bleed plan indexes must match output frames")
    work_width = image_width if layout == "horizontal" else image_height
    work_height = image_height if layout == "horizontal" else image_width
    work_envelope = original_box_to_work(
        geometry.crop_envelope.box,
        layout,
        image_width,
        image_height,
    ).clamp(work_width, work_height)
    frames = tuple(
        _expand_frame(
            original_box_to_work(frame, layout, image_width, image_height),
            leading_px=side.leading_px,
            trailing_px=side.trailing_px,
            short_axis_px=side.short_axis_px,
            envelope=work_envelope,
        )
        for frame, side in zip(
            geometry.frames,
            frame_bleed_plan.frame_sides,
            strict=True,
        )
    )
    return OutputGeometry(
        crop_envelope=geometry.crop_envelope,
        frames=tuple(
            map_work_box(frame, layout, image_width, image_height)
            for frame in frames
        ),
    )
