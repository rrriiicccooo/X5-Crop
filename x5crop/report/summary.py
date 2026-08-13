"""Compact production report facts for one completed local crop."""

from __future__ import annotations

from typing import Any

from .chain_records import selected_chain_summary
from .read_models import typed_read_model


AUTHORITY_PARTITION = {
    "pixel_observation": "direction_free_candidate_independent_measurement",
    "format_physical": "fixed_frame_dimensions_shared_scale_gap_count",
    "selection": "componentwise_sequence_cross_shared_dominance",
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
            "selected_combination_id": selection.selected_combination_id,
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
                "selected_placement_id": (
                    None
                    if lane.selected_placement is None
                    else lane.selected_placement.placement_id
                ),
                "selected_chain": (
                    None
                    if lane.selected_chain_record is None
                    else selected_chain_summary(lane.selected_chain_record)
                ),
                "safe_crop_envelopes": typed_read_model(lane.safe_crop_envelopes),
                "direct_use_budget_assessments": typed_read_model(
                    lane.direct_use_budget_assessments
                ),
            }
            for lane in geometry.lane_reconstructions
        ],
    }
