from __future__ import annotations

from typing import Any

from ..detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from ..detection.photo_geometry.bounds import (
    MAX_BANDS_PER_CORRIDOR,
    MAX_COMPLETE_CHAINS_PER_LANE,
    MAX_LEDGER_ENTRIES_PER_CHAIN,
    MAX_LEDGER_ENTRIES_PER_LANE,
    MAX_LEDGER_ENTRIES_PER_SOURCE,
)
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
    for observation_set in record["measurement"]["content_occupancy"]:
        if (
            observation_set["long_sample_count"] > 256
            or observation_set["cross_sample_count"] > 64
            or len(observation_set["observations"]) > 64
            or any(
                set(observation)
                != {
                    "observation_id",
                    "lane_id",
                    "source_box",
                    "reliability",
                    "provenance",
                }
                for observation in observation_set["observations"]
            )
        ):
            raise ValueError("content occupancy observations are unbounded")
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
    review_copy = record["output"]["review_copy"]
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
    requested = finalization["frame_export_requested"]
    if not isinstance(requested, bool):
        raise ValueError("frame-export request must be boolean")
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
        if requested:
            if (
                not finalization["frame_export_performed"]
                or not finalization["official_tiff_expected"]
                or finalization["official_tiff_count"] != count
                or len(output_files) != count
                or review_copy is not None
                or not fidelity["write_readback_validated"]
                or fidelity["success_receipt"] != "validated"
            ):
                raise ValueError("approved output lacks validated TIFFs")
    elif status != "needs_review" or (
        finalization["frame_export_eligible"]
        or geometries
        or authorities
        or boxes
    ):
        raise ValueError("review output exposed official geometry")
    if not requested:
        if (
            finalization["frame_export_performed"]
            or finalization["official_tiff_expected"]
            or finalization["official_tiff_count"] != 0
            or output_files
            or review_copy is not None
            or fidelity["write_readback_validated"]
            or fidelity["success_receipt"] != "not_created"
        ):
            raise ValueError("analysis-only output created production artifacts")
    elif status == "needs_review" and (
        finalization["frame_export_performed"]
        or finalization["official_tiff_expected"]
        or finalization["official_tiff_count"] != 0
        or output_files
        or fidelity["write_readback_validated"]
        or fidelity["success_receipt"] != "not_created"
    ):
        raise ValueError("review output exposed official TIFFs")
    if finalization["post_decision_mutation"]:
        raise ValueError("post-DecisionGate mutation is forbidden")


def validate_current_report_record(record: dict[str, Any]) -> None:
    if tuple(record) != CURRENT_REPORT_SECTIONS:
        raise ValueError("current report sections are incomplete or out of order")
    if (
        record["schema_id"] != REPORT_SCHEMA_ID
        or record["schema_revision"] != REPORT_SCHEMA_REVISION
        or record["configuration"]["execution"]["detector_kind"]
        != "v5_bounded_physical_chain_selection"
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
        "selection": "sampling_cluster_then_tiered_direct_dominance",
        "safety": "selected_placement_uncertainty_only",
        "search": "bounded_measurement_coverage_only",
    }
    geometry = record["photo_geometry"]
    matched_holder = geometry.get("matched_holder")
    resolved_count = geometry.get("resolved_slot_count")
    if resolved_count is not None and (
        matched_holder is None
        or resolved_count["matched_holder_profile_id"]
        != matched_holder["profile"]["profile_id"]
        or resolved_count["full_count"] != matched_holder["full_count"]
        or resolved_count["output_count"] != geometry["output_slot_count"]
    ):
        raise ValueError("matched holder and resolved count disagree")
    if geometry["authority_partition"] != expected_partition:
        raise ValueError("format-placement authority partition is invalid")
    source_ledger_count = 0
    for lane in geometry["lanes"]:
        if lane["search"]["authority"] != "bounded_measurement_coverage_only":
            raise ValueError("search proposal gained placement authority")
        chains = lane["chains"]
        selection = lane["selection"]
        if (
            chains["authority"] != "bounded_complete_chain_producer"
            or selection["authority"]
            != "sampling_cluster_tiered_dominance"
            or selection["safety_rule"] != "selected_placement_only"
        ):
            raise ValueError("placement safety authority is invalid")
        materialized = chains["materialized"]
        ledger = chains["ledger"]
        bounds = chains["producer_bounds"]
        selected_id = selection["selected_placement_id"]
        if (
            len(materialized) > MAX_COMPLETE_CHAINS_PER_LANE
            or len(ledger) != len(materialized)
            or bounds["materialized_complete_chain_count"] != len(materialized)
            or bounds["proposed_complete_chain_count"] < len(materialized)
            or any(
                item["materialized_count"] > MAX_BANDS_PER_CORRIDOR
                or item["proposed_count"] < item["materialized_count"]
                for item in bounds["corridor_bands"]
            )
            or any(
                len(item["ledger"]) > MAX_LEDGER_ENTRIES_PER_CHAIN
                for item in ledger
            )
            or sum(len(item["ledger"]) for item in ledger)
            > MAX_LEDGER_ENTRIES_PER_LANE
            or selected_id
            not in ({None} | {item["placement_id"] for item in materialized})
        ):
            raise ValueError("bounded chain ledger is invalid")
        source_ledger_count += sum(len(item["ledger"]) for item in ledger)
        outputs = selection["safe_crop_envelopes"]
        budgets = selection["direct_use_budget_assessments"]
        if {item["geometry_id"] for item in outputs} != {
            item["geometry_id"] for item in budgets
        }:
            raise ValueError("budget does not cover every selected output")
        if outputs and selected_id is None:
            raise ValueError("safe envelope lacks a selected placement")
        for item in outputs:
            if (
                item.get("provenance")
                != "selected_placement_safety_footprint"
                or item.get("mapped_output_box") is None
                or len(item.get("placement_source_footprint", ())) < 3
                or len(item.get("required_source_footprint", ())) < 3
                or len(item.get("constrained_source_footprint", ())) < 3
            ):
                raise ValueError("continuous placement output is incomplete")
    if source_ledger_count > MAX_LEDGER_ENTRIES_PER_SOURCE:
        raise ValueError("source chain ledger exceeds its bound")
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
