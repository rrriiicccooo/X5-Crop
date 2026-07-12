from __future__ import annotations

from typing import Any

from ..constants import FINAL_REVIEW_REASONS
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION


CURRENT_REPORT_SECTIONS = (
    "schema_id",
    "schema_revision",
    "script_version",
    "source",
    "profile",
    "format_id",
    "strip_mode",
    "layout",
    "count",
    "count_resolution",
    "holder_span",
    "visible_sequence_span",
    "crop_envelope",
    "boundary_observations",
    "strip_completeness",
    "holder_occupancy",
    "status",
    "final_review_reasons",
    "decision_geometry",
    "output_geometry",
    "separator_observations",
    "separator_assignments",
    "frame_boundaries",
    "holder_occlusion",
    "inter_frame_spacing",
    "sequence_conservation",
    "candidate_table",
    "selection",
    "policy",
    "policy_id",
    "evidence_summary",
    "candidate_gate",
    "decision_gate",
    "scan_calibration",
    "analysis_reuse_signature",
    "analysis_reuse",
    "schema_validation",
    "diagnostics",
    "output",
)


def _box_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and {"left", "top", "right", "bottom"}.issubset(value)
        and int(value["right"]) > int(value["left"])
        and int(value["bottom"]) > int(value["top"])
    )


def _span_valid(value: Any) -> bool:
    return isinstance(value, dict) and _box_valid(value.get("box"))


def _geometry_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and _box_valid(value.get("crop_envelope"))
        and isinstance(value.get("frame_boxes"), list)
        and all(_box_valid(frame) for frame in value["frame_boxes"])
    )


def _provenance_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and {
            "root_measurement",
            "source",
            "dependencies",
            "boundary_anchors",
        }.issubset(value)
        and isinstance(value["dependencies"], list)
        and isinstance(value["boundary_anchors"], list)
    )


def _separator_observation_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and {
            "start",
            "end",
            "center",
            "tonal_evidence",
            "provenance",
            "lane_box",
            "continuity",
            "tonal_evidence",
        }.issubset(value)
        and float(value["end"]) > float(value["start"])
        and _provenance_valid(value["provenance"])
        and (value["lane_box"] is None or _box_valid(value["lane_box"]))
    )


def _separator_assignment_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and {
            "boundary_index",
            "observation",
            "position_constraint",
            "width_constraint",
            "state",
            "geometry_dependent",
            "used_for_boundary",
            "reason",
        }.issubset(value)
        and _separator_observation_valid(value["observation"])
        and isinstance(value["position_constraint"], dict)
        and isinstance(value["width_constraint"], dict)
    )


def _decision_consistent(record: dict[str, Any], errors: list[str]) -> None:
    gate = record["decision_gate"]
    if not (
        isinstance(gate, dict)
        and isinstance(gate.get("passed"), bool)
        and isinstance(gate.get("checks"), list)
        and isinstance(gate.get("reason_inputs"), list)
    ):
        errors.append("decision_gate_incomplete")
        return
    blocking = [
        check
        for check in gate["checks"]
        if isinstance(check, dict)
        and check.get("consequence") == "blocker"
        and check.get("state") == "contradicted"
    ]
    derived_passed = not blocking
    derived_reasons = list(
        dict.fromkeys(
            str(check["final_review_reason"])
            for check in blocking
            if check.get("final_review_reason") is not None
        )
    )
    if gate["passed"] != derived_passed:
        errors.append("decision_gate_passed_mismatch")
    if gate["passed"] != (record["status"] == "approved_auto"):
        errors.append("decision_gate_status_mismatch")
    if derived_reasons != record["final_review_reasons"]:
        errors.append("decision_gate_reason_mismatch")


def current_report_record_errors(record: dict[str, Any]) -> list[str]:
    errors = [
        f"missing_section:{key}" for key in CURRENT_REPORT_SECTIONS if key not in record
    ]
    if errors:
        return errors
    if record["schema_id"] != REPORT_SCHEMA_ID:
        errors.append("schema_id_mismatch")
    if record["schema_revision"] != REPORT_SCHEMA_REVISION:
        errors.append("schema_revision_mismatch")
    if record["status"] not in {"approved_auto", "needs_review"}:
        errors.append("invalid_status")
    if record["schema_validation"]:
        errors.append("schema_validation_not_empty")
    for key in ("holder_span", "visible_sequence_span", "crop_envelope"):
        if not _span_valid(record[key]):
            errors.append(f"{key}_invalid")
    for key in ("decision_geometry", "output_geometry"):
        if not _geometry_valid(record[key]):
            errors.append(f"{key}_invalid")
    for key in (
        "boundary_observations",
        "separator_observations",
        "separator_assignments",
        "frame_boundaries",
        "inter_frame_spacing",
        "candidate_table",
    ):
        if not isinstance(record[key], list):
            errors.append(f"{key}_not_list")
    if isinstance(record["separator_observations"], list) and any(
        not _separator_observation_valid(item)
        for item in record["separator_observations"]
    ):
        errors.append("separator_observation_invalid")
    if isinstance(record["separator_assignments"], list) and any(
        not _separator_assignment_valid(item)
        for item in record["separator_assignments"]
    ):
        errors.append("separator_assignment_invalid")
    for key in (
        "profile",
        "strip_completeness",
        "holder_occupancy",
        "holder_occlusion",
        "sequence_conservation",
        "selection",
        "policy",
        "evidence_summary",
        "candidate_gate",
        "decision_gate",
        "scan_calibration",
        "analysis_reuse_signature",
        "analysis_reuse",
        "diagnostics",
        "output",
    ):
        if not isinstance(record[key], dict):
            errors.append(f"section_not_mapping:{key}")
    candidate_gate = record["candidate_gate"]
    if not (
        isinstance(candidate_gate, dict)
        and isinstance(candidate_gate.get("passed"), bool)
        and all(
            isinstance(candidate_gate.get(field), list)
            for field in ("checks", "proof_paths", "failed_checks", "diagnostics")
        )
    ):
        errors.append("candidate_gate_incomplete")
    _decision_consistent(record, errors)
    reasons = record["final_review_reasons"]
    if not isinstance(reasons, list):
        errors.append("final_review_reasons_not_list")
    else:
        for reason in reasons:
            if not isinstance(reason, str):
                errors.append("final_review_reason_not_string")
            elif reason not in FINAL_REVIEW_REASONS:
                errors.append(f"unknown_final_review_reason:{reason}")
        if record["status"] == "approved_auto" and reasons:
            errors.append("approved_auto_has_final_review_reasons")
        if record["status"] == "needs_review" and not reasons:
            errors.append("needs_review_missing_final_review_reason")
    diagnostics = record["diagnostics"]
    transform_fields = {
        "state",
        "applied",
        "estimated_angle_degrees",
        "applied_angle_degrees",
        "reason",
        "span_px",
        "span_threshold_px",
    }
    if not (
        isinstance(diagnostics, dict)
        and isinstance(diagnostics.get("detection"), list)
        and isinstance(diagnostics.get("transform_geometry"), dict)
        and transform_fields.issubset(diagnostics["transform_geometry"])
    ):
        errors.append("transform_geometry_incomplete")
    output = record["output"]
    if not (
        isinstance(output, dict)
        and {
            "output_files",
            "review_copy",
            "warnings",
            "frame_bleed_plan",
        }.issubset(output)
        and isinstance(output["frame_bleed_plan"], dict)
    ):
        errors.append("output_section_incomplete")
    return errors


def validate_current_report_record(record: dict[str, Any]) -> None:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError(f"invalid current report record: {', '.join(errors)}")
