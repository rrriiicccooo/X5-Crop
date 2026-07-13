from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..configuration.diagnostics import DebugLegendEntry
from ..domain import Box
from ..image.constants import UINT8_MAX_VALUE
from ..utils import RGB_CHANNEL_COUNT


@dataclass
class DebugRenderCache:
    previews: dict[tuple[str, int], tuple[np.ndarray, float]] = field(
        default_factory=dict
    )
    labeled_panels: dict[tuple[str, str, int], np.ndarray] = field(
        default_factory=dict
    )


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


def preview_gray(gray: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    scale = min(1.0, float(max_side) / float(max(h, w)))
    if scale < 1.0:
        step = max(1, int(math.ceil(1.0 / scale)))
        small = gray[::step, ::step]
        actual_scale = float(small.shape[1]) / float(w)
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


def cached_labeled_preview_gray(
    cache: DebugRenderCache,
    key: str,
    label: str,
    gray: np.ndarray,
    max_side: int,
    label_height: int,
    label_origin: tuple[int, int],
    background: int,
    text_color: tuple[int, int, int],
) -> tuple[np.ndarray, float]:
    cache_key = (str(key), str(label), int(max_side))
    cached = cache.labeled_panels.get(cache_key)
    if cached is None:
        rgb, scale = cached_preview_gray(cache, key, gray, max_side)
        labeled = add_panel_label(
            rgb,
            label,
            height=label_height,
            origin=label_origin,
            background=background,
            text_color=text_color,
        )
        cache.labeled_panels[cache_key] = labeled.copy()
        return labeled, scale
    preview = cache.previews.get((str(key), int(max_side)))
    scale = float(preview[1]) if preview is not None else 1.0
    return cached.copy(), float(scale)


def draw_preview_rect(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
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
    alpha: float,
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
    blended = np.clip(
        region * (1.0 - alpha) + overlay * alpha,
        0,
        UINT8_MAX_VALUE,
    )
    rgb[top:bottom, left:right] = blended.astype(np.uint8)


def draw_preview_line(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    h, w = rgb.shape[:2]
    vertical = box.height >= box.width
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    t = max(1, int(thickness))
    if vertical:
        if bottom <= top:
            return
        x = left
        rgb[
            top:bottom,
            max(0, x - t // 2):min(w, x + (t + 1) // 2),
        ] = color
        return
    if right <= left:
        return
    y = top
    rgb[
        max(0, y - t // 2):min(h, y + (t + 1) // 2),
        left:right,
    ] = color


def draw_preview_dashed_line(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
    *,
    dash_length: int,
    dash_gap: int,
) -> None:
    h, w = rgb.shape[:2]
    vertical = box.height >= box.width
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    dash = max(1, int(dash_length))
    period = dash + max(1, int(dash_gap))
    t = max(1, int(thickness))
    if vertical:
        if bottom <= top:
            return
        x = left
        for start in range(top, bottom, period):
            rgb[
                start:min(bottom, start + dash),
                max(0, x - t // 2):min(w, x + (t + 1) // 2),
        ] = color
        return
    if right <= left:
        return
    y = top
    for start in range(left, right, period):
        rgb[
            max(0, y - t // 2):min(h, y + (t + 1) // 2),
            start:min(right, start + dash),
        ] = color


def draw_preview_dashed_rect(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
    *,
    dash_length: int,
    dash_gap: int,
) -> None:
    edges = (
        Box(box.left, box.top, box.right, box.top + 1),
        Box(box.left, box.bottom - 1, box.right, box.bottom),
        Box(box.left, box.top, box.left + 1, box.bottom),
        Box(box.right - 1, box.top, box.right, box.bottom),
    )
    for edge in edges:
        draw_preview_dashed_line(
            rgb,
            edge,
            scale,
            color,
            thickness,
            dash_length=dash_length,
            dash_gap=dash_gap,
        )


def draw_preview_mark(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    if box.width > 1 or box.height > 1:
        draw_preview_rect(rgb, box, scale, color, thickness)
    else:
        draw_preview_line(rgb, box, scale, color, thickness)


def add_panel_label(
    rgb: np.ndarray,
    label: str,
    *,
    height: int,
    origin: tuple[int, int],
    background: int,
    text_color: tuple[int, int, int],
) -> np.ndarray:
    h, w = rgb.shape[:2]
    panel = np.full(
        (h + height, w, RGB_CHANNEL_COUNT),
        background,
        dtype=np.uint8,
    )
    panel[height:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text(origin, label, fill=text_color)
    return np.asarray(image)


def add_panel_label_with_legend(
    rgb: np.ndarray,
    label: str,
    entries: tuple[DebugLegendEntry, ...],
    *,
    label_height: int,
    label_origin: tuple[int, int],
    legend_row_height: int,
    legend_sample_width: int,
    legend_text_gap: int,
    background: int,
    text_color: tuple[int, int, int],
    line_width: int,
    dash_length: int,
    dash_gap: int,
) -> np.ndarray:
    measurement_image = Image.new("RGB", (1, 1))
    measurement_draw = ImageDraw.Draw(measurement_image)
    text_widths = tuple(
        measurement_draw.textbbox((0, 0), entry.label)[2]
        for entry in entries
    )
    title_width = measurement_draw.textbbox((0, 0), label)[2]
    horizontal_margin = label_origin[0] + label_origin[0]
    required_width = max(
        title_width + horizontal_margin,
        (
            max(text_widths, default=0)
            + horizontal_margin
            + legend_sample_width
            + legend_text_gap
        ),
    )
    h, w = rgb.shape[:2]
    header_height = label_height + legend_row_height * len(entries)
    panel = np.full(
        (h + header_height, max(w, required_width), RGB_CHANNEL_COUNT),
        background,
        dtype=np.uint8,
    )
    panel[header_height:, :w, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text(label_origin, label, fill=text_color)
    sample_left = label_origin[0]
    sample_right = sample_left + legend_sample_width
    text_left = sample_right + legend_text_gap
    for index, entry in enumerate(entries):
        row_top = label_height + index * legend_row_height
        row_center = row_top + legend_row_height // 2
        if entry.dashed:
            period = dash_length + dash_gap
            for start in range(sample_left, sample_right, period):
                draw.line(
                    (
                        start,
                        row_center,
                        min(sample_right, start + dash_length),
                        row_center,
                    ),
                    fill=entry.color,
                    width=line_width,
                )
        else:
            draw.line(
                (sample_left, row_center, sample_right, row_center),
                fill=entry.color,
                width=line_width,
            )
        text_box = draw.textbbox((0, 0), entry.label)
        text_height = text_box[3] - text_box[1]
        draw.text(
            (text_left, row_top + max(0, (legend_row_height - text_height) // 2)),
            entry.label,
            fill=text_color,
        )
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
