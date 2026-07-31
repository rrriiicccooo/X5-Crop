from __future__ import annotations

from typing import Any

from ..detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from ..detection.decision.vocabulary import FINAL_REVIEW_REASONS
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    core_facts_sha256,
)

_SHA256_HEX_LENGTH = 64


CURRENT_REPORT_SECTIONS = (
    "schema_id",
    "schema_revision",
    "script_version",
    "source",
    "input",
    "configuration",
    "measurement",
    "photo_geometry",
    "candidate_gate",
    "decision",
    "output",
    "analysis_identity",
    "core_facts_sha256",
)


def _validate_gate(record: dict[str, Any], stage: str) -> None:
    checks = record.get("checks")
    if (
        not isinstance(checks, list)
        or tuple(item.get("code") for item in checks)
        != CANDIDATE_GATE_CHECK_CODES
        or any(item.get("stage") != stage for item in checks)
    ):
        raise ValueError(f"{stage} Gate is incomplete or out of order")


def _validate_measurement(record: dict[str, Any]) -> None:
    field = record["measurement"]["field"]
    if (
        field.get("owner") != "PhotoBoundaryMeasurementField"
        or not field.get("streaming_transition_records_only")
    ):
        raise ValueError("measurement field owner is not current")
    for lane in record["measurement"]["source_lanes"]:
        content = lane["content"]
        statistics = content["statistics"]
        if (
            "components" in content
            or content.get("authority")
            != "ownership_and_containment_only"
            or content.get("component_count")
            != statistics.get("component_count")
            or content.get("row_run_count")
            != statistics.get("run_count")
            or content.get("component_geometry_derivation")
            != "canonical_from_row_runs_lane_domain_and_content_config"
            or content.get("row_run_digest_algorithm")
            != "sha256_content_row_runs_int32le_v1"
            or not _is_sha256(content.get("row_run_digest"))
        ):
            raise ValueError("source content summary is inconsistent")
    for measurement_set in record["measurement"]["queries"]:
        coverage = measurement_set["coverage"]
        complete = bool(coverage["complete"])
        state = measurement_set["state"]
        transition_count = measurement_set["transition_count"]
        if complete != (
            coverage["registered_trace_count"]
            == coverage["completed_trace_count"]
            and coverage["registered_coordinate_count"]
            == coverage["completed_coordinate_count"]
        ):
            raise ValueError("query coverage receipt is inconsistent")
        if state == "supported":
            if not complete:
                raise ValueError("supported query lacks complete coverage")
        elif transition_count:
            raise ValueError("incomplete query exposed partial transitions")
        if (
            "transitions" in measurement_set
            or not isinstance(transition_count, int)
            or transition_count < 0
            or measurement_set.get("transition_digest_algorithm")
            != "sha256_transition_jsonl_v1"
            or not _is_sha256(measurement_set.get("transition_digest"))
        ):
            raise ValueError("transition summary is inconsistent")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_current_report_record(record: dict[str, Any]) -> None:
    if tuple(record) != CURRENT_REPORT_SECTIONS:
        raise ValueError("current report sections are incomplete or out of order")
    if (
        record["schema_id"] != REPORT_SCHEMA_ID
        or record["schema_revision"] != REPORT_SCHEMA_REVISION
        or record["configuration"]["execution"]["detector_kind"]
        != "source_coordinate_photo_geometry"
    ):
        raise ValueError("report does not use the current-only schema")
    _validate_measurement(record)
    partition = record["photo_geometry"]["authority_partition"]
    if partition != {
        "pixel_observation": (
            "transition_line_support_residual_angle_uncertainty"
        ),
        "physical_constraint": (
            "format_count_scale_aperture_tolerance_lane_adjacency"
        ),
        "search_proposal": "grid_outer_corridor_query_domain_only",
    }:
        raise ValueError("photo geometry authority partition is invalid")

    _validate_gate(record["candidate_gate"], "candidate")
    decision = record["decision"]
    _validate_gate(decision["gate"], "decision")
    status = decision.get("status")
    if status not in {"approved_auto", "needs_review"}:
        raise ValueError("decision status is not current")
    reasons = tuple(decision.get("final_review_reasons", ()))
    if any(reason not in FINAL_REVIEW_REASONS for reason in reasons):
        raise ValueError("decision reasons are not current typed reasons")
    if (status == "approved_auto") != (not reasons):
        raise ValueError("approved/review status and final reasons disagree")

    finalization = record["output"]["finalization"]
    resolved = finalization["resolved_output_slots"]
    output_slot_count = finalization["output_slot_count"]
    slot_identities = finalization["slot_identities"]
    geometries = finalization["resolved_output_geometries"]
    source_boxes = finalization["source_sampling_boxes"]
    final_boxes = finalization["final_boxes"]
    output_files = record["output"]["output_files"]
    diagnostics = bool(
        record["analysis_identity"]["runtime_configuration"]["diagnostics"]
    )
    if resolved is None:
        if output_slot_count is not None or slot_identities:
            raise ValueError(
                "unresolved output slots cannot claim count or identities"
            )
    else:
        lane_counts = resolved.get("lane_output_slot_counts")
        if (
            not isinstance(lane_counts, list)
            or not lane_counts
            or any(
                not isinstance(value, int) or value <= 0
                for value in lane_counts
            )
            or output_slot_count != sum(lane_counts)
            or len(slot_identities) != output_slot_count
        ):
            raise ValueError("resolved output slot identity is inconsistent")
    if status == "approved_auto":
        if (
            not finalization["frame_export_eligible"]
            or not isinstance(output_slot_count, int)
            or output_slot_count <= 0
            or len(geometries) != output_slot_count
            or len(source_boxes) != output_slot_count
            or len(final_boxes) != output_slot_count
        ):
            raise ValueError(
                "approved output requires one resolved geometry per slot"
            )
        if diagnostics:
            if (
                finalization["frame_export_requested"]
                or finalization["frame_export_performed"]
                or finalization["official_tiff_expected"]
                or finalization["official_tiff_count"] != 0
                or output_files
                or record["output"]["tiff_fidelity"]["success_receipt"]
                != "not_requested_diagnostics"
            ):
                raise ValueError("diagnostics cannot claim official TIFF output")
        elif (
            not finalization["frame_export_requested"]
            or not finalization["frame_export_performed"]
            or not finalization["official_tiff_expected"]
            or finalization["official_tiff_count"] != output_slot_count
            or len(output_files) != output_slot_count
            or record["output"]["tiff_fidelity"]["success_receipt"]
            != "validated"
            or not record["output"]["tiff_fidelity"][
                "write_readback_validated"
            ]
        ):
            raise ValueError(
                "approved output must contain validated TIFFs for all slots"
            )
    elif (
        finalization["frame_export_eligible"]
        or finalization["frame_export_performed"]
        or finalization["official_tiff_expected"]
        or finalization["official_tiff_count"] != 0
        or geometries
        or source_boxes
        or final_boxes
        or output_files
        or record["output"]["tiff_fidelity"]["success_receipt"]
        != "not_created"
    ):
        raise ValueError("review output cannot expose official output geometry")
    if finalization["post_decision_mutation"]:
        raise ValueError("post-DecisionGate output mutation is forbidden")

    geometry = record["photo_geometry"]
    for lane in geometry["lanes"]:
        search = lane["search_proposals"]
        if (
            search["authority"]
            != "query_domain_and_execution_order_only"
            or any(
                proposal.get("query_domain_only") is not True
                for proposal in search["sequence_extent_proposals"]
            )
        ):
            raise ValueError("search proposal gained geometry authority")
        selection = lane["selection"]
        solution = selection["solution"]
        if solution is not None:
            state_rows = solution["undominated_states_by_ordinal"]
            if any(len(states) > 3 for states in state_rows):
                raise ValueError("complete FrameGeometryState K exceeds three")
        candidates = selection["undominated_candidate_set"]
        competition = selection["competition_assessment"]
        candidate_ids = [
            candidate["candidate_id"] for candidate in candidates
        ]
        if (
            competition["candidate_ids"] != candidate_ids
            or len(set(candidate_ids)) != len(candidate_ids)
            or competition["non_equivalent_competition"]
            != (len(candidates) > 1)
            or any(
                pair["left_candidate_id"] not in candidate_ids
                or pair["right_candidate_id"] not in candidate_ids
                or pair["left_candidate_id"]
                == pair["right_candidate_id"]
                for pair in competition[
                    "pairwise_output_differences"
                ]
            )
        ):
            raise ValueError(
                "sequence competition receipt is inconsistent"
            )
        exceeds_two = any(
            "complete_sequence_state_count_exceeds_two" in code
            for code in selection["unresolved_codes"]
        )
        if exceeds_two != (len(candidates) > 2):
            raise ValueError(
                "complete sequence candidate limit receipt is inconsistent"
            )
        if status == "approved_auto" and len(candidates) > 1:
            raise ValueError(
                "approved output retained non-equivalent sequence candidates"
            )
    transform = finalization["transform_assessment"]
    transform_authority = transform.get("authority")
    blank_outputs = bool(geometries) and all(
        item.get("provenance") == "grid_inferred_blank"
        for item in geometries
    )
    if transform_authority == "grid_blank_no_photo_geometry":
        if (
            transform.get("outcome") != "identity"
            or not blank_outputs
            or any(
                state.get("photo_geometry") is not None
                for lane in geometry["lanes"]
                for state in (
                    []
                    if lane["selection"]["solution"] is None
                    else lane["selection"]["solution"]["selected_states"]
                )
            )
        ):
            raise ValueError("blank Grid identity transform is not isolated")
    elif status == "approved_auto" and transform_authority != (
        "observed_photo_lines"
    ):
        raise ValueError("photo output lacks observed transform authority")
    for item in geometries:
        provenance = item.get("provenance")
        if provenance == "grid_inferred_blank":
            if item["grid_translation"]["outcome"] == "unresolved":
                raise ValueError("blank output has unresolved Grid translation")
        elif (
            provenance != "photo_geometry_uncertainty_protection"
            or item.get("interpolation_allowance_source_px") != 1.0
            or float(item.get("long_axis_protection_mm", 0.0)) <= 0.0
            or float(item.get("short_axis_protection_mm", 0.0)) <= 0.0
        ):
            raise ValueError("photo envelope cannot be exactly recalculated")
    output_identity = record["analysis_identity"]["output_identity"]
    if (
        geometry["resolved_output_slots"] != resolved
        or geometry["output_slot_count"] != output_slot_count
        or geometry["slot_identities"] != slot_identities
        or output_identity["resolved_output_slots"] != resolved
        or output_identity["output_slot_count"] != output_slot_count
        or output_identity["slot_identities"] != slot_identities
        or geometry["selected_scan_canvas_profile_id"]
        != output_identity["selected_scan_canvas_profile_id"]
    ):
        raise ValueError("output identities disagree")
    if record["core_facts_sha256"] != core_facts_sha256(record):
        raise ValueError("core facts hash does not match the record")
