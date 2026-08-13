"""Shared drawing geometry for Debug Analysis panels."""

from __future__ import annotations

from dataclasses import dataclass
import math

from PIL import Image, ImageDraw, ImageFont

from ..configuration.diagnostics import DebugStyleParameters
from ..detection.photo_geometry.model import BoundaryAxis
from .canvas import FRAME_FILL_COLORS


@dataclass(frozen=True)
class Projection:
    source_width: int
    source_height: int
    rotate_clockwise: bool

    @property
    def display_width(self) -> int:
        return self.source_height if self.rotate_clockwise else self.source_width

    @property
    def display_height(self) -> int:
        return self.source_width if self.rotate_clockwise else self.source_height

    def point(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        if self.rotate_clockwise:
            return float(self.source_height) - y, x
        return x, y


@dataclass(frozen=True)
class Viewport:
    projection: Projection
    source_box: tuple[int, int, int, int]
    target_box: tuple[int, int, int, int]

    def point(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = self.projection.point(point)
        source_left, source_top, source_right, source_bottom = self.source_box
        target_left, target_top, target_right, target_bottom = self.target_box
        return (
            target_left
            + (x - source_left)
            * (target_right - target_left)
            / (source_right - source_left),
            target_top
            + (y - source_top)
            * (target_bottom - target_top)
            / (source_bottom - source_top),
        )

    def polygon(
        self,
        polygon: tuple[tuple[float, float], ...],
    ) -> tuple[tuple[float, float], ...]:
        return tuple(self.point(point) for point in polygon)


@dataclass(frozen=True)
class PresentationGrid:
    media_height: int
    cross_axis_panel_height: int
    long_axis_panel_height: int
    output_panel_height: int
    canvas_height: int


def presentation_grid(
    projection: Projection,
    style: DebugStyleParameters,
) -> PresentationGrid:
    panel_width = style.canvas_width - 2 * style.outer_margin
    media_width = panel_width - 2 * style.panel_media_inset_x
    media_height = max(
        1,
        int(
            round(
                media_width
                * projection.display_height
                / projection.display_width
            )
        ),
    )
    cross_axis_panel_height = (
        style.cross_axis_media_top
        + media_height
        + style.cross_axis_media_bottom_padding
    )
    long_axis_panel_height = (
        style.long_axis_media_top
        + media_height
        + style.long_axis_media_bottom_padding
    )
    output_panel_height = (
        style.output_media_top
        + media_height
        + style.output_media_bottom_padding
    )
    canvas_height = (
        style.status_bar_height
        + cross_axis_panel_height
        + long_axis_panel_height
        + output_panel_height
        + 2 * style.panel_gap
        + style.legend_bar_height
    )
    return PresentationGrid(
        media_height=media_height,
        cross_axis_panel_height=cross_axis_panel_height,
        long_axis_panel_height=long_axis_panel_height,
        output_panel_height=output_panel_height,
        canvas_height=canvas_height,
    )


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    selected_font: ImageFont.ImageFont,
) -> int:
    bounds = draw.textbbox((0, 0), text, font=selected_font)
    return bounds[2] - bounds[0]


def frame_color(global_ordinal: int) -> tuple[int, int, int]:
    if not 1 <= global_ordinal <= len(FRAME_FILL_COLORS):
        raise ValueError("Debug Analysis frame ordinal exceeds the fixed color table")
    return FRAME_FILL_COLORS[global_ordinal - 1]


def panel_base(
    width: int,
    height: int,
    title: str,
    right_title: str,
    style: DebugStyleParameters,
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    panel = Image.new("RGB", (width, height), style.panel_background)
    draw = ImageDraw.Draw(panel)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=style.panel_border_color,
        width=1,
    )
    draw.line(
        ((1, style.panel_title_height), (width - 2, style.panel_title_height)),
        fill=style.divider_color,
        width=1,
    )
    title_font = font(style.title_font_size)
    draw.text((16, 11), title, fill=style.text_color, font=title_font)
    right_width = text_width(draw, right_title, title_font)
    draw.text(
        (width - right_width - 17, 11),
        right_title,
        fill=style.secondary_text_color,
        font=title_font,
    )
    return panel, draw


def viewport(
    projection: Projection,
    target_box: tuple[int, int, int, int],
) -> Viewport:
    return Viewport(
        projection,
        (0, 0, projection.display_width, projection.display_height),
        target_box,
    )


def paste_source(
    panel: Image.Image,
    source: Image.Image,
    selected_viewport: Viewport,
) -> None:
    left, top, right, bottom = selected_viewport.target_box
    crop = source.crop(selected_viewport.source_box).resize(
        (right - left, bottom - top),
        Image.Resampling.LANCZOS,
    )
    panel.paste(crop, (left, top))


def draw_dashed_polyline(
    draw: ImageDraw.ImageDraw,
    points: tuple[tuple[float, float], ...],
    color: tuple[int, int, int],
    width: int,
    dash_length: int,
    dash_gap: int,
    *,
    closed: bool,
) -> None:
    if len(points) < 2:
        return
    path = points + ((points[0],) if closed else ())
    period = float(dash_length + dash_gap)
    for start, end in zip(path, path[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy)
        if distance <= 1.0e-9:
            continue
        cursor = 0.0
        while cursor < distance:
            stop = min(distance, cursor + dash_length)
            draw.line(
                (
                    (
                        start[0] + dx * cursor / distance,
                        start[1] + dy * cursor / distance,
                    ),
                    (
                        start[0] + dx * stop / distance,
                        start[1] + dy * stop / distance,
                    ),
                ),
                fill=color,
                width=width,
            )
            cursor += period


def clip_segment_to_box(
    start: tuple[float, float],
    end: tuple[float, float],
    box: tuple[int, int, int, int],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    left, top, right, bottom = (float(value) for value in box)
    x0, y0 = start
    dx = end[0] - x0
    dy = end[1] - y0
    lower = 0.0
    upper = 1.0
    for direction, distance in (
        (-dx, x0 - left),
        (dx, right - x0),
        (-dy, y0 - top),
        (dy, bottom - y0),
    ):
        if abs(direction) <= 1.0e-12:
            if distance < 0.0:
                return None
            continue
        ratio = distance / direction
        if direction < 0.0:
            if ratio > upper:
                return None
            lower = max(lower, ratio)
        else:
            if ratio < lower:
                return None
            upper = min(upper, ratio)
    return (
        (x0 + lower * dx, y0 + lower * dy),
        (x0 + upper * dx, y0 + upper * dy),
    )


def fill_polygon(
    draw: ImageDraw.ImageDraw,
    polygon: tuple[tuple[float, float], ...],
    color: tuple[int, int, int],
    alpha: float,
    *,
    selected_viewport: Viewport | None = None,
) -> None:
    if len(polygon) >= 3:
        target = (
            selected_viewport.polygon(polygon)
            if selected_viewport is not None
            else polygon
        )
        draw.polygon(target, fill=(*color, int(round(255.0 * alpha))))


def source_line_points(observation: object) -> tuple[tuple[float, float], ...]:
    line = observation.line
    support = line.support_projection_px
    if line.source_axis_long == BoundaryAxis.X:
        if abs(line.normal_y) <= 1.0e-12:
            return ()
        return (
            (
                support.minimum,
                (line.offset_px - line.normal_x * support.minimum) / line.normal_y,
            ),
            (
                support.maximum,
                (line.offset_px - line.normal_x * support.maximum) / line.normal_y,
            ),
        )
    if abs(line.normal_x) <= 1.0e-12:
        return ()
    return (
        (
            (line.offset_px - line.normal_y * support.minimum) / line.normal_x,
            support.minimum,
        ),
        (
            (line.offset_px - line.normal_y * support.maximum) / line.normal_x,
            support.maximum,
        ),
    )


def draw_label_chip(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    style: DebugStyleParameters,
    *,
    filled: bool = True,
) -> None:
    selected_font = font(style.frame_label_font_size)
    x, y = xy
    width = text_width(draw, text, selected_font) + 10
    bounds = (x, y, x + width, y + 22)
    if filled:
        draw.rounded_rectangle(bounds, radius=3, fill=color)
        text_color = (255, 255, 255)
    else:
        draw.rounded_rectangle(
            bounds,
            radius=3,
            fill=style.panel_background,
            outline=color,
            width=1,
        )
        text_color = color
    draw.text((x + 5, y + 3), text, fill=text_color, font=selected_font)
