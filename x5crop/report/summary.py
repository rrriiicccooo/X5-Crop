"""Compact production report facts for one completed local crop."""

from __future__ import annotations

from typing import Any

from ..detection.photo_geometry.template_alignment_diagnostic import (
    template_alignment_diagnostic,
)
from .read_models import typed_read_model


AUTHORITY_PARTITION = {
    "pixel_observation": "role_free_candidate_independent_measurement",
    "format_physical": "fixed_template_dimensions_pitch_gap_count",
    "selection": "bounded_phase_cross_shared_placement",
    "safety": "selected_placement_uncertainty_only",
}


def measurement_summary(detection: object, workspace: object) -> dict[str, Any]:
    field = workspace.boundary_measurement_field
    return {
        "owner": "PhotoBoundaryMeasurementField",
        "source_extent": typed_read_model(field.source_extent),
        "layout": field.layout,
        "scan_canvas_state": detection.source_core.scan_canvas_state.value,
        "incomplete_reasons": list(detection.source_core.incomplete_reasons),
    }


def photo_geometry_summary(detection: object) -> dict[str, Any]:
    core = detection.source_core
    geometry = detection.candidate.geometry
    selected_profile_id = (
        None if core.matched_holder is None else core.matched_holder.profile.profile_id
    )
    selection = geometry.source_placement_selection
    alignments = {
        lane.lane_id: template_alignment_diagnostic(
            lane.prepared.phase_competition,
            lane.prepared.sequence_edges,
            lane.prepared.separator_bands,
        )
        for lane in geometry.lane_reconstructions
    }
    return {
        "authority_partition": dict(AUTHORITY_PARTITION),
        "selected_scan_canvas_profile_id": selected_profile_id,
        "matched_holder": typed_read_model(core.matched_holder),
        "resolved_slot_count": typed_read_model(core.resolved_slot_count),
        "resolved_output_slots": typed_read_model(detection.resolved_output_slots),
        "output_slot_count": detection.output_slot_count,
        "slot_identities": typed_read_model(detection.output_slot_identities),
        "source_placement_selection": {
            "state": selection.state.value,
            "failure": typed_read_model(selection.failure),
            "selected_placement_ids": list(selection.selected_placement_ids),
            "runner_up_placement_ids": list(selection.runner_up_placement_ids),
        },
        "source_transform_assessment": typed_read_model(
            geometry.source_transform_assessment
        ),
        "lane_transform_assessments": typed_read_model(
            geometry.lane_transform_assessments
        ),
        "lanes": [
            {
                "lane_id": lane.lane_id,
                "template_id": lane.prepared.template_spec.template_id,
                "phase_status": lane.prepared.phase_competition.status.value,
                "cross_status": lane.prepared.cross_competition.status.value,
                "placement_state": lane.placement_competition.state.value,
                "placement_failure": typed_read_model(
                    lane.placement_competition.failure
                ),
                "template_alignment": {
                    "pattern": alignments[lane.lane_id].pattern.value,
                    "absolute_phase_px": (
                        alignments[lane.lane_id].absolute_phase_px
                    ),
                    "canonical_pitch_px": (
                        alignments[lane.lane_id].canonical_pitch_px
                    ),
                    "pitch_delta_from_compiled_center_px": (
                        alignments[lane.lane_id]
                        .pitch_delta_from_compiled_center_px
                    ),
                    "maximum_absolute_role_residual_px": (
                        alignments[lane.lane_id]
                        .maximum_absolute_role_residual_px
                    ),
                    "local_advance_relations": typed_read_model(
                        alignments[lane.lane_id].local_advance_relations
                    ),
                    "unbound_direct_observation_count": len(
                        alignments[lane.lane_id]
                        .unbound_direct_observation_ids
                    ),
                    "unresolved_reason": (
                        alignments[lane.lane_id].unresolved_reason
                    ),
                },
                "selected_cross_boundary_use": (
                    None
                    if lane.selected_placement is None
                    or lane.prepared.cross_competition.best is None
                    else lane.prepared.cross_competition.best.boundary_use.value
                ),
                "selected_placement_id": (
                    None
                    if lane.selected_placement is None
                    else lane.selected_placement.placement_id
                ),
                "runner_up_placement_id": (
                    lane.placement_competition.runner_up_placement_id
                ),
                "photo_group_outer": typed_read_model(
                    None
                    if lane.holder_fill_assessment is None
                    else lane.holder_fill_assessment.outer
                ),
                "holder_fill_assessment": typed_read_model(
                    lane.holder_fill_assessment
                ),
                "output_footprints": typed_read_model(lane.output_footprints),
                "direct_use_budget_assessments": typed_read_model(
                    lane.direct_use_budget_assessments
                ),
                "peak_temporary_bytes": max(
                    lane.prepared.measurement_work.peak_temporary_bytes,
                    lane.work.peak_temporary_bytes,
                ),
            }
            for lane in geometry.lane_reconstructions
        ],
    }
