from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from ..configuration.diagnostics import (
    DebugStyleParameters,
    DiagnosticsConfiguration,
)
from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.corridors import source_lane_box
from ..detection.photo_geometry.model import BoundaryAxis, SafeCropEnvelope
from ..detection.photo_geometry.template_model import FrameFormatPlacement
from ..detection.workspace import DetectionWorkspace
from ..domain import Box
from ..run_status import RunTerminalOutcome
from ..utils import RGB_CHANNEL_COUNT
from .canvas import (
    FRAME_FILL_COLORS,
    DebugRenderCache,
    add_panel_label,
    cached_preview_gray,
    draw_preview_label,
    draw_preview_rect,
)
from .status import add_status_bar


DEBUG_ANALYSIS_PANEL_LABELS = (
    "Source-coordinate gray and lane authority",
    "Raw boundary evidence and shared direction",
    "Canonical format placement and retained union",
    "Continuous safe output geometry and budget",
)


def _frame_color(global_ordinal: int) -> tuple[int, int, int]:
    if not 1 <= global_ordinal <= len(FRAME_FILL_COLORS):
        raise ValueError(
            "Debug Analysis frame ordinal exceeds the fixed color table"
        )
    return FRAME_FILL_COLORS[global_ordinal - 1]


def _preview(
    workspace: DetectionWorkspace,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> tuple[np.ndarray, float]:
    return cached_preview_gray(
        render_cache,
        "source_coordinate_gray",
        workspace.source_gray,
        style.preview_max_side,
    )


def _labeled(
    rgb: np.ndarray,
    label: str,
    style: DebugStyleParameters,
) -> np.ndarray:
    return add_panel_label(
        rgb,
        label,
        height=style.label_height,
        origin=style.label_origin,
        background=style.dark_background,
        text_color=style.text_color,
    )


def _draw_source_line(
    rgb: np.ndarray,
    observation: object,
    scale: float,
    color: tuple[int, int, int],
    width: int,
) -> None:
    line = observation.line
    support = line.support_projection_px
    if line.source_axis_long == BoundaryAxis.X:
        if abs(line.normal_y) <= 1.0e-12:
            return
        points = (
            (
                support.minimum,
                (
                    line.offset_px
                    - line.normal_x * support.minimum
                )
                / line.normal_y,
            ),
            (
                support.maximum,
                (
                    line.offset_px
                    - line.normal_x * support.maximum
                )
                / line.normal_y,
            ),
        )
    else:
        if abs(line.normal_x) <= 1.0e-12:
            return
        points = (
            (
                (
                    line.offset_px
                    - line.normal_y * support.minimum
                )
                / line.normal_x,
                support.minimum,
            ),
            (
                (
                    line.offset_px
                    - line.normal_y * support.maximum
                )
                / line.normal_x,
                support.maximum,
            ),
        )
    image = Image.fromarray(rgb, mode="RGB")
    ImageDraw.Draw(image).line(
        tuple((x * scale, y * scale) for x, y in points),
        fill=color,
        width=max(1, width),
    )
    np.copyto(rgb, np.asarray(image))


def _draw_polygon(
    rgb: np.ndarray,
    polygon: tuple[tuple[float, float], ...],
    scale: float,
    color: tuple[int, int, int],
    width: int,
) -> None:
    if len(polygon) < 3:
        return
    image = Image.fromarray(rgb, mode="RGB")
    points = tuple((x * scale, y * scale) for x, y in polygon)
    ImageDraw.Draw(image).line(
        points + (points[0],),
        fill=color,
        width=max(1, width),
    )
    np.copyto(rgb, np.asarray(image))


def _fill_polygon(
    rgb: np.ndarray,
    polygon: tuple[tuple[float, float], ...],
    scale: float,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    if len(polygon) < 3:
        return
    base = Image.fromarray(rgb, mode="RGB").convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).polygon(
        tuple((x * scale, y * scale) for x, y in polygon),
        fill=(*color, int(round(255.0 * alpha))),
    )
    np.copyto(rgb, np.asarray(Image.alpha_composite(base, overlay).convert("RGB")))


def _source_panel(
    workspace: DetectionWorkspace,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = _preview(workspace, style, render_cache)
    for lane in workspace.source_core.lanes:
        draw_preview_rect(
            rgb,
            source_lane_box(
                lane,
                workspace.boundary_measurement_field.layout,
            ),
            scale,
            style.raw_separator_color,
            style.raw_separator_line_width,
        )
    return _labeled(rgb, DEBUG_ANALYSIS_PANEL_LABELS[0], style)


def _measurement_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = _preview(workspace, style, render_cache)
    for lane in detection.candidate.geometry.lane_reconstructions:
        for observation in lane.raw_top_bottom_observations:
            _draw_source_line(
                rgb,
                observation,
                scale,
                style.selected_edge_pair_color,
                style.selected_separator_line_width,
            )
    query_count = sum(
        len(lane.measurement_sets)
        for lane in detection.candidate.geometry.lane_reconstructions
    )
    transition_count = sum(
        len(item.transitions)
        for lane in detection.candidate.geometry.lane_reconstructions
        for item in lane.measurement_sets
    )
    return _labeled(
        rgb,
        (
            f"{DEBUG_ANALYSIS_PANEL_LABELS[1]} | "
            f"queries={query_count} transitions={transition_count}"
        ),
        style,
    )


def _geometry_by_identity(
    detection: FinalDetection,
) -> tuple[tuple[int, FrameFormatPlacement], ...]:
    global_ordinals = {
        (item.lane_id, item.lane_ordinal): item.global_output_ordinal
        for item in detection.output_slot_identities
    }
    values: list[tuple[int, FrameFormatPlacement]] = []
    for lane in detection.candidate.geometry.lane_reconstructions:
        placement = lane.canonical_placement
        if placement is None:
            continue
        for geometry in placement.canonical.frames:
            ordinal = global_ordinals.get(
                (geometry.lane_id, geometry.lane_ordinal)
            )
            if ordinal is not None:
                values.append((ordinal, geometry))
    return tuple(sorted(values, key=lambda item: item[0]))


def _selected_geometry_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = _preview(workspace, style, render_cache)
    geometries = _geometry_by_identity(detection)
    for global_ordinal, geometry in geometries:
        color = _frame_color(global_ordinal)
        _draw_polygon(
            rgb,
            geometry.canonical_source_polygon,
            scale,
            color,
            style.frame_line_width,
        )
        bounds = Box(
            math.floor(min(point[0] for point in geometry.canonical_source_polygon)),
            math.floor(min(point[1] for point in geometry.canonical_source_polygon)),
            math.ceil(max(point[0] for point in geometry.canonical_source_polygon)),
            math.ceil(max(point[1] for point in geometry.canonical_source_polygon)),
        )
        draw_preview_label(
            rgb,
            bounds,
            scale,
            f"F{global_ordinal}",
            color,
            inset=style.frame_label_inset,
            stroke_width=style.frame_label_stroke_width,
        )
    label = DEBUG_ANALYSIS_PANEL_LABELS[2]
    if detection.decision.status == "needs_review":
        label += " | candidate audit only - NOT EXPORTABLE"
    return _labeled(rgb, label, style)


def _safe_crop_envelopes(
    detection: FinalDetection,
) -> tuple[SafeCropEnvelope, ...]:
    return detection.candidate.geometry.safe_crop_envelopes


def _protected_output_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = _preview(workspace, style, render_cache)
    geometries = _safe_crop_envelopes(detection)
    if geometries:
        identities = {
            (item.lane_id, item.lane_ordinal): item
            for item in detection.output_slot_identities
        }
        for geometry in geometries:
            identity = identities[(geometry.lane_id, geometry.lane_ordinal)]
            color = _frame_color(identity.global_output_ordinal)
            _fill_polygon(
                rgb,
                geometry.placement_source_footprint,
                scale,
                color,
                style.frame_fill_alpha,
            )
            _fill_polygon(
                rgb,
                geometry.constrained_source_footprint,
                scale,
                color,
                style.frame_fill_alpha,
            )
            _draw_polygon(
                rgb,
                geometry.required_source_footprint,
                scale,
                style.raw_separator_color,
                style.frame_line_width,
            )
            _draw_polygon(
                rgb,
                geometry.constrained_source_footprint,
                scale,
                color,
                style.frame_line_width,
            )
            left = math.floor(
                min(point[0] for point in geometry.constrained_source_footprint)
            )
            top = math.floor(
                min(point[1] for point in geometry.constrained_source_footprint)
            )
            right = math.ceil(
                max(point[0] for point in geometry.constrained_source_footprint)
            ) + 1
            bottom = math.ceil(
                max(point[1] for point in geometry.constrained_source_footprint)
            ) + 1
            draw_preview_label(
                rgb,
                Box(left, top, right, bottom),
                scale,
                f"F{identity.global_output_ordinal}",
                color,
                inset=style.frame_label_inset,
                stroke_width=style.frame_label_stroke_width,
            )
        exceeded = sum(
            assessment.state.value == "contradicted"
            for assessment in detection.candidate.geometry.direct_use_budget_assessments
        )
        saturation_count = sum(
            len(geometry.saturation_facts) for geometry in geometries
        )
        label = (
            f"{DEBUG_ANALYSIS_PANEL_LABELS[3]} | "
            f"budget_exceeded={exceeded} "
            f"authority_saturation={saturation_count}"
        )
        if not detection.frame_export_eligible:
            label += " | NOT EXPORTABLE"
    else:
        # Candidate envelopes may be inspected in the selected-geometry panel;
        # a review decision intentionally has no official output box here.
        label = f"{DEBUG_ANALYSIS_PANEL_LABELS[3]} | NONE - NOT EXPORTABLE"
    return _labeled(rgb, label, style)


def stack_debug_panels(
    panels: tuple[np.ndarray, ...],
    *,
    horizontal: bool,
    style: DebugStyleParameters,
) -> np.ndarray:
    if not panels:
        raise ValueError("Debug Analysis requires at least one panel")
    spacing = style.panel_spacing
    if horizontal:
        height = max(panel.shape[0] for panel in panels)
        width = sum(panel.shape[1] for panel in panels) + spacing * (
            len(panels) - 1
        )
        canvas = np.full(
            (height, width, RGB_CHANNEL_COUNT),
            style.panel_background,
            dtype=np.uint8,
        )
        left = 0
        for panel in panels:
            panel_height, panel_width = panel.shape[:2]
            canvas[:panel_height, left : left + panel_width] = panel
            left += panel_width + spacing
        return canvas
    width = max(panel.shape[1] for panel in panels)
    height = sum(panel.shape[0] for panel in panels) + spacing * (
        len(panels) - 1
    )
    canvas = np.full(
        (height, width, RGB_CHANNEL_COUNT),
        style.panel_background,
        dtype=np.uint8,
    )
    top = 0
    for panel in panels:
        panel_height, panel_width = panel.shape[:2]
        canvas[top : top + panel_height, :panel_width] = panel
        top += panel_height + spacing
    return canvas


def make_debug_analysis_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    style = diagnostics.style
    panels = (
        _source_panel(workspace, style, render_cache),
        _measurement_panel(
            workspace,
            detection,
            style,
            render_cache,
        ),
        _selected_geometry_panel(
            workspace,
            detection,
            style,
            render_cache,
        ),
        _protected_output_panel(
            workspace,
            detection,
            style,
            render_cache,
        ),
    )
    source_gray = workspace.source_gray
    canvas = stack_debug_panels(
        panels,
        horizontal=source_gray.shape[1] < source_gray.shape[0],
        style=style,
    )
    return add_status_bar(
        canvas,
        detection,
        style,
        terminal_outcome,
    )
