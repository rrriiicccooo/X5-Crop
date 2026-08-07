from __future__ import annotations

from typing import Any

from ..detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from ..detection.decision.vocabulary import FINAL_REVIEW_REASONS
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    core_facts_sha256,
)


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
    "runtime_identity",
    "core_facts_sha256",
)

def _validate_gate(record: dict[str, Any], stage: str) -> None:
    checks = record.get("checks")
    check_keys = {
        "code",
        "stage",
        "state",
        "gap",
        "final_review_reason",
        "blocks",
    }
    if (
        not isinstance(checks, list)
        or tuple(item.get("code") for item in checks)
        != CANDIDATE_GATE_CHECK_CODES
        or any(item.get("stage") != stage for item in checks)
        or any(set(item) != check_keys for item in checks)
    ):
        raise ValueError(f"{stage} Gate is incomplete or out of order")
    for item in checks:
        supported = item.get("state") == "supported"
        if (
            supported != (item.get("gap") is None)
            or bool(item.get("blocks")) != (not supported)
            or (
                stage == "candidate"
                and item.get("final_review_reason") is not None
            )
            or (
                stage == "decision"
                and supported
                != (item.get("final_review_reason") is None)
            )
        ):
            raise ValueError(f"{stage} Gate typed gap is inconsistent")


def _validate_measurement(record: dict[str, Any]) -> None:
    field = record["measurement"]["field"]
    if (
        field.get("owner") != "PhotoBoundaryMeasurementField"
        or not field.get("streaming_transition_records_only")
    ):
        raise ValueError("measurement field owner is not current")
    for measurement_set in record["measurement"]["queries"]:
        coverage = measurement_set["coverage"]
        complete = bool(coverage["complete"])
        if complete != (
            coverage["registered_trace_count"]
            == coverage["completed_trace_count"]
            and coverage["registered_coordinate_count"]
            == coverage["completed_coordinate_count"]
        ):
            raise ValueError("query coverage receipt is inconsistent")
        if measurement_set["state"] == "supported":
            if not complete:
                raise ValueError("supported query lacks complete coverage")
        elif measurement_set["transition_count"]:
            raise ValueError("incomplete query exposed transitions")
        transitions = measurement_set.get("transitions")
        if (
            not isinstance(transitions, list)
            or len(transitions) != measurement_set["transition_count"]
            or any(
                not isinstance(item.get("coordinate_interval_px"), dict)
                or item.get("polarity") not in {-1, 0, 1}
                or not isinstance(item.get("provenance"), dict)
                for item in transitions
            )
        ):
            raise ValueError("transition safety facts are incomplete")


def _validate_finalization(record: dict[str, Any]) -> None:
    status = record["decision"]["status"]
    finalization = record["output"]["finalization"]
    resolved = finalization["resolved_output_slots"]
    count = finalization["output_slot_count"]
    identities = finalization["slot_identities"]
    geometries = finalization["resolved_output_geometries"]
    authorities = finalization["sampling_authority_boxes"]
    boxes = finalization["final_boxes"]
    output_files = record["output"]["output_files"]
    fidelity = record["output"]["tiff_fidelity"]
    if fidelity.get("source_sample_count_per_roi") != 1:
        raise ValueError("TIFF output must use one source sample per ROI")
    if resolved is None:
        if count is not None or identities:
            raise ValueError("unresolved slots cannot claim identities")
    elif (
        count != sum(resolved["lane_output_slot_counts"])
        or len(identities) != count
    ):
        raise ValueError("resolved output-slot identity is inconsistent")
    if status == "approved_auto":
        if (
            not finalization["frame_export_eligible"]
            or not isinstance(count, int)
            or count <= 0
            or len(geometries) != count
            or len(authorities) != count
            or len(boxes) != count
        ):
            raise ValueError("approved output lacks complete geometry")
        if (
            not finalization["frame_export_requested"]
            or not finalization["frame_export_performed"]
            or not finalization["official_tiff_expected"]
            or finalization["official_tiff_count"] != count
            or len(output_files) != count
            or not fidelity["write_readback_validated"]
            or fidelity["success_receipt"] != "validated"
        ):
            raise ValueError("approved output lacks validated TIFFs")
    elif (
        status != "needs_review"
        or finalization["frame_export_eligible"]
        or not finalization["frame_export_requested"]
        or finalization["frame_export_performed"]
        or finalization["official_tiff_expected"]
        or finalization["official_tiff_count"] != 0
        or geometries
        or authorities
        or boxes
        or output_files
        or fidelity["write_readback_validated"]
        or fidelity["success_receipt"] != "not_created"
    ):
        raise ValueError("review output exposed official geometry")
    if finalization["post_decision_mutation"]:
        raise ValueError("post-DecisionGate mutation is forbidden")


