from __future__ import annotations

import numpy as np

from ..detection.final.model import FinalDetection
from ..detection.candidate.model import AssessedCandidate
from ..domain import CropEnvelope
from ..geometry.boxes import map_work_box
from ..output.model import OutputGeometry
from ..run_status import RunTerminalOutcome
from ..image.evidence import (
    SeparatorEvidenceImageParameters,
    make_separator_evidence_gray,
)
from ..configuration.diagnostics import (
    DebugStyleParameters,
    DiagnosticsConfiguration,
    SeparatorOverlayParameters,
)
from ..utils import RGB_CHANNEL_COUNT
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
    selected_candidate: AssessedCandidate,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    geometry = debug_geometry(gray, detection, selected_candidate)
    rgb, scale = cached_preview_gray(
        render_cache,
        "original_gray",
        gray,
        style.preview_max_side,
    )
    for index, box in enumerate(geometry.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, style.frame_fill_alpha)
        draw_preview_rect(rgb, box, scale, color, style.frame_line_width)
    draw_preview_rect(
        rgb,
        geometry.crop_envelope.box,
        scale,
        style.crop_envelope_color,
        style.crop_envelope_line_width,
    )
    return rgb


def debug_geometry(
    gray: np.ndarray,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
) -> OutputGeometry:
    final_geometry = detection.output_geometry
    if final_geometry is not None:
        return final_geometry
    candidate_geometry = selected_candidate.geometry
    image_height, image_width = gray.shape
    return OutputGeometry(
        crop_envelope=CropEnvelope(
            map_work_box(
                candidate_geometry.crop_envelope.box,
                candidate_geometry.layout,
                image_width,
                image_height,
            )
        ),
        frames=tuple(
            map_work_box(
                frame,
                candidate_geometry.layout,
                image_width,
                image_height,
            )
            for frame in candidate_geometry.frames
        ),
    )


def draw_evidence_context_overlay(
    rgb: np.ndarray,
    geometry: OutputGeometry,
    scale: float,
    style: DebugStyleParameters,
) -> None:
    draw_preview_rect(
        rgb,
        geometry.crop_envelope.box,
        scale,
        style.crop_envelope_color,
        style.evidence_envelope_line_width,
    )


def make_separator_evidence_debug_gray(
    gray: np.ndarray,
    params: SeparatorEvidenceImageParameters,
) -> np.ndarray:
    return make_separator_evidence_gray(gray, params)


def make_separator_evidence_debug_rgb(
    gray: np.ndarray,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    separator_overlay: SeparatorOverlayParameters,
    params: SeparatorEvidenceImageParameters,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    geometry = debug_geometry(gray, detection, selected_candidate)
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
    draw_evidence_context_overlay(rgb, geometry, scale, style)
    draw_separator_overlay(
        rgb,
        selected_candidate,
        scale,
        separator_overlay,
        style,
        gray.shape[1],
        gray.shape[0],
    )
    return rgb


def make_debug_analysis_panel(
    gray: np.ndarray,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    separator_overlay = diagnostics.separator_overlay
    style = diagnostics.style
    original_gray = cached_labeled_preview_gray(
        render_cache,
        "original_gray",
        "Original gray context",
        gray,
        style.preview_max_side,
        style.label_height,
        style.label_origin,
        style.dark_background,
        style.text_color,
    )[0]
    debug_boxes = add_panel_label(
        make_debug_preview_rgb(
            gray,
            detection,
            selected_candidate,
            style,
            render_cache,
        ),
        (
            "Debug boxes"
            if detection.frame_export_eligible
            else "Provisional boxes - NOT EXPORTABLE"
        ),
        height=style.label_height,
        origin=style.label_origin,
        background=style.dark_background,
        text_color=style.text_color,
    )
    separator_evidence = add_panel_label(
        make_separator_evidence_debug_rgb(
            gray,
            detection,
            selected_candidate,
            separator_overlay,
            diagnostics.separator_evidence_image,
            style,
            render_cache,
        ),
        "Separator evidence",
        height=style.label_height,
        origin=style.label_origin,
        background=style.dark_background,
        text_color=style.text_color,
    )
    canvas = stack_debug_panels(
        original_gray,
        debug_boxes,
        separator_evidence,
        horizontal=gray.shape[1] < gray.shape[0],
        style=style,
    )
    return add_status_bar(
        canvas,
        detection,
        style,
        terminal_outcome,
    )


def stack_debug_panels(
    original_gray: np.ndarray,
    debug_boxes: np.ndarray,
    separator_evidence: np.ndarray,
    *,
    horizontal: bool,
    style: DebugStyleParameters,
) -> np.ndarray:
    panels = (original_gray, debug_boxes, separator_evidence)
    panel_spacing = style.panel_spacing
    if horizontal:
        max_h = max(panel.shape[0] for panel in panels)
        total_w = sum(panel.shape[1] for panel in panels) + panel_spacing * (len(panels) - 1)
        canvas = np.full(
            (max_h, total_w, RGB_CHANNEL_COUNT),
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
        (total_h, max_w, RGB_CHANNEL_COUNT),
        style.panel_background,
        dtype=np.uint8,
    )
    y = 0
    for panel in panels:
        h, w = panel.shape[:2]
        canvas[y:y + h, :w] = panel
        y += h + panel_spacing
    return canvas
