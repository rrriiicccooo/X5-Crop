from __future__ import annotations

from typing import Any

import numpy as np

from ..detection.decision.model import FinalDetection
from ..image.evidence import (
    SeparatorEvidenceImageParameters,
    make_separator_evidence_gray,
)
from ..configuration.diagnostics import DiagnosticsConfiguration
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
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = cached_preview_gray(render_cache, "original_gray", gray)
    for index, box in enumerate(detection.output_geometry.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, 0.26)
        draw_preview_rect(rgb, box, scale, color, 1)
    draw_preview_rect(
        rgb,
        detection.output_geometry.crop_envelope.box,
        scale,
        (0, 255, 0),
        3,
    )
    return rgb


def draw_evidence_context_overlay(
    rgb: np.ndarray,
    detection: FinalDetection,
    scale: float,
    include_frames: bool = False,
) -> None:
    draw_preview_rect(
        rgb,
        detection.output_geometry.crop_envelope.box,
        scale,
        (0, 255, 0),
        2,
    )
    if include_frames:
        for index, box in enumerate(detection.output_geometry.frames):
            color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
            draw_preview_rect(rgb, box, scale, color, 1)


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
    )
    draw_evidence_context_overlay(rgb, detection, scale)
    draw_separator_overlay(rgb, detection, scale, separator_overlay)
    return rgb


def make_debug_analysis_panel(
    gray: np.ndarray,
    detection: FinalDetection,
    diagnostics: DiagnosticsConfiguration,
    separator_evidence_image: SeparatorEvidenceImageParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    separator_overlay = diagnostics.separator_overlay
    panel_builders = {
        "original_gray": lambda title: cached_labeled_preview_gray(
            render_cache,
            "original_gray",
            title,
            gray,
        )[0],
        "debug_boxes": lambda title: add_panel_label(
            make_debug_preview_rgb(gray, detection, render_cache),
            title,
        ),
        "separator_evidence": lambda title: add_panel_label(
            make_separator_evidence_debug_rgb(
                gray,
                detection,
                separator_overlay,
                separator_evidence_image,
                render_cache,
            ),
            title,
        ),
    }
    panels = [
        panel_builders[name](diagnostics.debug_panel_title(name))
        for name in diagnostics.debug_panels
    ]
    canvas = stack_debug_panels(panels, horizontal=gray.shape[1] < gray.shape[0])
    return add_status_bar(canvas, detection)


def stack_debug_panels(panels: list[np.ndarray], horizontal: bool) -> np.ndarray:
    panel_spacing = 12
    if horizontal:
        max_h = max(panel.shape[0] for panel in panels)
        total_w = sum(panel.shape[1] for panel in panels) + panel_spacing * (len(panels) - 1)
        canvas = np.full((max_h, total_w, 3), 32, dtype=np.uint8)
        x = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[:h, x:x + w] = panel
            x += w + panel_spacing
        return canvas

    max_w = max(panel.shape[1] for panel in panels)
    total_h = sum(panel.shape[0] for panel in panels) + panel_spacing * (len(panels) - 1)
    canvas = np.full((total_h, max_w, 3), 32, dtype=np.uint8)
    y = 0
    for panel in panels:
        h, w = panel.shape[:2]
        canvas[y:y + h, :w] = panel
        y += h + panel_spacing
    return canvas
