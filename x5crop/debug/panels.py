from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..configuration.diagnostics import (
    DebugLegendEntry,
    DebugStyleParameters,
    DiagnosticsConfiguration,
)
from ..configuration.model import DetectionConfiguration
from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.corridors import source_lane_box
from ..detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    SafeCropEnvelope,
)
from ..detection.photo_geometry.template_model import (
    FormatPlacement,
    FrameFormatPlacement,
)
from ..detection.workspace import DetectionWorkspace
from ..domain import Box
from ..io.model import ImageProfile
from ..run_status import RunTerminalOutcome
from ..utils import RGB_CHANNEL_COUNT
from .canvas import (
    FRAME_FILL_COLORS,
    DebugRenderCache,
    add_panel_label,
    cached_preview_gray,
    draw_preview_label,
)
from .status import add_status_bar


DEBUG_ANALYSIS_PANEL_LABELS = (
    "01 · SOURCE AUTHORITY & PIXEL EVIDENCE",
    "02 · RETAINED PLACEMENTS & CANONICAL",
    "03 · PROTECTED OUTPUT & DECISION",
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
        font_size=style.panel_label_font_size,
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


def _draw_dashed_polyline(
    rgb: np.ndarray,
    points: tuple[tuple[float, float], ...],
    scale: float,
    color: tuple[int, int, int],
    width: int,
    dash_length: int,
    dash_gap: int,
    *,
    closed: bool,
) -> None:
    if len(points) < 2:
        return
    scaled = tuple((x * scale, y * scale) for x, y in points)
    if closed:
        scaled += (scaled[0],)
    image = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(image)
    period = float(dash_length + dash_gap)
    for start, end in zip(scaled, scaled[1:]):
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
                width=max(1, width),
            )
            cursor += period
    np.copyto(rgb, np.asarray(image))


def _box_polygon(box: Box) -> tuple[tuple[float, float], ...]:
    return (
        (float(box.left), float(box.top)),
        (float(box.right), float(box.top)),
        (float(box.right), float(box.bottom)),
        (float(box.left), float(box.bottom)),
    )


def _draw_side_transition_region(
    rgb: np.ndarray,
    lane_box: Box,
    region: object,
    layout: str,
    scale: float,
    style: DebugStyleParameters,
) -> None:
    coordinate = region.proposal_position_interval_px.center
    points = (
        ((coordinate, lane_box.top), (coordinate, lane_box.bottom))
        if layout == "horizontal"
        else ((lane_box.left, coordinate), (lane_box.right, coordinate))
    )
    _draw_dashed_polyline(
        rgb,
        points,
        scale,
        style.raw_transition_color,
        style.raw_transition_line_width,
        style.line_dash_length,
        style.line_dash_gap,
        closed=False,
    )


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


def _draw_corner_note(
    rgb: np.ndarray,
    text: str,
    color: tuple[int, int, int],
    font_size: int,
) -> None:
    image = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(image)
    try:
        box = draw.textbbox(
            (0, 0),
            text,
            font=ImageFont.load_default(size=font_size),
            stroke_width=2,
        )
        width = box[2] - box[0]
    except Exception:
        width = len(text) * 8
    draw.text(
        (max(6, rgb.shape[1] - width - 10), 8),
        text,
        fill=color,
        font=ImageFont.load_default(size=font_size),
        stroke_width=2,
        stroke_fill=(0, 0, 0),
    )
    np.copyto(rgb, np.asarray(image))


