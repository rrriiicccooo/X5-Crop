"""Cross-axis and sequence-axis Debug Analysis panels."""

from __future__ import annotations

import numpy as np
from PIL import ImageDraw

from ..configuration.diagnostics import DebugStyleParameters
from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.corridors import source_lane_box
from ..detection.photo_geometry.model import BoundaryRole
from ..detection.photo_geometry.template_placement import TemplateFrame
from ..detection.workspace import DetectionWorkspace
from .canvas import DebugRenderCache
from .panel_facts import (
    axis_authority_summaries,
    geometry_by_identity,
    selection_summary,
    source_image,
)
from .panel_layout import (
    PresentationGrid,
    Viewport,
    clip_segment_to_box,
    draw_dashed_polyline,
    draw_label_chip,
    font,
    panel_base,
    paste_source,
    source_line_points,
    text_width,
    viewport,
)


def _boundary_points(
    geometry: TemplateFrame,
    role: BoundaryRole,
) -> tuple[tuple[float, float], tuple[float, float]]:
    boundary = geometry.start if role == BoundaryRole.START else geometry.end
    line = boundary.line
    closest = sorted(
        geometry.canonical_source_polygon,
        key=lambda point: abs(
            line.normal_x * point[0]
            + line.normal_y * point[1]
            - line.offset_px
        ),
    )[:2]
    return closest[0], closest[1]


def _draw_selected_start_end(
    draw: ImageDraw.ImageDraw,
    geometries: tuple[tuple[int, TemplateFrame], ...],
    selected_viewport: Viewport,
    style: DebugStyleParameters,
) -> None:
    annotation_font = font(style.annotation_font_size)
    viewport_top = selected_viewport.target_box[1]
    labels: list[tuple[float, int, str]] = []
    for index, (_ordinal, geometry) in enumerate(geometries):
        roles = (
            ((BoundaryRole.END,) if index < len(geometries) - 1 else ())
            + ((BoundaryRole.START,) if index > 0 else ())
        )
        for role in roles:
            source_points = _boundary_points(geometry, role)
            projected = tuple(
                selected_viewport.point(point) for point in source_points
            )
            clipped = clip_segment_to_box(
                projected[0],
                projected[1],
                selected_viewport.target_box,
            )
            if clipped is None:
                continue
            upper, lower = sorted(clipped, key=lambda point: point[1])
            dy = lower[1] - upper[1]
            dx = lower[0] - upper[0]
            extension_y = max(
                float(style.annotation_extension),
                upper[1] - viewport_top + 7.0,
            )
            extension_x = 0.0 if abs(dy) <= 1.0e-9 else dx * extension_y / dy
            line_top = (upper[0] - extension_x, upper[1] - extension_y)
            draw.line(
                (line_top, lower),
                fill=style.selected_boundary_color,
                width=2,
            )
            text = role.value.upper()
            label_width = text_width(draw, text, annotation_font)
            text_x = (
                line_top[0] + 4
                if role == BoundaryRole.START
                else line_top[0] - label_width - 4
            )
            target_left, _top, target_right, _bottom = (
                selected_viewport.target_box
            )
            text_x = min(max(target_left, text_x), target_right - label_width)
            labels.append((text_x, label_width, text))
    occupied_right = [float("-inf"), float("-inf")]
    label_rows = (
        style.panel_title_height + 3,
        style.panel_title_height + 3 + style.boundary_label_row_gap,
    )
    for text_x, label_width, text in sorted(labels, key=lambda item: item[0]):
        row = next(
            (
                index
                for index, right in enumerate(occupied_right)
                if text_x >= right + style.boundary_label_horizontal_gap
            ),
            min(range(len(occupied_right)), key=occupied_right.__getitem__),
        )
        draw.text(
            (text_x, label_rows[row]),
            text,
            fill=style.selected_boundary_color,
            font=annotation_font,
        )
        occupied_right[row] = max(
            occupied_right[row], text_x + label_width
        )


def _draw_detected_top_bottom(
    draw: ImageDraw.ImageDraw,
    detection: FinalDetection,
    selected_viewport: Viewport,
    style: DebugStyleParameters,
) -> set[BoundaryRole]:
    roles: set[BoundaryRole] = set()
    for lane in detection.candidate.geometry.lane_reconstructions:
        for observation in lane.prepared.raw_cross_observations:
            source_points = source_line_points(observation)
            if not source_points:
                continue
            projected = tuple(
                selected_viewport.point(point) for point in source_points
            )
            clipped = clip_segment_to_box(
                projected[0], projected[1], selected_viewport.target_box
            )
            if clipped is None:
                continue
            draw_dashed_polyline(
                draw,
                clipped,
                style.detected_edge_color,
                2,
                style.line_dash_length,
                style.line_dash_gap,
                closed=False,
            )
            roles.add(observation.role)
    return roles


def _draw_selected_top_bottom(
    draw: ImageDraw.ImageDraw,
    geometries: tuple[tuple[int, TemplateFrame], ...],
    selected_viewport: Viewport,
    style: DebugStyleParameters,
) -> set[BoundaryRole]:
    roles: set[BoundaryRole] = set()
    for _ordinal, geometry in geometries:
        for boundary in (geometry.top, geometry.bottom):
            source_points = source_line_points(boundary)
            if not source_points:
                continue
            projected = tuple(
                selected_viewport.point(point) for point in source_points
            )
            clipped = clip_segment_to_box(
                projected[0], projected[1], selected_viewport.target_box
            )
            if clipped is None:
                continue
            draw.line(
                clipped,
                fill=style.selected_edge_color,
                width=style.evidence_line_width,
            )
            roles.add(boundary.role)
    return roles


