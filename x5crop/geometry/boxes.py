from __future__ import annotations

from ..domain import Box
from .layout import is_horizontal_layout


def translate_box(box: Box, offset_x: int, offset_y: int) -> Box:
    return Box(
        box.left + offset_x,
        box.top + offset_y,
        box.right + offset_x,
        box.bottom + offset_y,
    )


def map_work_box(box: Box, layout: str, width: int, height: int) -> Box:
    if is_horizontal_layout(layout):
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(width, height)


def original_box_to_work(box: Box, layout: str, width: int, height: int) -> Box:
    if is_horizontal_layout(layout):
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(height, width)
