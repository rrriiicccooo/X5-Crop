"""Compose the three read-only Debug Analysis panels."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ..configuration.diagnostics import (
    DebugLegendEntry,
    DebugStyleParameters,
    DiagnosticsConfiguration,
)
from ..configuration.model import DetectionConfiguration
from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from ..io.model import ImageProfile
from ..run_status import RunTerminalOutcome
from ..utils import RGB_CHANNEL_COUNT
from .axis_panels import cross_axis_panel, long_axis_panel
from .canvas import DebugRenderCache
from .output_panel import protected_output_panel
from .panel_facts import source_projection
from .panel_layout import (
    PresentationGrid,
    draw_dashed_polyline,
    font,
    presentation_grid,
    text_width,
)
from .status import add_status_bar


def stack_debug_panels(
    panels: tuple[np.ndarray, ...],
    *,
    style: DebugStyleParameters,
    grid: PresentationGrid,
) -> np.ndarray:
    expected_heights = (
        grid.cross_axis_panel_height,
        grid.long_axis_panel_height,
        grid.output_panel_height,
    )
    panel_width = style.canvas_width - 2 * style.outer_margin
    if len(panels) != len(expected_heights) or any(
        panel.shape != (height, panel_width, RGB_CHANNEL_COUNT)
        for panel, height in zip(panels, expected_heights, strict=True)
    ):
        raise ValueError("Debug Analysis panels do not match the adaptive grid")
    body_height = sum(expected_heights) + style.panel_gap * 2
    body = np.full(
        (body_height, style.canvas_width, RGB_CHANNEL_COUNT),
        style.canvas_background,
        dtype=np.uint8,
    )
    top = 0
    for panel in panels:
        height = panel.shape[0]
        body[
            top : top + height,
            style.outer_margin : style.canvas_width - style.outer_margin,
        ] = panel
        top += height + style.panel_gap
    return body


def add_legend_bar(
    rgb: np.ndarray,
    entries: tuple[DebugLegendEntry, ...],
    style: DebugStyleParameters,
) -> np.ndarray:
    if rgb.shape[1] != style.canvas_width:
        raise ValueError("Debug Analysis legend width is not canonical")
    height = rgb.shape[0]
    panel = np.full(
        (
            height + style.legend_bar_height,
            style.canvas_width,
            RGB_CHANNEL_COUNT,
        ),
        style.canvas_background,
        dtype=np.uint8,
    )
    panel[:height] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    legend_font = font(style.legend_font_size)
    widths = tuple(
        38 + 9 + text_width(draw, entry.label, legend_font) + 20
        for entry in entries
    )
    scale = min(1.0, (style.canvas_width - 48) / max(1, sum(widths)))
    x = 31.0
    center_y = height + style.legend_bar_height / 2.0
    for entry, natural_width in zip(entries, widths, strict=True):
        sample_width = max(23, int(round(38 * scale)))
        left = int(round(x))
        right = left + sample_width
        top = int(round(center_y - 9))
        bottom = int(round(center_y + 9))
        if entry.sample == "solid":
            draw.line(
                (left, center_y, right, center_y),
                fill=entry.color,
                width=2,
            )
        elif entry.sample == "dashed":
            draw_dashed_polyline(
                draw,
                ((left, center_y), (right, center_y)),
                entry.color,
                2,
                style.line_dash_length,
                style.line_dash_gap,
                closed=False,
            )
        else:
            draw.rectangle(
                (left, top, right, bottom),
                outline=entry.color,
                width=1,
            )
            if entry.sample == "hatched":
                for offset in range(left - 12, right + 12, 5):
                    draw.line(
                        (offset, bottom, offset + 18, top),
                        fill=entry.color,
                        width=1,
                    )
        text_x = right + max(6, int(round(9 * scale)))
        draw.text(
            (text_x, center_y - 7),
            entry.label,
            fill=style.secondary_text_color,
            font=legend_font,
        )
        x += natural_width * scale
    return np.asarray(image)


def make_debug_analysis_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    configuration: DetectionConfiguration,
    profile: ImageProfile,
    source_name: str,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    style = diagnostics.style
    grid = presentation_grid(source_projection(workspace), style)
    panels = (
        cross_axis_panel(workspace, detection, style, render_cache, grid),
        long_axis_panel(workspace, detection, style, render_cache, grid),
        protected_output_panel(
            workspace, detection, style, render_cache, grid
        ),
    )
    canvas = stack_debug_panels(panels, style=style, grid=grid)
    canvas = add_legend_bar(canvas, diagnostics.legend_entries, style)
    canvas = add_status_bar(
        canvas,
        detection,
        configuration,
        profile,
        source_name,
        style,
        terminal_outcome,
    )
    if canvas.shape != (
        grid.canvas_height,
        style.canvas_width,
        RGB_CHANNEL_COUNT,
    ):
        raise ValueError(
            "Debug Analysis output does not match the adaptive design canvas"
        )
    return canvas
