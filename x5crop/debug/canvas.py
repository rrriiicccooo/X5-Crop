from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

from ..domain import Box
from ..runtime import AnalysisCache


FRAME_FILL_COLORS = (
    (30, 144, 255),
    (255, 120, 40),
    (80, 200, 120),
    (210, 90, 255),
    (255, 210, 40),
    (40, 210, 220),
    (255, 90, 120),
    (150, 170, 255),
)


def preview_gray(gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    scale = min(1.0, float(max_side) / float(max(h, w)))
    if scale < 1.0:
        step = max(1, int(math.ceil(1.0 / scale)))
        small = gray[::step, ::step]
        actual_scale = float(small.shape[1]) / float(w)
    else:
        small = gray
        actual_scale = 1.0
    rgb = np.repeat(small[..., None], 3, axis=2).astype(np.uint8, copy=False)
    return rgb, actual_scale


def cached_preview_gray(
    cache: Optional[AnalysisCache],
    key: str,
    gray: np.ndarray,
    max_side: int = 1800,
) -> tuple[np.ndarray, float]:
    if cache is None:
        return preview_gray(gray, max_side)
    cache_key = (str(key), int(max_side))
    cached = cache.preview_rgb_cache.get(cache_key)
    if cached is None:
        rgb, scale = preview_gray(gray, max_side)
        cache.preview_rgb_cache[cache_key] = (rgb.copy(), float(scale))
        return rgb, scale
    rgb, scale = cached
    return rgb.copy(), float(scale)


def cached_labeled_preview_gray(
    cache: Optional[AnalysisCache],
    key: str,
    label: str,
    gray: np.ndarray,
    max_side: int = 1800,
) -> tuple[np.ndarray, float]:
    if cache is None:
        rgb, scale = preview_gray(gray, max_side)
        return add_panel_label(rgb, label), scale
    cache_key = (str(key), str(label), int(max_side))
    cached = cache.panel_label_cache.get(cache_key)
    if cached is None:
        rgb, scale = cached_preview_gray(cache, key, gray, max_side)
        labeled = add_panel_label(rgb, label)
        cache.panel_label_cache[cache_key] = labeled.copy()
        return labeled, scale
    preview = cache.preview_rgb_cache.get((str(key), int(max_side)))
    scale = float(preview[1]) if preview is not None else 1.0
    return cached.copy(), float(scale)


def draw_preview_rect(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:min(bottom, top + t), left:right] = color
    rgb[max(top, bottom - t):bottom, left:right] = color
    rgb[top:bottom, left:min(right, left + t)] = color
    rgb[top:bottom, max(left, right - t):right] = color


def fill_preview_rect(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    alpha: float = 0.24,
) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    overlay = np.array(color, dtype=np.float32)
    region = rgb[top:bottom, left:right].astype(np.float32, copy=False)
    blended = np.clip(region * (1.0 - alpha) + overlay * alpha, 0, 255)
    rgb[top:bottom, left:right] = blended.astype(np.uint8)


def draw_preview_line(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    h, w = rgb.shape[:2]
    x = max(0, min(w - 1, int(round(box.left * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:bottom, max(0, x - t // 2):min(w, x + (t + 1) // 2)] = color


def draw_preview_hline(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    h, w = rgb.shape[:2]
    y = max(0, min(h - 1, int(round(box.top * scale))))
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    if right <= left:
        return
    t = max(1, int(thickness))
    rgb[max(0, y - t // 2):min(h, y + (t + 1) // 2), left:right] = color


def draw_preview_mark(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    if box.width > 1 or box.height > 1:
        draw_preview_rect(rgb, box, scale, color, thickness)
    else:
        draw_preview_line(rgb, box, scale, color, thickness)


def add_panel_label(rgb: np.ndarray, label: str) -> np.ndarray:
    label_h = 34
    h, w = rgb.shape[:2]
    panel = np.full((h + label_h, w, 3), 18, dtype=np.uint8)
    panel[label_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text((12, 9), label, fill=(245, 245, 245))
    return np.asarray(image)


def write_rgb_jpeg(rgb: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    image.save(output_path, format="JPEG", quality=92, optimize=True)