def cross_axis_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
    grid: PresentationGrid,
) -> np.ndarray:
    panel_width = style.canvas_width - 2 * style.outer_margin
    cross_authority, _sequence_authority, _shared_authority = (
        axis_authority_summaries(detection)
    )
    panel, draw = panel_base(
        panel_width,
        grid.cross_axis_panel_height,
        "01 · CROSS-AXIS TOP / BOTTOM",
        cross_authority,
        style,
    )
    source, projection = source_image(workspace, render_cache)
    selected_viewport = viewport(
        projection,
        (
            style.panel_media_inset_x,
            style.cross_axis_media_top,
            panel_width - style.panel_media_inset_x,
            style.cross_axis_media_top + grid.media_height,
        ),
    )
    paste_source(panel, source, selected_viewport)
    draw = ImageDraw.Draw(panel)
    geometries = geometry_by_identity(detection)
    detected = _draw_detected_top_bottom(
        draw, detection, selected_viewport, style
    )
    selected = _draw_selected_top_bottom(
        draw, geometries, selected_viewport, style
    )
    top_y = style.panel_title_height + 6
    bottom_y = grid.cross_axis_panel_height - 27
    left = selected_viewport.target_box[0]
    if BoundaryRole.TOP in detected:
        draw_label_chip(
            draw, (left, top_y), "DETECTED TOP", style.detected_edge_color,
            style, filled=False,
        )
    if BoundaryRole.TOP in selected:
        draw_label_chip(
            draw, (left + 118, top_y), "SELECTED TOP",
            style.selected_edge_color, style,
        )
    if BoundaryRole.BOTTOM in selected:
        draw_label_chip(
            draw, (left, bottom_y), "SELECTED BOTTOM",
            style.selected_edge_color, style,
        )
    if BoundaryRole.BOTTOM in detected:
        draw_label_chip(
            draw, (left + 138, bottom_y), "DETECTED BOTTOM",
            style.detected_edge_color, style, filled=False,
        )
    return np.asarray(panel)


def _draw_detected_start_end(
    draw: ImageDraw.ImageDraw,
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    selected_viewport: Viewport,
    style: DebugStyleParameters,
) -> bool:
    layout = workspace.layout
    source_lanes = {
        lane.domain.lane_id: lane for lane in workspace.source_core.lanes
    }
    found = False
    for lane in detection.candidate.geometry.lane_reconstructions:
        source_lane = source_lanes.get(lane.lane_id)
        if source_lane is None:
            continue
        lane_box = source_lane_box(source_lane, layout)
        for region in lane.prepared.side_regions:
            coordinate = region.proposal_position_interval_px.center
            source_points = (
                ((coordinate, lane_box.top), (coordinate, lane_box.bottom))
                if layout == "horizontal"
                else ((lane_box.left, coordinate), (lane_box.right, coordinate))
            )
            projected = tuple(
                selected_viewport.point(point) for point in source_points
            )
            clipped = clip_segment_to_box(
                projected[0], projected[1], selected_viewport.target_box
            )
            if clipped is None:
                continue
            draw_dashed_polyline(
                draw,
                clipped,
                style.detected_transition_color,
                style.raw_transition_line_width,
                style.line_dash_length,
                style.line_dash_gap,
                closed=False,
            )
            found = True
    return found


def long_axis_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
    grid: PresentationGrid,
) -> np.ndarray:
    panel_width = style.canvas_width - 2 * style.outer_margin
    _cross_authority, sequence_authority, _shared_authority = (
        axis_authority_summaries(detection)
    )
    panel, _draw = panel_base(
        panel_width,
        grid.long_axis_panel_height,
        "02 · LONG-AXIS START / END",
        sequence_authority,
        style,
    )
    source, projection = source_image(workspace, render_cache)
    geometries = geometry_by_identity(detection)
    media_left = style.panel_media_inset_x
    media_right = panel_width - style.panel_media_inset_x
    media_top = style.long_axis_media_top
    media_bottom = media_top + grid.media_height
    selected_viewport = viewport(
        projection, (media_left, media_top, media_right, media_bottom)
    )
    paste_source(panel, source, selected_viewport)
    draw = ImageDraw.Draw(panel)
    detected = _draw_detected_start_end(
        draw, workspace, detection, selected_viewport, style
    )
    _draw_selected_start_end(draw, geometries, selected_viewport, style)
    if not geometries:
        note = "NO SELECTED START / END · CANDIDATE AUDIT ONLY"
        note_font = font(style.header_detail_font_size)
        note_width = text_width(draw, note, note_font)
        draw.rectangle(
            (
                (media_left + media_right - note_width) // 2 - 12,
                media_top + 57,
                (media_left + media_right + note_width) // 2 + 12,
                media_top + 86,
            ),
            fill=style.panel_background,
        )
        draw.text(
            ((media_left + media_right - note_width) // 2, media_top + 63),
            note,
            fill=style.review_color,
            font=note_font,
        )
    footer_y = grid.long_axis_panel_height - 27
    if detected:
        draw_label_chip(
            draw, (media_left, footer_y), "RAW / DETECTED",
            style.detected_transition_color, style, filled=False,
        )
    if geometries:
        draw_label_chip(
            draw, (media_left + 132, footer_y), "SELECTED START / END",
            style.selected_boundary_color, style, filled=False,
        )
    summary = selection_summary(detection)
    summary_font = font(style.annotation_font_size)
    draw.text(
        (media_right - text_width(draw, summary, summary_font), footer_y),
        summary,
        fill=style.secondary_text_color,
        font=summary_font,
    )
    return np.asarray(panel)
