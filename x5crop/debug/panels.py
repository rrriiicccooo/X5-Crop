from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..configuration.diagnostics import (
    DebugStyleParameters,
    DiagnosticsConfiguration,
)
from ..detection.evidence.separator import SeparatorLineObservation
from ..detection.final.model import FinalDetection
from ..detection.grid.model import (
    FrameGridProposal,
    GridCandidateKind,
)
from ..detection.workspace import DetectionWorkspace
from ..domain import Box
from ..run_status import RunTerminalOutcome
from ..utils import RGB_CHANNEL_COUNT
from .canvas import (
    FRAME_FILL_COLORS,
    DebugRenderCache,
    add_panel_label,
    add_panel_label_with_legend,
    cached_preview_gray,
    draw_preview_dashed_rect,
    draw_preview_label,
    draw_preview_rect,
    draw_preview_vertical_line,
    fill_preview_rect,
)
from .status import add_status_bar


DEBUG_ANALYSIS_PANEL_LABELS = (
    "Original gray context",
    "Frame outputs",
    "Separator evidence",
)


@dataclass(frozen=True)
class SeparatorDebugLine:
    x: float
    top: float
    bottom: float
    color: tuple[int, int, int]
    alpha: float
    thickness: int
    dashed: bool
    observation_id: str | None
    selected_kind: GridCandidateKind | None


def _frame_color(global_ordinal: int) -> tuple[int, int, int]:
    if not 1 <= global_ordinal <= len(FRAME_FILL_COLORS):
        raise ValueError(
            "Debug Analysis frame ordinal exceeds the fixed color table"
        )
    return FRAME_FILL_COLORS[global_ordinal - 1]


