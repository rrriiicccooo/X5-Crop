from __future__ import annotations

from ..app_info import VERSION
from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from ..detection.workspace import DetectionWorkspace
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    bind_core_facts,
)
from .read_models import gate_read_model, typed_read_model


def _measurement_set_read_model(measurement_set: object) -> dict[str, object]:
    return {
        "query": typed_read_model(measurement_set.query),
        "state": measurement_set.state.value,
        "coverage": typed_read_model(measurement_set.coverage),
        "transition_count": len(measurement_set.transitions),
        "transitions": typed_read_model(measurement_set.transitions),
    }


def _source_lane_read_model(lane: object) -> dict[str, object]:
    return {
        "domain": typed_read_model(lane.domain),
        "scan_canvas": typed_read_model(lane.scan_canvas),
        "axis_scale_intervals": typed_read_model(lane.scan_canvas.axis_scales),
        "axis_scale_authority": "ScanCanvasEvidence",
    }


def _lane_placement_read_model(lane: object) -> dict[str, object]:
    return {
        "lane_id": lane.lane_id,
        "search": {
            "authority": "bounded_measurement_coverage_only",
            "anchor_domain": typed_read_model(lane.anchor_domain),
            "sequence_profile": typed_read_model(lane.sequence_profile),
            "provisional_cross_profile": typed_read_model(
                lane.cross_profile
            ),
        },
        "observations": {
            "sequence_edges": typed_read_model(lane.sequence_edges),
            "separator_bands": typed_read_model(lane.separator_bands),
            "lane_gap_model": typed_read_model(lane.lane_gap_model),
            "side_transition_regions": typed_read_model(
                lane.side_transition_regions
            ),
            "raw_top_bottom_lines": typed_read_model(
                lane.raw_top_bottom_observations
            ),
            "cross_axis_proposals": typed_read_model(
                lane.cross_axis_proposals
            ),
            "raw_lines_are_canonical_direction": False,
        },
        "local_advance_unresolved_count": (
            lane.local_advance_unresolved_count
        ),
        "direction_classes": typed_read_model(lane.direction_classes),
        "chains": {
            "authority": "bounded_complete_chain_producer",
            "lane_complete_proposals": typed_read_model(
                lane.materialized_chains
            ),
            "proposal_ledgers": typed_read_model(
                lane.placement_selection.chains
            ),
            "producer_bounds": typed_read_model(lane.producer_bounds),
        },
        "selection": {
            "authority": "sampling_cluster_tiered_dominance",
            "clusters": typed_read_model(lane.placement_selection.clusters),
            "content_veto_assessments": typed_read_model(
                lane.placement_selection.content_veto_assessments
            ),
            "selected_cluster_id": lane.placement_selection.selected_cluster_id,
            "selected_placement_id": (
                None
                if lane.selected_placement is None
                else lane.selected_placement.placement_id
            ),
            "source_joint_selected_chain": typed_read_model(
                lane.selected_chain_record
            ),
            "safety_rule": "selected_placement_only",
            "safe_crop_envelopes": typed_read_model(
                lane.safe_crop_envelopes
            ),
            "direct_use_budget_assessments": typed_read_model(
                lane.direct_use_budget_assessments
            ),
        },
        "work": typed_read_model(lane.work),
    }


