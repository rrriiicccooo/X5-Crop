from __future__ import annotations

from ..domain import (
    Box,
    InterFrameBoundaryReference,
)
from ..geometry.boxes import map_work_box, original_box_to_work
from ..geometry.layout import is_horizontal_layout
from .model import (
    AxisBleedParameters,
    BoundaryOverlapProtection,
    FrameBleedPlan,
    FrameOverlapRequirement,
    FrameSideBleed,
    OutputGeometry,
)


def _long_axis_capacity(
    frame: Box,
    output_bound: Box,
    *,
    leading: bool,
    horizontal: bool,
) -> int:
    if horizontal:
        return (
            max(0, frame.left - output_bound.left)
            if leading
            else max(0, output_bound.right - frame.right)
        )
    return (
        max(0, frame.top - output_bound.top)
        if leading
        else max(0, output_bound.bottom - frame.bottom)
    )


def frame_bleed_plan(
    *,
    frames: tuple[Box, ...],
    frame_output_bounds: tuple[Box, ...],
    overlap_requirements: tuple[FrameOverlapRequirement, ...],
    user_bleed: AxisBleedParameters,
    layout: str,
) -> FrameBleedPlan:
    if len(frame_output_bounds) != len(frames):
        raise ValueError("each frame requires one output bound")
    if any(
        not bound.valid()
        or frame.left < bound.left
        or frame.top < bound.top
        or frame.right > bound.right
        or frame.bottom > bound.bottom
        for frame, bound in zip(frames, frame_output_bounds, strict=True)
    ):
        raise ValueError("frame output bounds must contain their frames")
    horizontal = is_horizontal_layout(layout)
    leading = [int(user_bleed.long_axis) for _frame in frames]
    trailing = [int(user_bleed.long_axis) for _frame in frames]
    protections: list[BoundaryOverlapProtection] = []
    unresolved: list[InterFrameBoundaryReference] = []

    for requirement in overlap_requirements:
        if requirement.right_frame_index >= len(frames):
            raise ValueError("overlap requirement references a missing frame")
        if not requirement.physically_supported:
            unresolved.append(requirement.boundary)
            continue
        left_index = requirement.left_frame_index
        right_index = requirement.right_frame_index
        left_capacity = _long_axis_capacity(
            frames[left_index],
            frame_output_bounds[left_index],
            leading=False,
            horizontal=horizontal,
        )
        right_capacity = _long_axis_capacity(
            frames[right_index],
            frame_output_bounds[right_index],
            leading=True,
            horizontal=horizontal,
        )
        protection = BoundaryOverlapProtection(
            requirement=requirement,
            left_trailing_available_px=left_capacity,
            right_leading_available_px=right_capacity,
        )
        protections.append(protection)
        trailing[left_index] = max(trailing[left_index], requirement.required_px)
        leading[right_index] = max(leading[right_index], requirement.required_px)
        if not protection.complete:
            unresolved.append(requirement.boundary)

    unresolved_boundaries = tuple(dict.fromkeys(unresolved))
    return FrameBleedPlan(
        user_bleed=user_bleed,
        frame_output_bounds=frame_output_bounds,
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
    envelopes = geometry.frame_crop_envelopes
    if len(frame_bleed_plan.frame_sides) != len(envelopes):
        raise ValueError("frame bleed plan does not match output geometry")
    if tuple(side.frame_index for side in frame_bleed_plan.frame_sides) != tuple(
        range(len(envelopes))
    ):
        raise ValueError("frame bleed plan indexes must match output frames")
    if len(frame_bleed_plan.frame_output_bounds) != len(envelopes):
        raise ValueError("frame output bounds do not match output geometry")
    work_frames = tuple(
        _expand_frame(
            original_box_to_work(
                envelope.box,
                layout,
                image_width,
                image_height,
            ),
            leading_px=side.leading_px,
            trailing_px=side.trailing_px,
            short_axis_px=side.short_axis_px,
            envelope=bound,
        )
        for envelope, side, bound in zip(
            envelopes,
            frame_bleed_plan.frame_sides,
            frame_bleed_plan.frame_output_bounds,
            strict=True,
        )
    )
    if not work_frames:
        return geometry
    frames = tuple(
        map_work_box(frame, layout, image_width, image_height)
        for frame in work_frames
    )
    return OutputGeometry(
        frame_crop_envelopes=geometry.frame_crop_envelopes,
        final_boxes=frames,
    )