def _source_evidence_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = _preview(workspace, style, render_cache)
    layout = workspace.boundary_measurement_field.layout
    source_lanes = {
        lane.domain.lane_id: lane for lane in workspace.source_core.lanes
    }
    for lane in workspace.source_core.lanes:
        _draw_dashed_polyline(
            rgb,
            _box_polygon(source_lane_box(lane, layout)),
            scale,
            style.lane_authority_color,
            style.retained_line_width,
            style.line_dash_length,
            style.line_dash_gap,
            closed=True,
        )
    for lane in detection.candidate.geometry.lane_reconstructions:
        source_lane = source_lanes.get(lane.lane_id)
        if source_lane is not None:
            lane_box = source_lane_box(source_lane, layout)
            for region in lane.side_transition_regions:
                _draw_side_transition_region(
                    rgb,
                    lane_box,
                    region,
                    layout,
                    scale,
                    style,
                )
        for observation in lane.raw_top_bottom_observations:
            _draw_source_line(
                rgb,
                observation,
                scale,
                style.observed_edge_color,
                style.observed_edge_line_width,
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
    long_edge_count = sum(
        len(lane.raw_top_bottom_observations)
        for lane in detection.candidate.geometry.lane_reconstructions
    )
    side_region_count = sum(
        len(lane.side_transition_regions)
        for lane in detection.candidate.geometry.lane_reconstructions
    )
    assessment = detection.transform_assessment
    if assessment.observed_angle_interval_degrees is not None:
        interval = assessment.observed_angle_interval_degrees
        applied = assessment.applied_source_rotation_degrees
        _draw_corner_note(
            rgb,
            (
                f"SHARED [{interval.minimum:+.3f}°, "
                f"{interval.maximum:+.3f}°] · "
                f"APPLIED {applied:+.3f}°"
            ),
            style.inferred_direction_color,
            style.panel_label_font_size,
        )
    return _labeled(
        rgb,
        (
            f"{DEBUG_ANALYSIS_PANEL_LABELS[0]} | "
            f"lanes={len(source_lanes)} side_regions={side_region_count} "
            f"long_edges={long_edge_count} queries={query_count} "
            f"transitions={transition_count}"
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


def _boundary_anchor(
    geometry: FrameFormatPlacement,
    role: BoundaryRole,
) -> tuple[float, float]:
    boundary = {
        BoundaryRole.START: geometry.start,
        BoundaryRole.END: geometry.end,
    }[role]
    line = boundary.line
    closest = sorted(
        geometry.canonical_source_polygon,
        key=lambda point: abs(
            line.normal_x * point[0]
            + line.normal_y * point[1]
            - line.offset_px
        ),
    )[:2]
    return min(closest, key=lambda point: (point[1], point[0]))


def _add_start_end_annotations(
    panel: np.ndarray,
    geometries: tuple[tuple[int, FrameFormatPlacement], ...],
    scale: float,
    style: DebugStyleParameters,
) -> np.ndarray:
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(
        size=max(10, style.frame_label_font_size - 2)
    )
    for _ordinal, geometry in geometries:
        for role in (BoundaryRole.START, BoundaryRole.END):
            anchor = _boundary_anchor(geometry, role)
            x = anchor[0] * scale
            photo_top = style.label_height + anchor[1] * scale
            line_top = max(style.label_height + 2, photo_top - 18)
            draw.line(
                ((x, line_top), (x, photo_top + 8)),
                fill=style.canonical_boundary_color,
                width=2,
            )
            text = role.value.upper()
            try:
                bounds = draw.textbbox((0, 0), text, font=font)
                text_width = bounds[2] - bounds[0]
                text_height = bounds[3] - bounds[1]
            except Exception:
                text_width = len(text) * style.text_fallback_size[0]
                text_height = style.text_fallback_size[1]
            draw.text(
                (
                    max(
                        2,
                        min(
                            panel.shape[1] - text_width - 2,
                            (
                                x + 3
                                if role == BoundaryRole.START
                                else x - text_width - 3
                            ),
                        ),
                    ),
                    max(style.label_height + 1, line_top - text_height - 1),
                ),
                text,
                fill=style.canonical_boundary_color,
                font=font,
                stroke_width=1,
                stroke_fill=(0, 0, 0),
            )
    return np.asarray(image)


def _selected_geometry_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = _preview(workspace, style, render_cache)
    global_ordinals = {
        (item.lane_id, item.lane_ordinal): item.global_output_ordinal
        for item in detection.output_slot_identities
    }
    retained: tuple[FormatPlacement, ...] = tuple(
        placement
        for lane in detection.candidate.geometry.lane_reconstructions
        for placement in lane.retained_placements
    )
    for placement in retained:
        for geometry in placement.canonical.frames:
            if (
                geometry.lane_id,
                geometry.lane_ordinal,
            ) not in global_ordinals:
                continue
            _draw_dashed_polyline(
                rgb,
                geometry.canonical_source_polygon,
                scale,
                style.retained_color,
                style.retained_line_width,
                style.line_dash_length,
                style.line_dash_gap,
                closed=True,
            )
    geometries = _geometry_by_identity(detection)
    for global_ordinal, geometry in geometries:
        color = _frame_color(global_ordinal)
        _fill_polygon(
            rgb,
            geometry.canonical_source_polygon,
            scale,
            color,
            style.frame_fill_alpha / 2.0,
        )
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
            font_size=style.frame_label_font_size,
        )
    label = (
        f"{DEBUG_ANALYSIS_PANEL_LABELS[1]} | "
        f"retained_complete_states={len(retained)} "
        f"canonical=representative_only"
    )
    if detection.decision.status == "needs_review":
        label += " | CANDIDATE AUDIT · NOT EXPORTABLE"
    return _add_start_end_annotations(
        _labeled(rgb, label, style),
        geometries,
        scale,
        style,
    )


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
        budget_by_geometry = {
            item.geometry_id: item
            for item in (
                detection.candidate.geometry.direct_use_budget_assessments
            )
        }
        for geometry in geometries:
            identity = identities[(geometry.lane_id, geometry.lane_ordinal)]
            color = _frame_color(identity.global_output_ordinal)
            _fill_polygon(
                rgb,
                geometry.placement_source_footprint,
                scale,
                color,
                style.frame_fill_alpha / 2.0,
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
                style.retained_color,
                style.retained_line_width,
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
                font_size=style.frame_label_font_size,
            )
            budget = budget_by_geometry.get(geometry.geometry_id)
            if budget is not None and budget.state.value == "contradicted":
                draw_preview_label(
                    rgb,
                    Box(left, top, right, bottom),
                    scale,
                    "BUDGET",
                    style.review_color,
                    inset=style.frame_label_inset + 16,
                    stroke_width=style.frame_label_stroke_width,
                    font_size=style.frame_label_font_size,
                )
        exceeded = sum(
            assessment.state.value == "contradicted"
            for assessment in detection.candidate.geometry.direct_use_budget_assessments
        )
        saturation_count = sum(
            len(geometry.saturation_facts) for geometry in geometries
        )
        label = (
            f"{DEBUG_ANALYSIS_PANEL_LABELS[2]} | "
            f"S/E≤5% T/B≤3% · budget_exceeded={exceeded} "
            f"authority_saturation={saturation_count}"
        )
        if not detection.frame_export_eligible:
            label += " | SOURCE ATOMIC · 0 OFFICIAL TIFF"
        else:
            label += (
                f" | SOURCE ATOMIC · {detection.output_slot_count} "
                "TIFF ELIGIBLE"
            )
    else:
        label = (
            f"{DEBUG_ANALYSIS_PANEL_LABELS[2]} | NONE · "
            "SOURCE ATOMIC · 0 OFFICIAL TIFF"
        )
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


def add_legend_bar(
    rgb: np.ndarray,
    entries: tuple[DebugLegendEntry, ...],
    style: DebugStyleParameters,
) -> np.ndarray:
    height, width = rgb.shape[:2]
    bar_height = style.legend_bar_height
    panel = np.full(
        (height + bar_height, width, RGB_CHANNEL_COUNT),
        style.dark_background,
        dtype=np.uint8,
    )
    panel[:height, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    x = 12
    y = height + bar_height // 2
    for entry in entries:
        sample_end = x + style.legend_sample_width
        if entry.dashed:
            cursor = x
            while cursor < sample_end:
                stop = min(sample_end, cursor + style.line_dash_length)
                draw.line(
                    ((cursor, y), (stop, y)),
                    fill=entry.color,
                    width=2,
                )
                cursor += style.line_dash_length + style.line_dash_gap
        else:
            draw.line(
                ((x, y), (sample_end, y)),
                fill=entry.color,
                width=2,
            )
        text_x = sample_end + style.legend_text_gap
        text_y = y - style.text_fallback_size[1] // 2
        legend_font = ImageFont.load_default(size=style.legend_font_size)
        draw.text(
            (text_x, text_y),
            entry.label,
            fill=style.text_color,
            font=legend_font,
        )
        try:
            bounds = draw.textbbox(
                (text_x, text_y),
                entry.label,
                font=legend_font,
            )
            text_width = bounds[2] - bounds[0]
        except Exception:
            text_width = len(entry.label) * style.text_fallback_size[0]
        x = text_x + text_width + 24
        if x >= width - style.legend_sample_width:
            break
    return np.asarray(image)


def make_debug_analysis_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    configuration: DetectionConfiguration,
    profile: ImageProfile,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    style = diagnostics.style
    panels = (
        _source_evidence_panel(
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
    canvas = add_legend_bar(
        canvas,
        diagnostics.legend_entries
        + (
            DebugLegendEntry(
                "Canonical / protected output",
                _frame_color(1),
                False,
            ),
            DebugLegendEntry(
                "Budget violation",
                style.review_color,
                False,
            ),
        ),
        style,
    )
    return add_status_bar(
        canvas,
        detection,
        configuration,
        profile,
        style,
        terminal_outcome,
    )
