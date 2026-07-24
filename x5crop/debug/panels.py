from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ..detection.final.model import FinalDetection
from ..detection.candidate.model import AssessedCandidate
from ..detection.evidence.photo_edges import PhotoEdgePairEvidence
from ..detection.physical.short_axis import SharedShortAxisPlan
from ..detection.workspace import DetectionWorkspace
from ..domain import Box, EvidenceState, FrameCropEnvelope
from ..detection.physical.model import ReviewOnlyContainment
from ..geometry.boxes import map_work_box
from ..geometry.layout import is_horizontal_layout
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
    add_panel_label_with_legend,
    cached_preview_gray,
    draw_preview_dashed_rect,
    draw_preview_rect,
    draw_preview_segment,
    fill_preview_rect,
)
from .separators import draw_separator_overlay
from .status import add_status_bar


def make_debug_preview_rgb(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    gray = workspace.gray
    geometry = debug_geometry(gray, detection, selected_candidate)
    rgb, scale = cached_preview_gray(
        render_cache,
        "original_gray",
        gray,
        style.preview_max_side,
    )
    display_boxes = geometry.final_boxes or tuple(
        item.box for item in geometry.frame_crop_envelopes
    )
    for index, box in enumerate(display_boxes):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, style.frame_fill_alpha)
        draw_preview_dashed_rect(
            rgb,
            box,
            scale,
            style.frame_crop_envelope_color,
            style.frame_crop_envelope_line_width,
            dash_length=style.line_dash_length,
            dash_gap=style.line_dash_gap,
        )
    for box in geometry.frame_slot_boxes:
        draw_preview_rect(
            rgb,
            box,
            scale,
            style.frame_slot_color,
            style.frame_slot_line_width,
        )
    for box in geometry.sequence_inferred_slot_boxes:
        draw_preview_dashed_rect(
            rgb,
            box,
            scale,
            style.sequence_inferred_slot_color,
            style.sequence_inferred_slot_line_width,
            dash_length=style.line_dash_length,
            dash_gap=style.line_dash_gap,
        )
    if geometry.containment_fallback is not None:
        draw_preview_rect(
            rgb,
            geometry.containment_fallback,
            scale,
            style.raw_observation_color,
            style.containment_fallback_line_width,
        )
    draw_photo_edge_overlay(
        rgb,
        workspace.mapped_photo_edge_pairs,
        workspace.shared_short_axes,
        workspace.measurement_cache.layout,
        workspace.measurement_cache.gray_work.shape[1],
        scale,
        style,
        include_search_corridors=False,
    )
    return rgb


def _work_point(
    layout: str,
    coordinate: float,
    position: float,
) -> tuple[float, float]:
    if is_horizontal_layout(layout):
        return float(coordinate), float(position)
    return float(position), float(coordinate)


def _draw_work_segment(
    rgb: np.ndarray,
    layout: str,
    coordinate_start: float,
    position_start: float,
    coordinate_end: float,
    position_end: float,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
    style: DebugStyleParameters,
    *,
    dashed: bool,
) -> None:
    draw_preview_segment(
        rgb,
        _work_point(layout, coordinate_start, position_start),
        _work_point(layout, coordinate_end, position_end),
        scale,
        color,
        thickness,
        dash_length=style.line_dash_length if dashed else None,
        dash_gap=style.line_dash_gap if dashed else None,
    )


def _draw_search_corridors(
    rgb: np.ndarray,
    evidence: PhotoEdgePairEvidence,
    layout: str,
    scale: float,
    style: DebugStyleParameters,
) -> None:
    for corridor in evidence.search_corridors:
        coordinates = (
            0.0,
            0.5 * float(corridor.work_long_axis_px - 1),
            float(corridor.work_long_axis_px - 1),
        )
        for nominal in (
            corridor.nominal_top_px,
            corridor.nominal_bottom_px,
        ):
            _draw_work_segment(
                rgb,
                layout,
                coordinates[0],
                nominal,
                coordinates[-1],
                nominal,
                scale,
                style.dimension_hypothesis_color,
                style.photo_edge_confidence_line_width,
                style,
                dashed=True,
            )
        for top in (True, False):
            intervals = tuple(
                corridor.side_interval_at(coordinate, top=top)
                for coordinate in coordinates
            )
            halo_intervals = tuple(
                type(interval)(
                    max(
                        0.0,
                        interval.minimum
                        - float(corridor.measurement_halo_short_px),
                    ),
                    min(
                        float(corridor.work_short_axis_px - 1),
                        interval.maximum
                        + float(corridor.measurement_halo_short_px),
                    ),
                )
                for interval in intervals
            )
            for bound in ("minimum", "maximum"):
                for left_index in range(len(coordinates) - 1):
                    _draw_work_segment(
                        rgb,
                        layout,
                        coordinates[left_index],
                        getattr(intervals[left_index], bound),
                        coordinates[left_index + 1],
                        getattr(
                            intervals[left_index + 1],
                            bound,
                        ),
                        scale,
                        style.dimension_hypothesis_color,
                        style.photo_edge_confidence_line_width,
                        style,
                        dashed=True,
                    )
                    _draw_work_segment(
                        rgb,
                        layout,
                        coordinates[left_index],
                        getattr(halo_intervals[left_index], bound),
                        coordinates[left_index + 1],
                        getattr(
                            halo_intervals[left_index + 1],
                            bound,
                        ),
                        scale,
                        style.raw_observation_color,
                        style.photo_edge_confidence_line_width,
                        style,
                        dashed=True,
                    )


