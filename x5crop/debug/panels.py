from __future__ import annotations

from dataclasses import dataclass
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
from ..detection.photo_geometry.template_model import FrameFormatPlacement
from ..detection.workspace import DetectionWorkspace
from ..io.model import ImageProfile
from ..run_status import RunTerminalOutcome
from ..utils import RGB_CHANNEL_COUNT
from .canvas import FRAME_FILL_COLORS, DebugRenderCache, cached_source_image
from .status import add_status_bar


DEBUG_ANALYSIS_PANEL_LABELS = (
    "01 · CROSS-AXIS TOP / BOTTOM",
    "02 · LONG-AXIS START / END",
    "03 · FINAL SAFE OUTPUT",
)


@dataclass(frozen=True)
class _Projection:
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
class _Viewport:
    projection: _Projection
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


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> int:
    bounds = draw.textbbox((0, 0), text, font=font)
    return bounds[2] - bounds[0]


def _frame_color(global_ordinal: int) -> tuple[int, int, int]:
    if not 1 <= global_ordinal <= len(FRAME_FILL_COLORS):
        raise ValueError("Debug Analysis frame ordinal exceeds the fixed color table")
    return FRAME_FILL_COLORS[global_ordinal - 1]


def _panel_base(
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
    title_font = _font(style.title_font_size)
    draw.text((16, 11), title, fill=style.text_color, font=title_font)
    right_width = _text_width(draw, right_title, title_font)
    draw.text(
        (width - right_width - 17, 11),
        right_title,
        fill=style.secondary_text_color,
        font=title_font,
    )
    return panel, draw


def _display_points(
    projection: _Projection,
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    return tuple(projection.point(point) for point in points)


def _source_box_for_points(
    projection: _Projection,
    points: tuple[tuple[float, float], ...],
    target_width: int,
    target_height: int,
    *,
    padding_fraction: float,
) -> tuple[int, int, int, int]:
    display_width = projection.display_width
    display_height = projection.display_height
    transformed = _display_points(projection, points)
    if transformed:
        left = min(point[0] for point in transformed)
        top = min(point[1] for point in transformed)
        right = max(point[0] for point in transformed)
        bottom = max(point[1] for point in transformed)
        span_x = max(1.0, right - left)
        span_y = max(1.0, bottom - top)
        left -= span_x * padding_fraction
        right += span_x * padding_fraction
        top -= span_y * padding_fraction
        bottom += span_y * padding_fraction
    else:
        left, top, right, bottom = 0.0, 0.0, float(display_width), float(display_height)
    left = max(0.0, left)
    top = max(0.0, top)
    right = min(float(display_width), right)
    bottom = min(float(display_height), bottom)
    target_aspect = float(target_width) / float(target_height)
    center_x = (left + right) / 2.0
    center_y = (top + bottom) / 2.0
    span_x = max(1.0, right - left)
    span_y = max(1.0, bottom - top)
    if span_x / span_y < target_aspect:
        desired_x = span_y * target_aspect
        if desired_x <= display_width:
            span_x = desired_x
        else:
            span_x = float(display_width)
            span_y = span_x / target_aspect
    else:
        desired_y = span_x / target_aspect
        if desired_y <= display_height:
            span_y = desired_y
        else:
            span_y = float(display_height)
            span_x = span_y * target_aspect
    left = min(max(0.0, center_x - span_x / 2.0), display_width - span_x)
    top = min(max(0.0, center_y - span_y / 2.0), display_height - span_y)
    right = left + span_x
    bottom = top + span_y
    int_left = max(0, int(math.floor(left)))
    int_top = max(0, int(math.floor(top)))
    int_right = min(display_width, int(math.ceil(right)))
    int_bottom = min(display_height, int(math.ceil(bottom)))
    if int_right <= int_left or int_bottom <= int_top:
        raise ValueError("Debug Analysis source viewport is empty")
    return int_left, int_top, int_right, int_bottom


def _viewport(
    projection: _Projection,
    points: tuple[tuple[float, float], ...],
    target_box: tuple[int, int, int, int],
    *,
    padding_fraction: float,
) -> _Viewport:
    target_left, target_top, target_right, target_bottom = target_box
    source_box = _source_box_for_points(
        projection,
        points,
        target_right - target_left,
        target_bottom - target_top,
        padding_fraction=padding_fraction,
    )
    return _Viewport(projection, source_box, target_box)


def _paste_source(
    panel: Image.Image,
    source: Image.Image,
    viewport: _Viewport,
) -> None:
    left, top, right, bottom = viewport.target_box
    crop = source.crop(viewport.source_box).resize(
        (right - left, bottom - top),
        Image.Resampling.LANCZOS,
    )
    panel.paste(crop, (left, top))


def _draw_dashed_polyline(
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


def _fill_polygon(
    draw: ImageDraw.ImageDraw,
    polygon: tuple[tuple[float, float], ...],
    color: tuple[int, int, int],
    alpha: float,
    *,
    viewport: _Viewport | None = None,
) -> None:
    if len(polygon) >= 3:
        target = viewport.polygon(polygon) if viewport is not None else polygon
        draw.polygon(target, fill=(*color, int(round(255.0 * alpha))))


def _source_line_points(observation: object) -> tuple[tuple[float, float], ...]:
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
            ordinal = global_ordinals.get((geometry.lane_id, geometry.lane_ordinal))
            if ordinal is not None:
                values.append((ordinal, geometry))
    return tuple(sorted(values, key=lambda item: item[0]))


def _safe_crop_envelopes(
    detection: FinalDetection,
) -> tuple[SafeCropEnvelope, ...]:
    return detection.candidate.geometry.safe_crop_envelopes


def _presentation_points(
    detection: FinalDetection,
) -> tuple[tuple[float, float], ...]:
    canonical = tuple(
        point
        for _ordinal, geometry in _geometry_by_identity(detection)
        for point in geometry.canonical_source_polygon
    )
    protected = tuple(
        point
        for geometry in _safe_crop_envelopes(detection)
        for polygon in (
            geometry.placement_source_footprint,
            geometry.required_source_footprint,
            geometry.constrained_source_footprint,
        )
        for point in polygon
    )
    return canonical + protected


def _projection(workspace: DetectionWorkspace) -> _Projection:
    height, width = workspace.source_gray.shape
    return _Projection(
        source_width=width,
        source_height=height,
        rotate_clockwise=workspace.boundary_measurement_field.layout == "vertical",
    )


def _source_image(
    workspace: DetectionWorkspace,
    render_cache: DebugRenderCache,
) -> tuple[Image.Image, _Projection]:
    projection = _projection(workspace)
    return (
        cached_source_image(
            render_cache,
            workspace.source_gray,
            rotate_clockwise=projection.rotate_clockwise,
        ),
        projection,
    )


def _draw_label_chip(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    style: DebugStyleParameters,
    *,
    filled: bool = True,
) -> None:
    font = _font(style.frame_label_font_size)
    x, y = xy
    width = _text_width(draw, text, font) + 10
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
    draw.text((x + 5, y + 3), text, fill=text_color, font=font)


def _boundary_points(
    geometry: FrameFormatPlacement,
    role: BoundaryRole,
) -> tuple[tuple[float, float], tuple[float, float]]:
    boundary = geometry.start if role == BoundaryRole.START else geometry.end
    line = boundary.line
    closest = sorted(
        geometry.canonical_source_polygon,
        key=lambda point: abs(
            line.normal_x * point[0] + line.normal_y * point[1] - line.offset_px
        ),
    )[:2]
    return closest[0], closest[1]


def _draw_selected_start_end(
    draw: ImageDraw.ImageDraw,
    geometries: tuple[tuple[int, FrameFormatPlacement], ...],
    viewport: _Viewport,
    style: DebugStyleParameters,
) -> None:
    font = _font(style.annotation_font_size)
    viewport_top = viewport.target_box[1]
    for index, (_ordinal, geometry) in enumerate(geometries):
        roles = (
            ((BoundaryRole.END,) if index < len(geometries) - 1 else ())
            + ((BoundaryRole.START,) if index > 0 else ())
        )
        for role in roles:
            source_points = _boundary_points(geometry, role)
            points = tuple(viewport.point(point) for point in source_points)
            upper, lower = sorted(points, key=lambda point: point[1])
            dy = lower[1] - upper[1]
            dx = lower[0] - upper[0]
            extension_y = max(float(style.annotation_extension), upper[1] - viewport_top + 7.0)
            extension_x = 0.0 if abs(dy) <= 1.0e-9 else dx * extension_y / dy
            line_top = (upper[0] - extension_x, upper[1] - extension_y)
            draw.line(
                (line_top, lower),
                fill=style.selected_boundary_color,
                width=2,
            )
            text = role.value.upper()
            text_width = _text_width(draw, text, font)
            text_x = (
                line_top[0] + 4
                if role == BoundaryRole.START
                else line_top[0] - text_width - 4
            )
            target_left, _top, target_right, _bottom = viewport.target_box
            text_x = min(max(target_left, text_x), target_right - text_width)
            draw.text(
                (text_x, max(style.panel_title_height + 3, line_top[1] - 17)),
                text,
                fill=style.selected_boundary_color,
                font=font,
            )


def _draw_detected_top_bottom(
    draw: ImageDraw.ImageDraw,
    detection: FinalDetection,
    viewport: _Viewport,
    style: DebugStyleParameters,
) -> set[BoundaryRole]:
    roles: set[BoundaryRole] = set()
    for lane in detection.candidate.geometry.lane_reconstructions:
        for observation in lane.raw_top_bottom_observations:
            source_points = _source_line_points(observation)
            if not source_points:
                continue
            points = tuple(viewport.point(point) for point in source_points)
            _draw_dashed_polyline(
                draw,
                points,
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
    geometries: tuple[tuple[int, FrameFormatPlacement], ...],
    viewport: _Viewport,
    style: DebugStyleParameters,
) -> set[BoundaryRole]:
    roles: set[BoundaryRole] = set()
    for _ordinal, geometry in geometries:
        for boundary in (geometry.top, geometry.bottom):
            source_points = _source_line_points(boundary)
            if not source_points:
                continue
            draw.line(
                tuple(viewport.point(point) for point in source_points),
                fill=style.selected_edge_color,
                width=style.evidence_line_width,
            )
            roles.add(boundary.role)
    return roles


def _cross_axis_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    panel_width = style.canvas_width - 2 * style.outer_margin
    panel, draw = _panel_base(
        panel_width,
        style.cross_axis_panel_height,
        DEBUG_ANALYSIS_PANEL_LABELS[0],
        "DETECTED EVIDENCE / SELECTED EDGE",
        style,
    )
    source, projection = _source_image(workspace, render_cache)
    target_box = (
        style.panel_media_inset_x,
        style.cross_axis_media_top,
        panel_width - style.panel_media_inset_x,
        style.cross_axis_media_top + style.cross_axis_media_height,
    )
    viewport = _viewport(
        projection,
        _presentation_points(detection),
        target_box,
        padding_fraction=0.018,
    )
    _paste_source(panel, source, viewport)
    draw = ImageDraw.Draw(panel)
    geometries = _geometry_by_identity(detection)
    detected = _draw_detected_top_bottom(draw, detection, viewport, style)
    selected = _draw_selected_top_bottom(draw, geometries, viewport, style)
    top_y = style.panel_title_height + 6
    bottom_y = style.cross_axis_panel_height - 27
    left = style.panel_media_inset_x
    if BoundaryRole.TOP in detected:
        _draw_label_chip(
            draw,
            (left, top_y),
            "DETECTED TOP",
            style.detected_edge_color,
            style,
            filled=False,
        )
    if BoundaryRole.TOP in selected:
        _draw_label_chip(
            draw,
            (left + 118, top_y),
            "SELECTED TOP",
            style.selected_edge_color,
            style,
        )
    if BoundaryRole.BOTTOM in selected:
        _draw_label_chip(
            draw,
            (left, bottom_y),
            "SELECTED BOTTOM",
            style.selected_edge_color,
            style,
        )
    if BoundaryRole.BOTTOM in detected:
        _draw_label_chip(
            draw,
            (left + 138, bottom_y),
            "DETECTED BOTTOM",
            style.detected_edge_color,
            style,
            filled=False,
        )
    return np.asarray(panel)


def _draw_detected_start_end(
    draw: ImageDraw.ImageDraw,
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    viewport: _Viewport,
    style: DebugStyleParameters,
) -> bool:
    layout = workspace.boundary_measurement_field.layout
    source_lanes = {
        lane.domain.lane_id: lane for lane in workspace.source_core.lanes
    }
    found = False
    for lane in detection.candidate.geometry.lane_reconstructions:
        source_lane = source_lanes.get(lane.lane_id)
        if source_lane is None:
            continue
        lane_box = source_lane_box(source_lane, layout)
        for region in lane.side_transition_regions:
            coordinate = region.proposal_position_interval_px.center
            source_points = (
                ((coordinate, lane_box.top), (coordinate, lane_box.bottom))
                if layout == "horizontal"
                else ((lane_box.left, coordinate), (lane_box.right, coordinate))
            )
            _draw_dashed_polyline(
                draw,
                tuple(viewport.point(point) for point in source_points),
                style.detected_transition_color,
                style.raw_transition_line_width,
                style.line_dash_length,
                style.line_dash_gap,
                closed=False,
            )
            found = True
    return found


def _long_axis_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    panel_width = style.canvas_width - 2 * style.outer_margin
    panel, _draw = _panel_base(
        panel_width,
        style.long_axis_panel_height,
        DEBUG_ANALYSIS_PANEL_LABELS[1],
        "DETECTED TRANSITION / SELECTED BOUNDARY",
        style,
    )
    source, projection = _source_image(workspace, render_cache)
    geometries = _geometry_by_identity(detection)
    media_left = style.panel_media_inset_x
    media_right = panel_width - style.panel_media_inset_x
    media_top = style.long_axis_media_top
    media_bottom = media_top + style.long_axis_media_height
    viewport = _viewport(
        projection,
        _presentation_points(detection),
        (media_left, media_top, media_right, media_bottom),
        padding_fraction=0.018,
    )
    _paste_source(panel, source, viewport)
    draw = ImageDraw.Draw(panel)
    detected = _draw_detected_start_end(
        draw,
        workspace,
        detection,
        viewport,
        style,
    )
    _draw_selected_start_end(draw, geometries, viewport, style)
    if not geometries:
        note = "NO SELECTED START / END · CANDIDATE AUDIT ONLY"
        font = _font(style.header_detail_font_size)
        note_width = _text_width(draw, note, font)
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
            font=font,
        )
    footer_y = style.long_axis_panel_height - 27
    if detected:
        _draw_label_chip(
            draw,
            (media_left, footer_y),
            "RAW / DETECTED",
            style.detected_transition_color,
            style,
            filled=False,
        )
    if geometries:
        _draw_label_chip(
            draw,
            (media_left + 132, footer_y),
            "SELECTED START / END",
            style.selected_boundary_color,
            style,
            filled=False,
        )
    return np.asarray(panel)


def _draw_hatched_polygon(
    panel: Image.Image,
    polygon: tuple[tuple[float, float], ...],
    color: tuple[int, int, int],
) -> Image.Image:
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    hatch = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(hatch)
    left = int(math.floor(min(point[0] for point in polygon)))
    top = int(math.floor(min(point[1] for point in polygon)))
    right = int(math.ceil(max(point[0] for point in polygon)))
    bottom = int(math.ceil(max(point[1] for point in polygon)))
    for offset in range(left - (bottom - top), right + (bottom - top), 6):
        draw.line((offset, bottom, offset + (bottom - top), top), fill=(*color, 210), width=2)
    hatch.putalpha(Image.composite(hatch.getchannel("A"), Image.new("L", panel.size, 0), mask))
    return Image.alpha_composite(panel.convert("RGBA"), hatch).convert("RGB")


def _protected_output_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    panel_width = style.canvas_width - 2 * style.outer_margin
    right_title = (
        f"SOURCE ATOMIC · {detection.output_slot_count} TIFF ELIGIBLE"
        if detection.frame_export_eligible
        else "CANDIDATE AUDIT · NOT EXPORTABLE"
    )
    panel, _draw = _panel_base(
        panel_width,
        style.output_panel_height,
        DEBUG_ANALYSIS_PANEL_LABELS[2],
        right_title,
        style,
    )
    source, projection = _source_image(workspace, render_cache)
    target_box = (
        style.panel_media_inset_x,
        style.output_media_top,
        panel_width - style.panel_media_inset_x,
        style.output_media_top + style.output_media_height,
    )
    viewport = _viewport(
        projection,
        _presentation_points(detection),
        target_box,
        padding_fraction=0.018,
    )
    _paste_source(panel, source, viewport)
    identities = {
        (item.lane_id, item.lane_ordinal): item
        for item in detection.output_slot_identities
    }
    budgets = {
        item.geometry_id: item
        for item in detection.candidate.geometry.direct_use_budget_assessments
    }
    overlay = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    envelopes = _safe_crop_envelopes(detection)
    for envelope in envelopes:
        identity = identities[(envelope.lane_id, envelope.lane_ordinal)]
        color = _frame_color(identity.global_output_ordinal)
        _fill_polygon(
            overlay_draw,
            envelope.placement_source_footprint,
            color,
            style.frame_fill_alpha,
            viewport=viewport,
        )
        _fill_polygon(
            overlay_draw,
            envelope.constrained_source_footprint,
            color,
            style.safe_fill_alpha,
            viewport=viewport,
        )
    panel = Image.alpha_composite(panel.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(panel)
    for envelope in envelopes:
        identity = identities[(envelope.lane_id, envelope.lane_ordinal)]
        color = _frame_color(identity.global_output_ordinal)
        _draw_dashed_polyline(
            draw,
            viewport.polygon(envelope.required_source_footprint),
            style.safety_envelope_color,
            style.retained_line_width,
            style.line_dash_length,
            style.line_dash_gap,
            closed=True,
        )
        constrained = viewport.polygon(envelope.constrained_source_footprint)
        draw.line(
            constrained + (constrained[0],),
            fill=color,
            width=style.frame_line_width,
        )
        budget = budgets.get(envelope.geometry_id)
        if budget is not None and budget.state.value == "contradicted":
            panel = _draw_hatched_polygon(panel, constrained, style.review_color)
            draw = ImageDraw.Draw(panel)
            label = "BUDGET VIOLATION"
            font = _font(style.annotation_font_size)
            width = _text_width(draw, label, font)
            x = max(target_box[0], min(target_box[2] - width, constrained[0][0]))
            draw.text(
                (x, target_box[1] - 35),
                label,
                fill=style.review_color,
                font=font,
            )
        left = max(
            target_box[0] + 4,
            int(math.floor(min(point[0] for point in constrained))) + 4,
        )
        top = max(
            target_box[1] + 4,
            int(math.floor(min(point[1] for point in constrained))) + 4,
        )
        _draw_label_chip(
            draw,
            (left, top),
            f"F{identity.global_output_ordinal}",
            color,
            style,
        )
    footer_font = _font(style.annotation_font_size)
    if envelopes:
        footer = (
            "RETAINED / REQUIRED · SAFETY ENVELOPE    "
            "FINAL SAFE OUTPUT · COLORED OVERLAY"
        )
    else:
        footer = "NO SAFETY ENVELOPE · NO OFFICIAL OUTPUT"
        note = "NO SAFE OUTPUT · SOURCE ATOMIC · 0 OFFICIAL TIFF"
        note_font = _font(style.header_detail_font_size)
        note_width = _text_width(draw, note, note_font)
        center_y = (target_box[1] + target_box[3]) // 2
        draw.rectangle(
            (
                (panel_width - note_width) // 2 - 12,
                center_y - 15,
                (panel_width + note_width) // 2 + 12,
                center_y + 15,
            ),
            fill=style.panel_background,
        )
        draw.text(
            ((panel_width - note_width) // 2, center_y - 8),
            note,
            fill=style.review_color,
            font=note_font,
        )
    draw.text(
        (19, style.output_panel_height - 25),
        footer,
        fill=style.text_color,
        font=footer_font,
    )
    return np.asarray(panel)


def stack_debug_panels(
    panels: tuple[np.ndarray, ...],
    *,
    style: DebugStyleParameters,
) -> np.ndarray:
    expected_heights = (
        style.cross_axis_panel_height,
        style.long_axis_panel_height,
        style.output_panel_height,
    )
    panel_width = style.canvas_width - 2 * style.outer_margin
    if len(panels) != len(expected_heights) or any(
        panel.shape != (height, panel_width, RGB_CHANNEL_COUNT)
        for panel, height in zip(panels, expected_heights, strict=True)
    ):
        raise ValueError("Debug Analysis panels do not match the fixed grid")
    body_height = sum(expected_heights) + style.panel_gap * 2
    body = np.full(
        (body_height, style.canvas_width, RGB_CHANNEL_COUNT),
        style.canvas_background,
        dtype=np.uint8,
    )
    top = 0
    for panel in panels:
        height = panel.shape[0]
        body[top : top + height, style.outer_margin : style.canvas_width - style.outer_margin] = panel
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
        (height + style.legend_bar_height, style.canvas_width, RGB_CHANNEL_COUNT),
        style.canvas_background,
        dtype=np.uint8,
    )
    panel[:height] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    font = _font(style.legend_font_size)
    widths = tuple(38 + 9 + _text_width(draw, entry.label, font) + 20 for entry in entries)
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
            draw.line((left, center_y, right, center_y), fill=entry.color, width=2)
        elif entry.sample == "dashed":
            _draw_dashed_polyline(
                draw,
                ((left, center_y), (right, center_y)),
                entry.color,
                2,
                style.line_dash_length,
                style.line_dash_gap,
                closed=False,
            )
        else:
            draw.rectangle((left, top, right, bottom), outline=entry.color, width=1)
            if entry.sample == "hatched":
                for offset in range(left - 12, right + 12, 5):
                    draw.line((offset, bottom, offset + 18, top), fill=entry.color, width=1)
        text_x = right + max(6, int(round(9 * scale)))
        draw.text(
            (text_x, center_y - 7),
            entry.label,
            fill=style.secondary_text_color,
            font=font,
        )
        x += natural_width * scale
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
        _cross_axis_panel(workspace, detection, style, render_cache),
        _long_axis_panel(workspace, detection, style, render_cache),
        _protected_output_panel(workspace, detection, style, render_cache),
    )
    canvas = stack_debug_panels(panels, style=style)
    canvas = add_legend_bar(canvas, diagnostics.legend_entries, style)
    canvas = add_status_bar(
        canvas,
        detection,
        configuration,
        profile,
        style,
        terminal_outcome,
    )
    if canvas.shape != (style.canvas_height, style.canvas_width, RGB_CHANNEL_COUNT):
        raise ValueError("Debug Analysis output does not match the fixed design canvas")
    return canvas
