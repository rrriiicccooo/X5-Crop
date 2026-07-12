from __future__ import annotations

from typing import Any

import numpy as np

from ..detection.decision.model import FinalDetection
from ..image.evidence import (
    SeparatorEvidenceImageParameters,
    make_separator_evidence_gray,
)
from ..configuration.diagnostics import (
    DebugStyleParameters,
    DiagnosticsConfiguration,
)
from .canvas import (
    DebugRenderCache,
    FRAME_FILL_COLORS,
    add_panel_label,
    cached_labeled_preview_gray,
    cached_preview_gray,
    draw_preview_rect,
    fill_preview_rect,
)
from .separators import draw_separator_overlay
from .status import add_status_bar


def make_debug_preview_rgb(
    gray: np.ndarray,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = cached_preview_gray(
        render_cache,
        "original_gray",
        gray,
        style.preview_max_side,
    )
    for index, box in enumerate(detection.output_geometry.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, style.frame_fill_alpha)
        draw_preview_rect(rgb, box, scale, color, style.frame_line_width)
    draw_preview_rect(
        rgb,
        detection.output_geometry.crop_envelope.box,
        scale,
        style.crop_envelope_color,
        style.crop_envelope_line_width,
    )
    return rgb


def draw_evidence_context_overlay(
    rgb: np.ndarray,
    detection: FinalDetection,
    scale: float,
    style: DebugStyleParameters,
    include_frames: bool = False,
) -> None:
    draw_preview_rect(
        rgb,
        detection.output_geometry.crop_envelope.box,
        scale,
        style.crop_envelope_color,
        style.evidence_envelope_line_width,
    )
    if include_frames:
        for index, box in enumerate(detection.output_geometry.frames):
            color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
            draw_preview_rect(rgb, box, scale, color, style.frame_line_width)


def make_separator_evidence_debug_gray(
    gray: np.ndarray,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    return make_separator_evidence_gray(gray, params)


def make_separator_evidence_debug_rgb(
    gray: np.ndarray,
    detection: FinalDetection,
    separator_overlay: Any,
    params: SeparatorEvidenceImageParameters,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    evidence = make_separator_evidence_debug_gray(
        gray,
        params,
    )
    rgb, scale = cached_preview_gray(
        render_cache,
        "separator_evidence_full",
        evidence,
        style.preview_max_side,
    )
    draw_evidence_context_overlay(rgb, detection, scale, style)
    draw_separator_overlay(rgb, detection, scale, separator_overlay, style)
    return rgb


def make_debug_analysis_panel(
    gray: np.ndarray,
    detection: FinalDetection,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    separator_overlay = diagnostics.separator_overlay
    style = diagnostics.style
    panel_builders = {
        "original_gray": lambda title: cached_labeled_preview_gray(
            render_cache,
            "original_gray",
            title,
            gray,
            style.preview_max_side,
            style.label_height,
            style.label_origin,
            style.dark_background,
            style.text_color,
        )[0],
        "debug_boxes": lambda title: add_panel_label(
            make_debug_preview_rgb(gray, detection, style, render_cache),
            title,
            height=style.label_height,
            origin=style.label_origin,
            background=style.dark_background,
            text_color=style.text_color,
        ),
        "separator_evidence": lambda title: add_panel_label(
            make_separator_evidence_debug_rgb(
                gray,
                detection,
                separator_overlay,
                diagnostics.separator_evidence_image,
                style,
                render_cache,
            ),
            title,
            height=style.label_height,
            origin=style.label_origin,
            background=style.dark_background,
            text_color=style.text_color,
        ),
    }
    panels = [
        panel_builders[name](diagnostics.debug_panel_title(name))
        for name in diagnostics.debug_panels
    ]
    canvas = stack_debug_panels(
        panels,
        horizontal=gray.shape[1] < gray.shape[0],
        style=style,
    )
    return add_status_bar(canvas, detection, style)


def stack_debug_panels(
    panels: list[np.ndarray],
    horizontal: bool,
    style: DebugStyleParameters,
) -> np.ndarray:
    panel_spacing = style.panel_spacing
    if horizontal:
        max_h = max(panel.shape[0] for panel in panels)
        total_w = sum(panel.shape[1] for panel in panels) + panel_spacing * (len(panels) - 1)
        canvas = np.full(
            (max_h, total_w, 3),
            style.panel_background,
            dtype=np.uint8,
        )
        x = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[:h, x:x + w] = panel
            x += w + panel_spacing
        return canvas

    max_w = max(panel.shape[1] for panel in panels)
    total_h = sum(panel.shape[0] for panel in panels) + panel_spacing * (len(panels) - 1)
    canvas = np.full(
        (total_h, max_w, 3),
        style.panel_background,
        dtype=np.uint8,
    )
    y = 0
    for panel in panels:
        h, w = panel.shape[:2]
        canvas[y:y + h, :w] = panel
        y += h + panel_spacing
    return canvas