def _draw_pair_evidence(
    rgb: np.ndarray,
    evidence: PhotoEdgePairEvidence,
    layout: str,
    scale: float,
    style: DebugStyleParameters,
) -> None:
    selected = evidence.selected_pair
    selected_fragment_ids = (
        frozenset()
        if selected is None
        else frozenset(
            (*selected.top_fragment_ids, *selected.bottom_fragment_ids)
        )
    )
    for fragment in evidence.fragment_summaries:
        start = fragment.long_axis_footprint.minimum
        end = fragment.long_axis_footprint.maximum
        color = (
            style.corroborated_overlap_color
            if fragment.fragment_id in selected_fragment_ids
            else style.raw_observation_color
        )
        _draw_work_segment(
            rgb,
            layout,
            start,
            fragment.short_axis_position_interval.midpoint,
            end,
            fragment.short_axis_position_interval.midpoint,
            scale,
            color,
            style.photo_edge_line_width,
            style,
            dashed=fragment.censored,
        )
        for bound in (
            fragment.short_axis_position_interval.minimum,
            fragment.short_axis_position_interval.maximum,
        ):
            _draw_work_segment(
                rgb,
                layout,
                start,
                bound,
                end,
                bound,
                scale,
                color,
                style.photo_edge_confidence_line_width,
                style,
                dashed=True,
            )
    active_ids = {
        identity
        for fragment in evidence.fragment_summaries
        for identity in fragment.active_observation_ids
    }
    witness_ids = {
        identity
        for fragment in evidence.fragment_summaries
        for identity in fragment.minimum_support_witness_ids
    }
    for observation in evidence.audit_observations:
        if observation.observation_id not in active_ids | witness_ids:
            continue
        _draw_work_segment(
            rgb,
            layout,
            observation.long_axis_footprint.minimum,
            observation.short_axis_position_interval.midpoint,
            observation.long_axis_footprint.maximum,
            observation.short_axis_position_interval.midpoint,
            scale,
            (
                style.measured_boundary_color
                if observation.observation_id in active_ids
                else style.corroborated_overlap_color
            ),
            style.photo_edge_line_width,
            style,
            dashed=False,
        )
    visible_hypotheses = tuple(
        hypothesis
        for hypothesis in evidence.hypotheses
        if hypothesis.geometry is not None
        and (
            hypothesis is selected
            or hypothesis.state != EvidenceState.CONTRADICTED
        )
    )
    for hypothesis in visible_hypotheses:
        assert hypothesis.geometry is not None
        color = (
            style.corroborated_overlap_color
            if hypothesis is selected
            else style.dimension_hypothesis_color
        )
        end = float(hypothesis.geometry.work_long_axis_extent_px - 1)
        for top in (True, False):
            start_interval = hypothesis.geometry.edge_position_interval(
                0.0,
                top=top,
            )
            end_interval = hypothesis.geometry.edge_position_interval(
                end,
                top=top,
            )
            _draw_work_segment(
                rgb,
                layout,
                0.0,
                start_interval.midpoint,
                end,
                end_interval.midpoint,
                scale,
                color,
                style.photo_edge_line_width,
                style,
                dashed=False,
            )
            for start_bound, end_bound in (
                (start_interval.minimum, end_interval.minimum),
                (start_interval.maximum, end_interval.maximum),
            ):
                _draw_work_segment(
                    rgb,
                    layout,
                    0.0,
                    start_bound,
                    end,
                    end_bound,
                    scale,
                    color,
                    style.photo_edge_confidence_line_width,
                    style,
                    dashed=True,
                )


