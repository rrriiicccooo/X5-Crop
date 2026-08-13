"""Read-only report/runtime facts consumed by Debug Analysis panels."""

from __future__ import annotations

from PIL import Image

from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.chains import FixedFormatFrame
from ..detection.photo_geometry.output_model import SafeCropEnvelope
from ..detection.workspace import DetectionWorkspace
from .canvas import DebugRenderCache, cached_source_image
from .panel_layout import Projection


def geometry_by_identity(
    detection: FinalDetection,
) -> tuple[tuple[int, FixedFormatFrame], ...]:
    global_ordinals = {
        (item.lane_id, item.lane_ordinal): item.global_output_ordinal
        for item in detection.output_slot_identities
    }
    values: list[tuple[int, FixedFormatFrame]] = []
    for lane in detection.candidate.geometry.lane_reconstructions:
        placements = (
            (lane.selected_placement,)
            if lane.selected_placement is not None
            else lane.materialized_chains
        )
        for placement in placements:
            for geometry in placement.fixed_frames.frames:
                ordinal = global_ordinals.get(
                    (geometry.lane_id, geometry.lane_ordinal)
                )
                if ordinal is not None:
                    values.append((ordinal, geometry))
    return tuple(
        sorted(
            values,
            key=lambda item: (item[0], item[1].placement_geometry_id),
        )
    )


def safe_crop_envelopes(
    detection: FinalDetection,
) -> tuple[SafeCropEnvelope, ...]:
    return detection.candidate.geometry.safe_crop_envelopes


def selection_summary(detection: FinalDetection) -> str:
    lanes = detection.candidate.geometry.lane_reconstructions
    chains = sum(len(item.materialized_chains) for item in lanes)
    clusters = sum(len(item.placement_selection.clusters) for item in lanes)
    vetoes = sum(
        len(assessment.facts)
        for lane in lanes
        for assessment in lane.placement_selection.content_veto_assessments
    )
    selected = sum(item.selected_placement is not None for item in lanes)
    bounded = any(item.producer_bounds.bound_exceeded for item in lanes)
    return (
        f"CHAINS {chains} · CLUSTERS {clusters} · SELECTED {selected} · "
        f"VETO {vetoes} · BOUND {'EXCEEDED' if bounded else 'OK'}"
    )


def axis_authority_summaries(
    detection: FinalDetection,
) -> tuple[str, str, str]:
    selection = detection.candidate.geometry.source_placement_selection
    selected = next(
        (
            item
            for item in selection.combinations
            if item.combination_id == selection.selected_combination_id
        ),
        None,
    )
    if selected is None:
        unresolved = f"{len(selection.combinations)} LEGAL · NO DOMINANT"
        return (
            f"CROSS AUTHORITY · {unresolved}",
            f"SEQUENCE AUTHORITY · {unresolved}",
            f"SHARED AUTHORITY · {unresolved}",
        )
    sequence = selected.sequence_authority
    cross = selected.cross_authority
    shared = selected.shared_authority
    return (
        (
            "CROSS AUTHORITY · "
            f"FRAME {cross.fixed_height_placement_authorized_count} · "
            f"PAIR {cross.complete_top_bottom_pair_count} · "
            f"H-SPAN {cross.direct_height_span_validated_count} · "
            f"REGION {cross.independent_support_region_count}"
        ),
        (
            "SEQUENCE AUTHORITY · "
            f"CHAIN {sequence.complete_direct_chain_count} · "
            f"BAND {sequence.direct_separator_band_count} · "
            f"OUTER {sequence.direct_outer_boundary_count} · "
            f"NORMAL {sequence.normal_completion_authorized_count} · "
            f"FILL {sequence.filled_holder_centering_authorized_count}"
        ),
        (
            "SHARED AUTHORITY · "
            f"SCALE {int(shared.source_scale_compatible)} · "
            f"DIR {shared.direction_bound_lane_count} · "
            f"LANE {shared.source_lane_authority_bound_count} · "
            f"CONTENT {shared.content_veto_passed_lane_count}"
        ),
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
