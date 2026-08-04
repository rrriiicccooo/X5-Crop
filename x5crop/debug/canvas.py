from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..domain import Box
from ..utils import RGB_CHANNEL_COUNT


FRAME_FILL_COLORS = (
    (30, 144, 255),
    (255, 120, 40),
    (80, 200, 120),
    (210, 90, 255),
    (255, 210, 40),
    (40, 210, 220),
    (255, 90, 120),
    (150, 170, 255),
    (180, 120, 60),
    (120, 220, 60),
    (255, 160, 190),
    (70, 110, 210),
)


@dataclass
class DebugRenderCache:
    previews: dict[tuple[str, int], tuple[np.ndarray, float]] = field(
        default_factory=dict
    )


def preview_gray(gray: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    height, width = gray.shape
    scale = min(1.0, float(max_side) / float(max(height, width)))
    if scale < 1.0:
        step = max(1, int(math.ceil(1.0 / scale)))
        small = gray[::step, ::step]
        actual_scale = float(small.shape[1]) / float(width)
    else:
        small = gray
        actual_scale = 1.0
    rgb = np.repeat(
        small[..., None],
        RGB_CHANNEL_COUNT,
        axis=2,
    ).astype(np.uint8, copy=False)
    return rgb, actual_scale


def cached_preview_gray(
    cache: DebugRenderCache,
    key: str,
    gray: np.ndarray,
    max_side: int,
) -> tuple[np.ndarray, float]:
    cache_key = (str(key), int(max_side))
    cached = cache.previews.get(cache_key)
    if cached is None:
        rgb, scale = preview_gray(gray, max_side)
        cache.previews[cache_key] = (rgb.copy(), float(scale))
        return rgb, scale
    rgb, scale = cached
    return rgb.copy(), float(scale)


def _scaled_box(
    rgb: np.ndarray,
    box: Box,
    scale: float,
) -> tuple[int, int, int, int] | None:
    height, width = rgb.shape[:2]
    if height <= 0 or width <= 0 or not box.valid():
        return None
    left = max(0, min(width - 1, int(round(box.left * scale))))
    right = max(left + 1, min(width, int(round(box.right * scale))))
    top = max(0, min(height - 1, int(round(box.top * scale))))
    bottom = max(top + 1, min(height, int(round(box.bottom * scale))))
    return left, top, right, bottom


def draw_preview_rect(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    bounds = _scaled_box(rgb, box, scale)
    if bounds is None:
        return
    left, top, right, bottom = bounds
    line_width = max(1, int(thickness))
    rgb[top : min(bottom, top + line_width), left:right] = color
    rgb[max(top, bottom - line_width) : bottom, left:right] = color
    rgb[top:bottom, left : min(right, left + line_width)] = color
    rgb[top:bottom, max(left, right - line_width) : right] = color


def draw_preview_label(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    text: str,
    color: tuple[int, int, int],
    *,
    inset: int,
    stroke_width: int,
) -> None:
    bounds = _scaled_box(rgb, box, scale)
    if bounds is None:
        return
    left, top, _right, _bottom = bounds
    image = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text(
        (left + inset, top + inset),
        text,
        fill=color,
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0),
    )
    np.copyto(rgb, np.asarray(image))


def add_panel_label(
    rgb: np.ndarray,
    label: str,
    *,
    height: int,
    origin: tuple[int, int],
    background: int,
    text_color: tuple[int, int, int],
) -> np.ndarray:
    image_height, image_width = rgb.shape[:2]
    panel = np.full(
        (image_height + height, image_width, RGB_CHANNEL_COUNT),
        background,
        dtype=np.uint8,
    )
    panel[height:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    ImageDraw.Draw(image).text(origin, label, fill=text_color)
    return np.asarray(image)


def write_rgb_jpeg(
    rgb: np.ndarray,
    output_path: Path,
    *,
    quality: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    image.save(output_path, format="JPEG", quality=quality, optimize=True)
