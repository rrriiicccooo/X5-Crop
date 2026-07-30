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


def _blend_region(
    region: np.ndarray,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    overlay = np.array(color, dtype=np.float32)
    blended = np.clip(
        region.astype(np.float32, copy=False) * (1.0 - alpha)
        + overlay * alpha,
        0,
        UINT8_MAX_VALUE,
    )
    region[...] = blended.astype(np.uint8)


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


def fill_preview_rect(
    rgb: np.ndarray,
    box: Box,
    scale: float,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    bounds = _scaled_box(rgb, box, scale)
    if bounds is None:
        return
    left, top, right, bottom = bounds
    _blend_region(rgb[top:bottom, left:right], color, alpha)


def draw_preview_vertical_line(
    rgb: np.ndarray,
    x: float,
    top: float,
    bottom: float,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
    *,
    alpha: float = 1.0,
    dashed: bool = False,
    dash_length: int = 8,
    dash_gap: int = 5,
) -> None:
    height, width = rgb.shape[:2]
    if height <= 0 or width <= 0:
        return
    display_x = max(0, min(width - 1, int(round(x * scale))))
    display_top = max(0, min(height - 1, int(round(top * scale))))
    display_bottom = max(
        display_top + 1,
        min(height, int(round(bottom * scale))),
    )
    line_width = max(1, int(thickness))
    left = max(0, display_x - line_width // 2)
    right = min(width, left + line_width)
    if not dashed:
        _blend_region(
            rgb[display_top:display_bottom, left:right],
            color,
            alpha,
        )
        return
    dash = max(1, int(dash_length))
    period = dash + max(1, int(dash_gap))
    for start in range(display_top, display_bottom, period):
        _blend_region(
            rgb[start : min(display_bottom, start + dash), left:right],
            color,
            alpha,
        )


def _draw_display_dashed_line(
    rgb: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int,
    dash_length: int,
    dash_gap: int,
) -> None:
    image = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(image)
    start_x, start_y = start
    end_x, end_y = end
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    length = math.hypot(delta_x, delta_y)
    if length > 0.0:
        dash = max(1.0, float(dash_length))
        period = dash + max(1.0, float(dash_gap))
        offset = 0.0
        while offset < length:
            segment_end = min(length, offset + dash)
            draw.line(
                (
                    (
                        start_x + delta_x * offset / length,
                        start_y + delta_y * offset / length,
                    ),
                    (
                        start_x + delta_x * segment_end / length,
                        start_y + delta_y * segment_end / length,
                    ),
                ),
                fill=color,
                width=max(1, int(thickness)),
            )
            offset += period
    np.copyto(rgb, np.asarray(image))


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
    bounds = _scaled_box(rgb, box, scale)
    if bounds is None:
        return
    left, top, right, bottom = bounds
    right -= 1
    bottom -= 1
    for start, end in (
        ((left, top), (right, top)),
        ((left, bottom), (right, bottom)),
        ((left, top), (left, bottom)),
        ((right, top), (right, bottom)),
    ):
        _draw_display_dashed_line(
            rgb,
            start,
            end,
            color,
            thickness,
            dash_length,
            dash_gap,
        )


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
    measurement_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text_widths = tuple(
        measurement_draw.textbbox((0, 0), entry.label)[2]
        for entry in entries
    )
    title_width = measurement_draw.textbbox((0, 0), label)[2]
    horizontal_margin = label_origin[0] * 2
    required_width = max(
        title_width + horizontal_margin,
        (
            max(text_widths, default=0)
            + horizontal_margin
            + legend_sample_width
            + legend_text_gap
        ),
    )
    image_height, image_width = rgb.shape[:2]
    header_height = label_height + legend_row_height * len(entries)
    panel = np.full(
        (
            image_height + header_height,
            max(image_width, required_width),
            RGB_CHANNEL_COUNT,
        ),
        background,
        dtype=np.uint8,
    )
    panel[header_height:, :image_width, :] = rgb
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
            (
                text_left,
                row_top + max(0, (legend_row_height - text_height) // 2),
            ),
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
