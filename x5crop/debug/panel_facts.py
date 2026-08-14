"""Read-only report/runtime facts consumed by Debug Analysis panels."""

from __future__ import annotations

from PIL import Image

from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.output_model import SafeCropEnvelope
from ..detection.photo_geometry.template_placement import TemplateFrame
from ..detection.workspace import DetectionWorkspace
from .canvas import DebugRenderCache, cached_source_image
from .panel_layout import Projection


def geometry_by_identity(
    detection: FinalDetection,
) -> tuple[tuple[int, TemplateFrame], ...]:
    global_ordinals = {
        (item.lane_id, item.lane_ordinal): item.global_output_ordinal
        for item in detection.output_slot_identities
    }
    values: list[tuple[int, TemplateFrame]] = []
    for lane in detection.candidate.geometry.lane_reconstructions:
        placements = lane.placement_competition.placements
        for placement in placements:
            for geometry in placement.frames:
                ordinal = global_ordinals.get(
                    (placement.lane_id, geometry.lane_ordinal)
                )
                if ordinal is not None:
                    values.append((ordinal, geometry))
    return tuple(
        sorted(
            values,
            key=lambda item: (item[0], item[1].lane_ordinal),
        )
    )


def safe_crop_envelopes(
    detection: FinalDetection,
) -> tuple[SafeCropEnvelope, ...]:
    return detection.candidate.geometry.safe_crop_envelopes


def selection_summary(detection: FinalDetection) -> str:
    lanes = detection.candidate.geometry.lane_reconstructions
    placements = sum(len(item.placement_competition.placements) for item in lanes)
    phase = sum(item.prepared.phase_competition.receipt.phase_hypothesis_count for item in lanes)
    vetoes = sum(len(item.content_veto_facts) for item in lanes)
    selected = sum(item.selected_placement is not None for item in lanes)
    bounded = any(item.work.bound_exceeded for item in lanes)
    return (
        f"PHASE {phase} · PLACEMENTS {placements} · SELECTED {selected} · "
        f"VETO {vetoes} · BOUND {'EXCEEDED' if bounded else 'OK'}"
    )


def axis_authority_summaries(
    detection: FinalDetection,
) -> tuple[str, str, str]:
    selection = detection.candidate.geometry.source_placement_selection
    if selection.state.value != "supported":
        competitors = sum(
            len(item.placement_competition.placements)
            for item in detection.candidate.geometry.lane_reconstructions
        )
        failure = selection.failure
        detail = (
            "PLACEMENT UNRESOLVED"
            if failure is None
            else failure.detail.replace("_", " ").upper()
        )
        unresolved = (
            f"{competitors} PLACEMENTS · "
            f"{detail}"
        )
        return (
            f"CROSS FIT · {unresolved}",
            f"SEQUENCE FIT · {unresolved}",
            f"SOURCE FIT · {unresolved}",
        )
    lanes = detection.candidate.geometry.lane_reconstructions
    direct_sequence = sum(
        len(item.prepared.phase_competition.best.direct_observation_ids)
        for item in lanes
        if item.prepared.phase_competition.best is not None
    )
    inferred_sequence = sum(
        len(item.prepared.phase_competition.best.inferred_role_indices)
        for item in lanes
        if item.prepared.phase_competition.best is not None
    )
    direct_cross = sum(
        len(item.prepared.cross_competition.best.direct_bindings)
        for item in lanes
        if item.prepared.cross_competition.best is not None
    )
    inferred_cross = sum(
        len(item.prepared.cross_competition.best.inferred_bindings)
        for item in lanes
        if item.prepared.cross_competition.best is not None
    )
    runners = sum(
        item.placement_competition.runner_up_placement_id is not None
        for item in lanes
    )
    return (
        f"CROSS FIT · DIRECT {direct_cross} · INFERRED {inferred_cross}",
        f"SEQUENCE FIT · DIRECT {direct_sequence} · INFERRED {inferred_sequence}",
        f"SOURCE FIT · LANES {len(lanes)} · RUNNERS {runners} · GATE SUPPORTED",
    )


def source_projection(workspace: DetectionWorkspace) -> Projection:
    height, width = workspace.source_gray.shape
    return Projection(
        source_width=width,
        source_height=height,
        rotate_clockwise=workspace.layout == "vertical",
    )


def source_image(
    workspace: DetectionWorkspace,
    render_cache: DebugRenderCache,
) -> tuple[Image.Image, Projection]:
    projection = source_projection(workspace)
    return (
        cached_source_image(
            render_cache,
            workspace.source_gray,
            rotate_clockwise=projection.rotate_clockwise,
        ),
        projection,
    )
