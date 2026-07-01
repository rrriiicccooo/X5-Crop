from __future__ import annotations

import numpy as np

from ..domain import Box


def box_cache_key(box: Box) -> tuple[int, int, int, int]:
    return (int(box.left), int(box.top), int(box.right), int(box.bottom))


def format_box_cache_key(format_name: str, box: Box) -> tuple[str, int, int, int, int]:
    return (str(format_name), int(box.left), int(box.top), int(box.right), int(box.bottom))


def full_work_box(gray_work: np.ndarray) -> Box:
    return Box(0, 0, gray_work.shape[1], gray_work.shape[0])


def is_full_work_box(gray_work: np.ndarray, box: Box) -> bool:
    full = full_work_box(gray_work)
    return box_cache_key(box.clamp(gray_work.shape[1], gray_work.shape[0])) == box_cache_key(full)


def crop_work_outer(gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if not outer.valid():
        return gray_work
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    return crop if crop.size else gray_work


def map_work_box(box: Box, layout: str, width: int, height: int) -> Box:
    if layout == "horizontal":
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(width, height)


def original_box_to_work(box: Box, layout: str, width: int, height: int) -> Box:
    if layout == "horizontal":
        return box.clamp(width, height)
    return Box(box.top, box.left, box.bottom, box.right).clamp(height, width)