def _draw_shared_short_axes(
    rgb: np.ndarray,
    plans: tuple[SharedShortAxisPlan, ...],
    work_long_axis_px: int,
    layout: str,
    scale: float,
    style: DebugStyleParameters,
) -> None:
    for plan in plans:
        if plan.span is None:
            continue
        for edge in (plan.top, plan.bottom):
            _draw_work_segment(
                rgb,
                layout,
                0.0,
                edge.midpoint,
                float(max(0, work_long_axis_px - 1)),
                edge.midpoint,
                scale,
                style.measured_boundary_color,
                style.photo_edge_line_width,
                style,
                dashed=False,
            )
            for bound in (edge.minimum, edge.maximum):
                _draw_work_segment(
                    rgb,
                    layout,
                    0.0,
                    bound,
                    float(max(0, work_long_axis_px - 1)),
                    bound,
                    scale,
                    style.measured_boundary_color,
                    style.photo_edge_confidence_line_width,
                    style,
                    dashed=True,
                )


def draw_photo_edge_overlay(
    rgb: np.ndarray,
    evidence_set: tuple[PhotoEdgePairEvidence, ...],
    shared_short_axes: tuple[SharedShortAxisPlan, ...],
    layout: str,
    work_long_axis_px: int,
    scale: float,
    style: DebugStyleParameters,
    *,
    include_search_corridors: bool,
) -> None:
    for evidence in evidence_set:
        if include_search_corridors:
            _draw_search_corridors(rgb, evidence, layout, scale, style)
        _draw_pair_evidence(rgb, evidence, layout, scale, style)
    _draw_shared_short_axes(
        rgb,
        shared_short_axes,
        work_long_axis_px,
        layout,
        scale,
        style,
    )


