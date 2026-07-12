from __future__ import annotations

import numpy as np

from ..domain import Box
from .layout import is_horizontal_layout


def box_cache_key(box: Box) -> tuple[int, int, int, int]:
    return (int(box.left), int(box.top), int(box.right), int(box.bottom))


def full_work_box(gray_work: np.ndarray) -> Box:
    return Box(0, 0, gray_work.shape[1], gray_work.shape[0])


def is_full_work_box(gray_work: np.ndarray, box: Box) -> bool:
    full = full_work_box(gray_work)
    return box_cache_key(box.clamp(gray_work.shape[1], gray_work.shape[0])) == box_cache_key(full)


def crop_work_box(gray_work: np.ndarray, box: Box) -> np.ndarray:
    if not box.valid():
        return gray_work
    crop = gray_work[box.top:box.bottom, box.left:box.right]
    return crop if crop.size else gray_work


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
