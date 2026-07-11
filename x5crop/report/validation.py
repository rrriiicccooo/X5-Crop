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
    "film_span",
    "pitch",
    "strip_completeness",
    "holder_occupancy",
    "status",
    "confidence",
    "final_review_reasons",
    "separator_observations",
    "candidate_table",
    "selection",
    "policy",
    "policy_id",
    "evidence_summary",
    "candidate_gate",
    "decision_gate",
    "scan_calibration",
    "decision_geometry",
    "output_geometry",
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


def _geometry_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and _box_valid(value.get("outer_box"))
        and isinstance(value.get("frame_boxes"), list)
        and all(_box_valid(frame) for frame in value["frame_boxes"])
    )


def _separator_observation_valid(value: Any) -> bool:
    required = {
        "index",
        "center",
        "score",
        "method",
        "provenance",
        "start",
        "end",
        "lane_box",
        "continuity",
        "tonal_evidence",
    }
    if not isinstance(value, dict) or not required.issubset(value):
        return False
    provenance = value["provenance"]
    if not (
        isinstance(provenance, dict)
        and {
            "root_measurement",
            "source",
            "dependencies",
            "boundary_anchors",
        }.issubset(provenance)
        and isinstance(provenance["dependencies"], list)
        and isinstance(provenance["boundary_anchors"], list)
    ):
        return False
    lane_box = value["lane_box"]
    return lane_box is None or _box_valid(lane_box)


def current_report_record_errors(record: dict[str, Any]) -> list[str]:
    errors = [
        f"missing_section:{key}"
        for key in CURRENT_REPORT_SECTIONS
        if key not in record
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
    if not _geometry_valid(record["decision_geometry"]):
        errors.append("decision_geometry_invalid")
    if not _geometry_valid(record["output_geometry"]):
        errors.append("output_geometry_invalid")
    if not _box_valid(record["film_span"]):
        errors.append("film_span_invalid")
    if not isinstance(record["pitch"], (int, float)) or float(record["pitch"]) <= 0.0:
        errors.append("pitch_invalid")
    for key in (
        "profile",
        "strip_completeness",
        "holder_occupancy",
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
    if record["count_resolution"] is not None and not isinstance(
        record["count_resolution"],
        dict,
    ):
        errors.append("count_resolution_invalid")
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
    decision_gate = record["decision_gate"]
    if not (
        isinstance(decision_gate, dict)
        and isinstance(decision_gate.get("passed"), bool)
        and all(
            isinstance(decision_gate.get(field), list)
            for field in ("checks", "reason_inputs")
        )
    ):
        errors.append("decision_gate_incomplete")
    else:
        blocking_checks = [
            check
            for check in decision_gate["checks"]
            if isinstance(check, dict)
            and check.get("consequence") == "blocker"
            and check.get("state") == "contradicted"
        ]
        derived_passed = not blocking_checks
        derived_reasons = list(
            dict.fromkeys(
                str(check["final_review_reason"])
                for check in blocking_checks
                if check.get("final_review_reason") is not None
            )
        )
        if bool(decision_gate["passed"]) != derived_passed:
            errors.append("decision_gate_passed_mismatch")
        if bool(decision_gate["passed"]) != (
            record["status"] == "approved_auto"
        ):
            errors.append("decision_gate_status_mismatch")
        if derived_reasons != record["final_review_reasons"]:
            errors.append("decision_gate_reason_mismatch")
    if not isinstance(record["candidate_table"], list):
        errors.append("candidate_table_not_list")
    observations = record["separator_observations"]
    if not isinstance(observations, list):
        errors.append("separator_observations_not_list")
    elif any(not _separator_observation_valid(observation) for observation in observations):
        errors.append("separator_observation_invalid")
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
    final_reasons = record["final_review_reasons"]
    if not isinstance(final_reasons, list):
        errors.append("final_review_reasons_not_list")
    else:
        for reason in final_reasons:
            if not isinstance(reason, str):
                errors.append("final_review_reason_not_string")
            elif reason not in FINAL_REVIEW_REASONS:
                errors.append(f"unknown_final_review_reason:{reason}")
        if record["status"] == "approved_auto" and final_reasons:
            errors.append("approved_auto_has_final_review_reasons")
        if record["status"] == "needs_review" and not final_reasons:
            errors.append("needs_review_missing_final_review_reason")
    diagnostics = record["diagnostics"]
    if isinstance(diagnostics, dict):
        transform = diagnostics.get("transform_geometry")
        if not isinstance(transform, dict) or "applied" not in transform:
            errors.append("transform_geometry_diagnostic_invalid")
        elif bool(transform["applied"]) and "applied_angle_degrees" not in transform:
            errors.append("transform_geometry_angle_missing")
    output = record["output"]
    if isinstance(output, dict):
        required_output = {
            "output_files",
            "review_copy",
            "warnings",
            "protection_plan",
        }
        if not required_output.issubset(output):
            errors.append("output_section_incomplete")
        elif not isinstance(output["protection_plan"], dict):
            errors.append("output_protection_plan_invalid")
    return errors


def validate_current_report_record(record: dict[str, Any]) -> None:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError(f"Invalid current report record: {', '.join(errors)}")
