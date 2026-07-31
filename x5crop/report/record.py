from __future__ import annotations

from hashlib import sha256
import json

from ..app_info import VERSION
from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from ..detection.workspace import DetectionWorkspace
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    bind_core_facts,
)
from .read_models import gate_read_model, typed_read_model


def _transition_digest(measurement_set: object) -> str:
    digest = sha256()
    digest.update(b"x5crop-transition-jsonl-v1\n")
    for item in measurement_set.transitions:
        payload = (
            str(item.transition_id),
            item.trace_ordinal,
            item.trace_coordinate_px,
            item.coordinate_interval_px.minimum,
            item.coordinate_interval_px.maximum,
            item.gradient_z,
            item.tone_z,
            item.texture_z,
            item.polarity,
        )
        digest.update(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _content_row_run_digest(content: object) -> str:
    digest = sha256()
    digest.update(b"x5crop-content-row-runs-int32le-v1\n")
    table = content.row_run_table
    for name, array in (
        ("rows", table.rows),
        ("lefts", table.lefts),
        ("rights", table.rights),
        ("component_indices", table.component_indices),
    ):
        canonical = array.astype("<i4", copy=False)
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(canonical.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(memoryview(canonical).cast("B"))
        digest.update(b"\n")
    return digest.hexdigest()


def _measurement_set_read_model(measurement_set: object) -> dict[str, object]:
    return {
        "query": typed_read_model(measurement_set.query),
        "state": measurement_set.state.value,
        "coverage": typed_read_model(measurement_set.coverage),
        "transition_count": len(measurement_set.transitions),
        "transition_digest": _transition_digest(measurement_set),
        "transition_digest_algorithm": "sha256_transition_jsonl_v1",
    }


def _source_lane_read_model(lane: object) -> dict[str, object]:
    content = lane.content
    return {
        "domain": typed_read_model(lane.domain),
        "scan_canvas": typed_read_model(lane.scan_canvas),
        "axis_scale_intervals": typed_read_model(lane.axis_scale_intervals),
        "axis_scale_authority": "ScanCanvasEvidence",
        "content": {
            "state": content.state.value,
            "intensity_threshold": content.intensity_threshold,
            "texture_threshold": content.texture_threshold,
            "statistics": typed_read_model(content.statistics),
            "component_count": len(content.components),
            "row_run_count": content.row_run_table.run_count,
            "row_run_digest": _content_row_run_digest(content),
            "row_run_digest_algorithm": (
                "sha256_content_row_runs_int32le_v1"
            ),
            "component_geometry_derivation": (
                "canonical_from_row_runs_lane_domain_and_content_config"
            ),
            "authority": "ownership_and_containment_only",
        },
    }


def _sequence_competition_read_model(lane: object) -> dict[str, object]:
    candidates = lane.undominated_sequence_candidates
    pairwise_differences: list[dict[str, object]] = []
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            left_boxes = tuple(
                item.source_protected_box
                for item in left.output_geometries
            )
            right_boxes = tuple(
                item.source_protected_box
                for item in right.output_geometries
            )
            first_different_ordinal = None
            maximum_source_edge_difference_px = 0.0
            for ordinal, (left_box, right_box) in enumerate(
                zip(left_boxes, right_boxes),
                1,
            ):
                edge_difference = max(
                    abs(left_value - right_value)
                    for left_value, right_value in zip(
                        (
                            left_box.left,
                            left_box.top,
                            left_box.right,
                            left_box.bottom,
                        ),
                        (
                            right_box.left,
                            right_box.top,
                            right_box.right,
                            right_box.bottom,
                        ),
                        strict=True,
                    )
                )
                maximum_source_edge_difference_px = max(
                    maximum_source_edge_difference_px,
                    edge_difference,
                )
                if (
                    first_different_ordinal is None
                    and edge_difference > 1.0
                ):
                    first_different_ordinal = ordinal
            if len(left_boxes) != len(right_boxes):
                first_different_ordinal = min(
                    len(left_boxes),
                    len(right_boxes),
                ) + 1
            pairwise_differences.append(
                {
                    "left_candidate_id": left.candidate_id,
                    "right_candidate_id": right.candidate_id,
                    "left_output_count": len(left_boxes),
                    "right_output_count": len(right_boxes),
                    "first_non_equivalent_ordinal": (
                        first_different_ordinal
                    ),
                    "maximum_source_edge_difference_px": (
                        maximum_source_edge_difference_px
                    ),
                }
            )
    gate_codes: list[str] = []
    if any("known_content" in code for code in lane.unresolved_codes):
        gate_codes.append("known_content_containment")
    if any(
        token in code
        for code in lane.unresolved_codes
        for token in (
            "sequence",
            "ordinal",
            "complete_sequence_state_count",
        )
    ):
        gate_codes.append("slot_ordinal_assignment")
    return {
        "candidate_ids": [
            item.candidate_id for item in candidates
        ],
        "output_equivalence_class_ids": [
            item.output_equivalence_class_id
            for item in candidates
        ],
        "non_equivalent_competition": len(candidates) > 1,
        "candidate_gate_codes": list(dict.fromkeys(gate_codes)),
        "pairwise_output_differences": pairwise_differences,
    }


def _lane_geometry_read_model(lane: object) -> dict[str, object]:
    return {
        "lane_id": lane.lane_id,
        "search_proposals": {
            "authority": "query_domain_and_execution_order_only",
            "anchor_domain": typed_read_model(lane.anchor_domain),
            "sequence_extent_proposals": typed_read_model(
                lane.extent_proposals
            ),
            "label_proposals": [
                {
                    "aperture_label": item.constraint.aperture_label,
                    "expected_grid_translation_px": (
                        item.expected_grid_translation_px
                    ),
                    "outer_observed_assignments": (
                        typed_read_model(item.outer_observed_assignments)
                    ),
                }
                for item in lane.label_reconstructions
            ],
        },
        "physical_constraints": {
            "authority": "feasibility_inference_and_sequence_only",
            "labels": [
                {
                    "constraint": typed_read_model(item.constraint),
                    "aperture_pixels": typed_read_model(item.aperture_pixels),
                    "gutter_px": typed_read_model(item.gutter_px),
                }
                for item in lane.label_reconstructions
            ],
            "selected_constraint_set": typed_read_model(lane.constraint_set),
        },
        "pixel_observations": {
            "authority": "photo_boundary_measurement",
            "selected_observations": typed_read_model(
                lane.selected_observations
            ),
            "raw_long_observation_count_by_label": [
                len(item.raw_long_observations)
                for item in lane.label_reconstructions
            ],
            "physical_long_observation_count_by_label": [
                len(item.physical_long_observations)
                for item in lane.label_reconstructions
            ],
        },
        "selection": {
            "selected_label": lane.selected_label,
            "sequence_choice_ranking": typed_read_model(
                lane.sequence_choice_ranking
            ),
            "selected_long_hypothesis": typed_read_model(
                lane.selected_long_hypothesis
            ),
            "solution": typed_read_model(lane.solution),
            "undominated_candidate_set": typed_read_model(
                lane.undominated_sequence_candidates
            ),
            "undominated_states_by_ordinal": typed_read_model(
                lane.all_undominated_states_by_ordinal
            ),
            "competition_assessment": (
                _sequence_competition_read_model(lane)
            ),
            "candidate_output_geometries": typed_read_model(
                lane.resolved_output_geometries
            ),
            "unresolved_codes": list(lane.unresolved_codes),
        },
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
    analysis_identity: dict,
) -> dict:
    core = detection.source_core
    candidate_geometry = detection.candidate.geometry
    diagnostics = bool(
        analysis_identity["runtime_configuration"]["diagnostics"]
    )
    export_performed = bool(output_files)
    selected_profile_id = (
        None
        if not core.lanes
        else core.lanes[0].scan_canvas.selected_profile.profile_id
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
                _source_lane_read_model(lane)
                for lane in core.lanes
            ],
            "queries": [
                _measurement_set_read_model(measurement_set)
                for lane in candidate_geometry.lane_reconstructions
                for measurement_set in lane.measurement_sets
            ],
            "scan_canvas_state": core.scan_canvas_state.value,
            "source_content_state": core.content_state.value,
            "incomplete_reasons": list(core.incomplete_reasons),
        },
        "photo_geometry": {
            "authority_partition": {
                "pixel_observation": (
                    "transition_line_support_residual_angle_uncertainty"
                ),
                "physical_constraint": (
                    "format_count_scale_aperture_tolerance_lane_adjacency"
                ),
                "search_proposal": "grid_outer_corridor_query_domain_only",
            },
            "measurement_spec": typed_read_model(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC
            ),
            "measurement_calibration_receipt_id": (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.calibration_receipt_id
            ),
            "selected_scan_canvas_profile_id": selected_profile_id,
            "resolved_output_slots": typed_read_model(
                detection.resolved_output_slots
            ),
            "output_slot_count": detection.output_slot_count,
            "slot_identities": typed_read_model(
                detection.output_slot_identities
            ),
            "lanes": [
                _lane_geometry_read_model(lane)
                for lane in candidate_geometry.lane_reconstructions
            ],
            "unresolved_codes": list(candidate_geometry.unresolved_codes),
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
                "frame_export_requested": not diagnostics,
                "frame_export_performed": export_performed,
                "official_tiff_expected": (
                    detection.frame_export_eligible and not diagnostics
                ),
                "official_tiff_count": len(output_files),
                "reason": (
                    "diagnostics_read_only"
                    if detection.frame_export_eligible and diagnostics
                    else detection.frame_export_reason
                ),
                "resolved_output_slots": typed_read_model(
                    detection.resolved_output_slots
                ),
                "output_slot_count": detection.output_slot_count,
                "slot_identities": typed_read_model(
                    detection.output_slot_identities
                ),
                "transform_assessment": typed_read_model(
                    detection.transform_assessment
                ),
                "resolved_output_geometries": typed_read_model(
                    detection.resolved_output_geometries
                ),
                "source_sampling_boxes": typed_read_model(
                    detection.source_sampling_boxes
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
                    "lossless_compression_none_or_lzw",
                ],
                "success_receipt": (
                    "validated"
                    if export_performed
                    else "not_requested_diagnostics"
                    if detection.frame_export_eligible and diagnostics
                    else "not_created"
                ),
            },
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
        "analysis_identity": dict(analysis_identity),
    }
    return bind_core_facts(record)
