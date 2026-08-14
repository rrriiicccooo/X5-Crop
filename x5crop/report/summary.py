"""Compact production report facts for one completed local crop."""

from __future__ import annotations

from typing import Any

from .read_models import typed_read_model


AUTHORITY_PARTITION = {
    "pixel_observation": "direction_free_candidate_independent_measurement",
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
                "selected_placement_id": (
                    None
                    if lane.selected_placement is None
                    else lane.selected_placement.placement_id
                ),
                "runner_up_placement_id": (
                    lane.placement_competition.runner_up_placement_id
                ),
                "safe_crop_envelopes": typed_read_model(lane.safe_crop_envelopes),
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