def make_source_photo_edge_debug_rgb(
    workspace: DetectionWorkspace,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = cached_preview_gray(
        render_cache,
        "source_gray",
        workspace.source_gray,
        style.preview_max_side,
    )
    draw_photo_edge_overlay(
        rgb,
        workspace.source_photo_edge_pairs,
        (),
        workspace.measurement_cache.layout,
        workspace.scan_canvas_evidence.observed_long_axis_px,
        scale,
        style,
        include_search_corridors=True,
    )
    return rgb


def _photo_edge_summary(workspace: DetectionWorkspace) -> str:
    canvas = workspace.scan_canvas_evidence
    profile = (
        canvas.outcome.value
        if canvas.selected_profile is None
        else canvas.selected_profile.profile_id
    )
    states = ",".join(
        evidence.state.value for evidence in workspace.source_photo_edge_pairs
    )
    facts = ",".join(
        fact.value
        for evidence in workspace.source_photo_edge_pairs
        for fact in evidence.facts
    )
    retained_fragment_count = sum(
        len(evidence.fragment_summaries)
        for evidence in workspace.source_photo_edge_pairs
    )
    total_fragment_count = sum(
        evidence.measurement_summary.fragment_count
        for evidence in workspace.source_photo_edge_pairs
    )
    observation_count = sum(
        evidence.measurement_summary.canonical_observation_count
        for evidence in workspace.source_photo_edge_pairs
    )
    valid_pair_count = sum(
        hypothesis.state == EvidenceState.SUPPORTED
        for evidence in workspace.source_photo_edge_pairs
        for hypothesis in evidence.hypotheses
    )
    censored_count = sum(
        evidence.measurement_summary.censored_component_count
        for evidence in workspace.source_photo_edge_pairs
    )
    suffix = f" | facts={facts}" if facts else ""
    return (
        f"Source photo edges | canvas={profile}"
        f" | pair={states or 'none'}"
        f" | retained_fragments={retained_fragment_count}/"
        f"{total_fragment_count}"
        f" | canonical_observations={observation_count}"
        f" | censored={censored_count}"
        f" | valid_pairs={valid_pair_count}{suffix}"
    )


def _mapped_photo_edge_summary(workspace: DetectionWorkspace) -> str:
    shared = ",".join(plan.outcome.value for plan in workspace.shared_short_axes)
    return (
        "Mapped photo edges + shared short axis"
        f" | transform={workspace.transform_geometry.outcome.value}"
        f" | shared={shared or 'none'}"
    )


@dataclass(frozen=True)
class DebugGeometry:
    frame_slot_boxes: tuple[Box, ...]
    sequence_inferred_slot_boxes: tuple[Box, ...]
    frame_crop_envelopes: tuple[FrameCropEnvelope, ...]
    final_boxes: tuple[Box, ...]
    containment_fallback: Box | None


def _map_envelopes(
    envelopes: tuple[FrameCropEnvelope, ...],
    layout: str,
    image_width: int,
    image_height: int,
) -> tuple[FrameCropEnvelope, ...]:
    return tuple(
        FrameCropEnvelope(
            item.frame_index,
            map_work_box(item.box, layout, image_width, image_height),
        )
        for item in envelopes
    )


def debug_geometry(
    gray: np.ndarray,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
) -> DebugGeometry:
    candidate_geometry = selected_candidate.geometry
    image_height, image_width = gray.shape
    if isinstance(candidate_geometry, ReviewOnlyContainment):
        return DebugGeometry(
            frame_slot_boxes=(),
            sequence_inferred_slot_boxes=(),
            frame_crop_envelopes=(),
            final_boxes=(),
            containment_fallback=map_work_box(
                candidate_geometry.holder_safety.containment_fallback.box,
                candidate_geometry.layout,
                image_width,
                image_height,
            ),
        )
    slot_boxes = tuple(
        (
            slot,
            map_work_box(
                Box(
                    int(round(slot.leading.position.midpoint)),
                    int(round(candidate_geometry.shared_short_axis.top.midpoint)),
                    int(round(slot.trailing.position.midpoint)),
                    int(round(candidate_geometry.shared_short_axis.bottom.midpoint)),
                ),
                candidate_geometry.layout,
                image_width,
                image_height,
            ),
        )
        for slot in candidate_geometry.frame_slots
    )
    frame_slot_boxes = tuple(
        box for slot, box in slot_boxes if not slot.sequence_inferred
    )
    sequence_inferred_slot_boxes = tuple(
        box for slot, box in slot_boxes if slot.sequence_inferred
    )
    final_geometry = detection.output_geometry
    if final_geometry is not None:
        return DebugGeometry(
            frame_slot_boxes=frame_slot_boxes,
            sequence_inferred_slot_boxes=sequence_inferred_slot_boxes,
            frame_crop_envelopes=final_geometry.frame_crop_envelopes,
            final_boxes=(
                final_geometry.final_boxes
                if detection.frame_export_eligible
                else ()
            ),
            containment_fallback=None,
        )
    mapped_envelopes = _map_envelopes(
        candidate_geometry.frame_crop_envelopes,
        candidate_geometry.layout,
        image_width,
        image_height,
    )
    return DebugGeometry(
        frame_slot_boxes=frame_slot_boxes,
        sequence_inferred_slot_boxes=sequence_inferred_slot_boxes,
        frame_crop_envelopes=mapped_envelopes,
        final_boxes=(),
        containment_fallback=None,
    )


def draw_evidence_context_overlay(
    rgb: np.ndarray,
    geometry: DebugGeometry,
    scale: float,
    style: DebugStyleParameters,
) -> None:
    for envelope in geometry.frame_crop_envelopes:
        draw_preview_dashed_rect(
            rgb,
            envelope.box,
            scale,
            style.frame_crop_envelope_color,
            style.frame_crop_envelope_line_width,
            dash_length=style.line_dash_length,
            dash_gap=style.line_dash_gap,
        )
    if geometry.containment_fallback is not None:
        draw_preview_rect(
            rgb,
            geometry.containment_fallback,
            scale,
            style.raw_observation_color,
            style.containment_fallback_line_width,
        )


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
    evidence = make_separator_evidence_gray(
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
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    gray = workspace.gray
    separator_overlay = diagnostics.separator_overlay
    style = diagnostics.style
    source_photo_edges = add_panel_label(
        make_source_photo_edge_debug_rgb(
            workspace,
            style,
            render_cache,
        ),
        _photo_edge_summary(workspace),
        height=style.label_height,
        origin=style.label_origin,
        background=style.dark_background,
        text_color=style.text_color,
    )
    debug_boxes = add_panel_label(
        make_debug_preview_rgb(
            workspace,
            detection,
            selected_candidate,
            style,
            render_cache,
        ),
        _mapped_photo_edge_summary(workspace)
        + (
            " | frame slots"
            if detection.frame_export_eligible
            else " | provisional frames - NOT EXPORTABLE"
        ),
        height=style.label_height,
        origin=style.label_origin,
        background=style.dark_background,
        text_color=style.text_color,
    )
    separator_evidence = add_panel_label_with_legend(
        make_separator_evidence_debug_rgb(
            gray,
            detection,
            selected_candidate,
            separator_overlay,
            diagnostics.separator_evidence_image,
            style,
            render_cache,
        ),
        "Boundary and separator evidence",
        diagnostics.legend_entries,
        label_height=style.label_height,
        label_origin=style.label_origin,
        legend_row_height=style.legend_row_height,
        legend_sample_width=style.legend_sample_width,
        legend_text_gap=style.legend_text_gap,
        background=style.dark_background,
        text_color=style.text_color,
        line_width=separator_overlay.observed_line_width,
        dash_length=style.line_dash_length,
        dash_gap=style.line_dash_gap,
    )
    canvas = stack_debug_panels(
        source_photo_edges,
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
    source_photo_edges: np.ndarray,
    debug_boxes: np.ndarray,
    separator_evidence: np.ndarray,
    *,
    horizontal: bool,
    style: DebugStyleParameters,
) -> np.ndarray:
    panels = (source_photo_edges, debug_boxes, separator_evidence)
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