def report_record_for_final_detection(
    detection: FinalDetection,
    *,
    source: str,
    profile: dict,
    workspace: DetectionWorkspace,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    configuration: dict,
    runtime_identity: dict,
    frame_export_requested: bool,
) -> dict:
    core = detection.source_core
    candidate_geometry = detection.candidate.geometry
    export_performed = bool(output_files)
    selected_profile_id = (
        None
        if core.matched_holder is None
        else core.matched_holder.profile.profile_id
    )
    record = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": str(source),
        "input": {
            "profile": dict(profile),
            "workspace_identity": typed_read_model(workspace.identity),
        },
        "configuration": dict(configuration),
        "measurement": {
            "field": {
                "owner": "PhotoBoundaryMeasurementField",
                "source_extent": typed_read_model(
                    workspace.boundary_measurement_field.source_extent
                ),
                "layout": workspace.boundary_measurement_field.layout,
                "provenance": typed_read_model(
                    workspace.boundary_measurement_field.provenance
                ),
                "streaming_transition_records_only": True,
            },
            "source_lanes": [
                _source_lane_read_model(lane) for lane in core.lanes
            ],
            "content_occupancy": typed_read_model(
                core.content_occupancy
            ),
            "queries": [
                _measurement_set_read_model(measurement_set)
                for lane in candidate_geometry.lane_reconstructions
                for measurement_set in lane.measurement_sets
            ],
            "scan_canvas_state": core.scan_canvas_state.value,
            "incomplete_reasons": list(core.incomplete_reasons),
        },
        "photo_geometry": {
            "authority_partition": {
                "pixel_observation": (
                    "direction_free_side_regions_and_raw_top_bottom_lines"
                ),
                "format_physical": (
                    "fixed_frame_dimensions_shared_scale_gap_count"
                ),
                "canonical": "representative_only_no_safety_pruning",
                "selection": "sampling_cluster_then_tiered_direct_dominance",
                "safety": "selected_placement_uncertainty_only",
                "search": "bounded_measurement_coverage_only",
            },
            "measurement_contract_id": (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.contract_id
            ),
            "selected_scan_canvas_profile_id": selected_profile_id,
            "matched_holder": typed_read_model(core.matched_holder),
            "resolved_slot_count": typed_read_model(
                core.resolved_slot_count
            ),
            "resolved_output_slots": typed_read_model(
                detection.resolved_output_slots
            ),
            "output_slot_count": detection.output_slot_count,
            "slot_identities": typed_read_model(
                detection.output_slot_identities
            ),
            "source_placement_selection": typed_read_model(
                candidate_geometry.source_placement_selection
            ),
            "source_transform_assessment": typed_read_model(
                candidate_geometry.source_transform_assessment
            ),
            "lane_transform_assessments": typed_read_model(
                candidate_geometry.lane_transform_assessments
            ),
            "lanes": [
                _lane_placement_read_model(lane)
                for lane in candidate_geometry.lane_reconstructions
            ],
        },
        "candidate_gate": gate_read_model(detection.candidate.gate),
        "decision": {
            "status": detection.decision.status,
            "final_review_reasons": list(
                detection.decision.final_review_reasons
            ),
            "reason_inputs": typed_read_model(
                detection.decision.reason_inputs
            ),
            "gate": gate_read_model(detection.decision),
        },
        "output": {
            "finalization": {
                "frame_export_eligible": detection.frame_export_eligible,
                "frame_export_requested": frame_export_requested,
                "frame_export_performed": export_performed,
                "official_tiff_expected": (
                    detection.frame_export_eligible
                    and frame_export_requested
                ),
                "official_tiff_count": len(output_files),
                "reason": detection.frame_export_reason,
                "resolved_output_slots": typed_read_model(
                    detection.resolved_output_slots
                ),
                "output_slot_count": detection.output_slot_count,
                "slot_identities": typed_read_model(
                    detection.output_slot_identities
                ),
                "source_transform_assessment": typed_read_model(
                    detection.source_transform_assessment
                ),
                "output_transforms": typed_read_model(
                    detection.output_transforms
                ),
                "resolved_output_geometries": typed_read_model(
                    detection.resolved_output_geometries
                ),
                "sampling_authority_boxes": typed_read_model(
                    detection.sampling_authority_boxes
                ),
                "final_boxes": typed_read_model(detection.final_boxes),
                "post_decision_mutation": False,
            },
            "tiff_fidelity": {
                "source_sample_count_per_roi": 1,
                "write_readback_validated": bool(output_files),
                "preserved_properties": [
                    "dtype",
                    "axes",
                    "channels",
                    "icc_color_space",
                    "resolution",
                    "metadata",
                    "frozen_lossless_compression",
                    "orientation_baked_to_1",
                ],
                "success_receipt": (
                    "validated"
                    if export_performed
                    else "not_created"
                ),
            },
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
        "runtime_identity": dict(runtime_identity),
    }
    return bind_core_facts(record)