def validate_current_report_record(record: dict[str, Any]) -> None:
    if tuple(record) != CURRENT_REPORT_SECTIONS:
        raise ValueError("current report sections are incomplete or out of order")
    if (
        record["schema_id"] != REPORT_SCHEMA_ID
        or record["schema_revision"] != REPORT_SCHEMA_REVISION
        or record["configuration"]["execution"]["detector_kind"]
        != "v5_template_first_format_placement"
    ):
        raise ValueError("report does not use the current-only schema")
    _validate_measurement(record)
    expected_partition = {
        "pixel_observation": (
            "direction_free_side_regions_and_raw_top_bottom_lines"
        ),
        "format_physical": (
            "frame_dimensions_tolerance_gap_component_count_fit"
        ),
        "canonical": "representative_only_no_safety_pruning",
        "safety": "union_of_retained_complete_format_placements",
        "search": "measurement_coverage_only",
    }
    geometry = record["photo_geometry"]
    if geometry["authority_partition"] != expected_partition:
        raise ValueError("format-placement authority partition is invalid")
    for lane in geometry["lanes"]:
        if lane["search"]["authority"] != "measurement_coverage_only":
            raise ValueError("search proposal gained placement authority")
        placement = lane["placement"]
        if (
            placement["authority"]
            != "template_group_pixel_evidence"
            or placement["safety_union_rule"]
            != "all_retained_complete_placements"
        ):
            raise ValueError("placement safety authority is invalid")
        retained = placement["retained_placements"]
        canonical_id = placement["canonical_placement_id"]
        if bool(retained) != (canonical_id is not None) or (
            retained
            and canonical_id
            not in {item["placement_id"] for item in retained}
        ):
            raise ValueError("canonical placement is outside the retained set")
        outputs = placement["safe_crop_envelopes"]
        budgets = placement["direct_use_budget_assessments"]
        if {item["geometry_id"] for item in outputs} != {
            item["geometry_id"] for item in budgets
        }:
            raise ValueError("budget does not cover every retained output")
        for item in outputs:
            if (
                item.get("provenance")
                != "continuous_format_placement_safety_footprint"
                or item.get("mapped_output_box") is None
                or len(item.get("placement_source_footprint", ())) < 3
                or len(item.get("required_source_footprint", ())) < 3
                or len(item.get("constrained_source_footprint", ())) < 3
            ):
                raise ValueError("continuous placement output is incomplete")
    _validate_gate(record["candidate_gate"], "candidate")
    decision = record["decision"]
    _validate_gate(decision["gate"], "decision")
    status = decision.get("status")
    reasons = tuple(decision.get("final_review_reasons", ()))
    if (
        status not in {"approved_auto", "needs_review"}
        or any(reason not in FINAL_REVIEW_REASONS for reason in reasons)
        or (status == "approved_auto") != (not reasons)
    ):
        raise ValueError("DecisionGate status/reasons are inconsistent")
    _validate_finalization(record)
    finalization = record["output"]["finalization"]
    runtime_identity = record["runtime_identity"]
    source_identity = runtime_identity.get("source", {})
    if (
        "content_sha256" in source_identity
        or "implementation_fingerprint" in runtime_identity
        or not isinstance(source_identity.get("input_ordinal"), int)
        or source_identity.get("input_ordinal", 0) <= 0
        or not isinstance(source_identity.get("orientation"), dict)
    ):
        raise ValueError("runtime identity is not lightweight V5")
    output_identity = runtime_identity["output_identity"]
    if (
        geometry["resolved_output_slots"]
        != finalization["resolved_output_slots"]
        or geometry["output_slot_count"] != finalization["output_slot_count"]
        or geometry["slot_identities"] != finalization["slot_identities"]
        or output_identity["resolved_output_slots"]
        != finalization["resolved_output_slots"]
        or output_identity["output_slot_count"]
        != finalization["output_slot_count"]
        or output_identity["slot_identities"]
        != finalization["slot_identities"]
    ):
        raise ValueError("output identities disagree")
    if record["core_facts_sha256"] != core_facts_sha256(record):
        raise ValueError("core facts hash does not match the record")