def _original_gray_panel(
    workspace: DetectionWorkspace,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, _scale = cached_preview_gray(
        render_cache,
        "canonical_gray_work",
        workspace.measurement_cache.gray_work,
        style.preview_max_side,
    )
    return add_panel_label(
        rgb,
        DEBUG_ANALYSIS_PANEL_LABELS[0],
        height=style.label_height,
        origin=style.label_origin,
        background=style.dark_background,
        text_color=style.text_color,
    )


def _provisional_frame_boxes(
    detection: FinalDetection,
) -> tuple[tuple[int, Box], ...]:
    global_ordinals = {
        (identity.lane_id, identity.lane_ordinal):
        identity.global_output_ordinal
        for identity in detection.candidate.output_slot_identities
    }
    provisional: list[tuple[int, Box]] = []
    for selection in detection.candidate.lane_selections:
        proposal = selection.selected_proposal
        if proposal is None:
            continue
        for envelope in proposal.safe_envelopes:
            global_ordinal = global_ordinals.get(
                (envelope.lane_id, envelope.lane_ordinal)
            )
            if global_ordinal is not None:
                provisional.append((global_ordinal, envelope.work_box))
    return tuple(sorted(provisional, key=lambda item: item[0]))


def _frame_outputs_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = cached_preview_gray(
        render_cache,
        "canonical_gray_work",
        workspace.measurement_cache.gray_work,
        style.preview_max_side,
    )
    if detection.frame_export_eligible:
        if len(detection.output_slot_identities) != len(
            detection.protected_envelopes
        ):
            raise ValueError(
                "Debug Analysis final frames require canonical identities"
            )
        frames = tuple(
            (
                identity.global_output_ordinal,
                envelope.protected_work_box,
            )
            for identity, envelope in zip(
                detection.output_slot_identities,
                detection.protected_envelopes,
                strict=True,
            )
        )
        provisional = False
        panel_label = DEBUG_ANALYSIS_PANEL_LABELS[1]
    else:
        frames = _provisional_frame_boxes(detection)
        provisional = True
        panel_label = (
            f"{DEBUG_ANALYSIS_PANEL_LABELS[1]} | "
            + (
                "provisional envelopes - NOT EXPORTABLE"
                if frames
                else "NOT EXPORTABLE"
            )
        )
    for global_ordinal, box in frames:
        color = _frame_color(global_ordinal)
        fill_preview_rect(
            rgb,
            box,
            scale,
            color,
            (
                style.provisional_frame_fill_alpha
                if provisional
                else style.frame_fill_alpha
            ),
        )
        if provisional:
            draw_preview_dashed_rect(
                rgb,
                box,
                scale,
                color,
                style.provisional_frame_line_width,
                dash_length=style.line_dash_length,
                dash_gap=style.line_dash_gap,
            )
        else:
            draw_preview_rect(
                rgb,
                box,
                scale,
                color,
                style.frame_line_width,
            )
        draw_preview_label(
            rgb,
            box,
            scale,
            (
                f"F{global_ordinal} PROVISIONAL"
                if provisional
                else f"F{global_ordinal}"
            ),
            color,
            inset=style.frame_label_inset,
            stroke_width=style.frame_label_stroke_width,
        )
    return add_panel_label(
        rgb,
        panel_label,
        height=style.label_height,
        origin=style.label_origin,
        background=style.dark_background,
        text_color=style.text_color,
    )


def separator_debug_line_plan(
    lane_box: Box,
    raw_lines: tuple[SeparatorLineObservation, ...],
    selected_proposal: FrameGridProposal | None,
    style: DebugStyleParameters,
) -> tuple[SeparatorDebugLine, ...]:
    plan = [
        SeparatorDebugLine(
            x=lane_box.left + float(line.boundary_px),
            top=lane_box.top,
            bottom=lane_box.bottom,
            color=style.raw_separator_color,
            alpha=style.raw_separator_alpha,
            thickness=style.raw_separator_line_width,
            dashed=False,
            observation_id=str(line.observation_id),
            selected_kind=None,
        )
        for line in raw_lines
    ]
    if selected_proposal is None:
        return tuple(plan)
    raw_by_id = {
        line.observation_id: line
        for line in raw_lines
    }
    for corridor in selected_proposal.corridor_candidates:
        if corridor.kind == GridCandidateKind.MODEL_ONLY:
            for interval in (
                corridor.previous_photo_end_px,
                corridor.next_photo_start_px,
            ):
                plan.append(
                    SeparatorDebugLine(
                        x=lane_box.left + interval.center,
                        top=lane_box.top,
                        bottom=lane_box.bottom,
                        color=style.selected_model_only_color,
                        alpha=1.0,
                        thickness=style.selected_separator_line_width,
                        dashed=True,
                        observation_id=None,
                        selected_kind=corridor.kind,
                    )
                )
            continue
        observation = corridor.observation
        if observation is None:
            raise ValueError("observed Grid corridor lost its observation")
        color = (
            style.selected_edge_pair_color
            if corridor.kind == GridCandidateKind.OBSERVED_EDGE_PAIR
            else style.selected_one_sided_color
        )
        for observation_id in observation.source_line_ids:
            line = raw_by_id.get(observation_id)
            if line is None:
                raise ValueError(
                    "selected separator observation is absent from raw field"
                )
            plan.append(
                SeparatorDebugLine(
                    x=lane_box.left + float(line.boundary_px),
                    top=lane_box.top,
                    bottom=lane_box.bottom,
                    color=color,
                    alpha=1.0,
                    thickness=style.selected_separator_line_width,
                    dashed=False,
                    observation_id=str(line.observation_id),
                    selected_kind=corridor.kind,
                )
            )
    return tuple(plan)


def _separator_evidence_panel(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    style = diagnostics.style
    rgb, scale = cached_preview_gray(
        render_cache,
        "canonical_gray_work",
        workspace.measurement_cache.gray_work,
        style.preview_max_side,
    )
    selections = {
        selection.lane_id: selection
        for selection in detection.candidate.lane_selections
    }
    lanes = {
        lane.domain.lane_id: lane
        for lane in workspace.source_core.lanes
    }
    for field in workspace.separator_fields:
        lane = lanes[field.lane_id]
        selection = selections.get(field.lane_id)
        selected_proposal = (
            None if selection is None else selection.selected_proposal
        )
        for line in separator_debug_line_plan(
            lane.domain.work_box,
            field.lines,
            selected_proposal,
            style,
        ):
            draw_preview_vertical_line(
                rgb,
                line.x,
                line.top,
                line.bottom,
                scale,
                line.color,
                line.thickness,
                alpha=line.alpha,
                dashed=line.dashed,
                dash_length=style.line_dash_length,
                dash_gap=style.line_dash_gap,
            )
    return add_panel_label_with_legend(
        rgb,
        DEBUG_ANALYSIS_PANEL_LABELS[2],
        diagnostics.separator_legend_entries,
        label_height=style.label_height,
        label_origin=style.label_origin,
        legend_row_height=style.legend_row_height,
        legend_sample_width=style.legend_sample_width,
        legend_text_gap=style.legend_text_gap,
        background=style.dark_background,
        text_color=style.text_color,
        line_width=style.selected_separator_line_width,
        dash_length=style.line_dash_length,
        dash_gap=style.line_dash_gap,
    )


def stack_debug_panels(
    panels: tuple[np.ndarray, np.ndarray, np.ndarray],
    *,
    horizontal: bool,
    style: DebugStyleParameters,
) -> np.ndarray:
    panel_spacing = style.panel_spacing
    if horizontal:
        max_height = max(panel.shape[0] for panel in panels)
        total_width = (
            sum(panel.shape[1] for panel in panels)
            + panel_spacing * (len(panels) - 1)
        )
        canvas = np.full(
            (max_height, total_width, RGB_CHANNEL_COUNT),
            style.panel_background,
            dtype=np.uint8,
        )
        left = 0
        for panel in panels:
            height, width = panel.shape[:2]
            canvas[:height, left : left + width] = panel
            left += width + panel_spacing
        return canvas
    max_width = max(panel.shape[1] for panel in panels)
    total_height = (
        sum(panel.shape[0] for panel in panels)
        + panel_spacing * (len(panels) - 1)
    )
    canvas = np.full(
        (total_height, max_width, RGB_CHANNEL_COUNT),
        style.panel_background,
        dtype=np.uint8,
    )
    top = 0
    for panel in panels:
        height, width = panel.shape[:2]
        canvas[top : top + height, :width] = panel
        top += height + panel_spacing
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
        _original_gray_panel(workspace, style, render_cache),
        _frame_outputs_panel(
            workspace,
            detection,
            style,
            render_cache,
        ),
        _separator_evidence_panel(
            workspace,
            detection,
            diagnostics,
            render_cache,
        ),
    )
    gray_work = workspace.measurement_cache.gray_work
    canvas = stack_debug_panels(
        panels,
        horizontal=gray_work.shape[1] < gray_work.shape[0],
        style=style,
    )
    return add_status_bar(
        canvas,
        detection,
        style,
        terminal_outcome,
    )
