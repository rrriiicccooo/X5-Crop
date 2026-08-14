"""Selected-only safety and direct-use Debug Analysis panel."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from ..configuration.diagnostics import DebugStyleParameters
from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from .canvas import DebugRenderCache
from .panel_facts import (
    axis_authority_summaries,
    root_gate_summary,
    safe_crop_envelopes,
    selection_summary,
    source_image,
)
from .panel_layout import (
    PresentationGrid,
    draw_dashed_polyline,
    draw_label_chip,
    fill_polygon,
    font,
    frame_color,
    panel_base,
    paste_source,
    text_width,
    viewport,
)


def draw_hatched_polygon(
    panel: Image.Image,
    polygon: tuple[tuple[float, float], ...],
    color: tuple[int, int, int],
    border_width: int,
) -> Image.Image:
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).line(
        polygon + (polygon[0],),
        fill=255,
        width=border_width,
        joint="curve",
    )
    hatch = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(hatch)
    left = int(math.floor(min(point[0] for point in polygon)))
    top = int(math.floor(min(point[1] for point in polygon)))
    right = int(math.ceil(max(point[0] for point in polygon)))
    bottom = int(math.ceil(max(point[1] for point in polygon)))
    for offset in range(left - (bottom - top), right + (bottom - top), 6):
        draw.line(
            (offset, bottom, offset + (bottom - top), top),
            fill=(*color, 210),
            width=2,
        )
    hatch.putalpha(
        Image.composite(
            hatch.getchannel("A"),
            Image.new("L", panel.size, 0),
            mask,
        )
    )
    return Image.alpha_composite(panel.convert("RGBA"), hatch).convert("RGB")


def keep_evidence_inside_media(
    base: Image.Image,
    evidence: Image.Image,
    target_box: tuple[int, int, int, int],
) -> Image.Image:
    clipped = base.copy()
    clipped.paste(evidence.crop(target_box), target_box[:2])
    return clipped


def protected_output_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
    grid: PresentationGrid,
) -> np.ndarray:
    panel_width = style.canvas_width - 2 * style.outer_margin
    _cross_authority, _sequence_authority, right_title = (
        axis_authority_summaries(detection)
    )
    panel, _draw = panel_base(
        panel_width,
        grid.output_panel_height,
        "03 · FINAL SAFE OUTPUT",
        right_title,
        style,
    )
    source, projection = source_image(workspace, render_cache)
    selected_viewport = viewport(
        projection,
        (
            style.panel_media_inset_x,
            style.output_media_top,
            panel_width - style.panel_media_inset_x,
            style.output_media_top + grid.media_height,
        ),
    )
    target_box = selected_viewport.target_box
    paste_source(panel, source, selected_viewport)
    media_base = panel.copy()
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
    envelopes = safe_crop_envelopes(detection)
    budget_labels: list[tuple[int, str]] = []
    for envelope in envelopes:
        identity = identities[(envelope.lane_id, envelope.lane_ordinal)]
        color = frame_color(identity.global_output_ordinal)
        fill_polygon(
            overlay_draw,
            envelope.placement_source_footprint,
            color,
            style.frame_fill_alpha,
            selected_viewport=selected_viewport,
        )
        fill_polygon(
            overlay_draw,
            envelope.constrained_source_footprint,
            color,
            style.safe_fill_alpha,
            selected_viewport=selected_viewport,
        )
    panel = Image.alpha_composite(panel.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(panel)
    for envelope in envelopes:
        identity = identities[(envelope.lane_id, envelope.lane_ordinal)]
        color = frame_color(identity.global_output_ordinal)
        draw_dashed_polyline(
            draw,
            selected_viewport.polygon(envelope.required_source_footprint),
            style.safety_envelope_color,
            style.retained_line_width,
            style.line_dash_length,
            style.line_dash_gap,
            closed=True,
        )
        constrained = selected_viewport.polygon(
            envelope.constrained_source_footprint
        )
        draw.line(
            constrained + (constrained[0],),
            fill=color,
            width=style.frame_line_width,
        )
        budget = budgets.get(envelope.geometry_id)
        if budget is not None and budget.state.value == "contradicted":
            panel = draw_hatched_polygon(
                panel,
                constrained,
                style.review_color,
                style.budget_hatch_border_width,
            )
            draw = ImageDraw.Draw(panel)
            failed_roles = "/".join(
                edge.role.value.upper()
                for edge in budget.edge_assessments
                if not edge.within_limit
            )
            budget_labels.append(
                (
                    max(
                        target_box[0],
                        int(math.floor(min(point[0] for point in constrained))),
                    ),
                    f"F{identity.global_output_ordinal} · BUDGET {failed_roles}",
                )
            )
        left = max(
            target_box[0] + 4,
            int(math.floor(min(point[0] for point in constrained))) + 4,
        )
        top = max(
            target_box[1] + 4,
            int(math.floor(min(point[1] for point in constrained))) + 4,
        )
        draw_label_chip(
            draw,
            (left, top),
            f"F{identity.global_output_ordinal}",
            color,
            style,
        )
    panel = keep_evidence_inside_media(media_base, panel, target_box)
    draw = ImageDraw.Draw(panel)
    budget_font = font(style.annotation_font_size)
    previous_right = target_box[0]
    for proposed_x, label in sorted(budget_labels):
        label_width = text_width(draw, label, budget_font)
        x = max(previous_right + style.boundary_label_horizontal_gap, proposed_x)
        x = min(x, target_box[2] - label_width)
        draw.text(
            (x, target_box[1] - 23),
            label,
            fill=style.review_color,
            font=budget_font,
        )
        previous_right = x + label_width
    footer_font = font(style.annotation_font_size)
    if envelopes:
        footer = (
            "RETAINED / REQUIRED · SAFETY ENVELOPE    "
            "FINAL SAFE OUTPUT · COLORED OVERLAY"
        )
    else:
        footer = "NO SAFETY ENVELOPE · NO OFFICIAL OUTPUT"
        note = "NO SAFE OUTPUT · SOURCE ATOMIC · 0 OFFICIAL TIFF"
        note_font = font(style.header_detail_font_size)
        note_width = text_width(draw, note, note_font)
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
    footer = f"{footer}    {selection_summary(detection)}"
    draw.text(
        (19, grid.output_panel_height - 43),
        footer,
        fill=style.text_color,
        font=footer_font,
    )
    draw.text(
        (19, grid.output_panel_height - 23),
        root_gate_summary(detection),
        fill=(
            style.approved_color
            if detection.decision.passed
            else style.review_color
        ),
        font=footer_font,
    )
    return np.asarray(panel)
