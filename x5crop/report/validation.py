from __future__ import annotations

from typing import Any

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
    "count_selection",
    "strip_completeness",
    "holder_occupancy",
    "status",
    "confidence",
    "final_review_reasons",
    "outer_box",
    "frame_boxes",
    "gaps",
    "candidate_table",
    "policy",
    "policy_id",
    "evidence",
    "evidence_summary",
    "candidate_gate",
    "decision_signals",
    "decision_gate",
    "scan_calibration",
    "decision_geometry",
    "analysis_cache",
    "analysis_reuse",
    "schema_validation",
    "diagnostics",
    "output",
)


def _box_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not {"left", "top", "right", "bottom"}.issubset(value):
        return False
    return int(value["right"]) > int(value["left"]) and int(value["bottom"]) > int(value["top"])


def _geometry_valid(value: Any) -> bool:
    if not isinstance(value, dict) or not _box_valid(value.get("outer_box")):
        return False
    frames = value.get("frame_boxes")
    return isinstance(frames, list) and all(_box_valid(frame) for frame in frames)


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
    if not _box_valid(record["outer_box"]):
        errors.append("outer_box_invalid")
    frames = record["frame_boxes"]
    if not isinstance(frames, list) or any(not _box_valid(frame) for frame in frames):
        errors.append("frame_boxes_invalid")
    if not _geometry_valid(record["decision_geometry"]):
        errors.append("decision_geometry_invalid")
    expected_mappings = (
        "profile",
        "count_selection",
        "strip_completeness",
        "holder_occupancy",
        "policy",
        "evidence",
        "evidence_summary",
        "candidate_gate",
        "decision_signals",
        "decision_gate",
        "scan_calibration",
        "analysis_cache",
        "analysis_reuse",
        "diagnostics",
        "output",
    )
    for key in expected_mappings:
        if not isinstance(record[key], dict):
            errors.append(f"section_not_mapping:{key}")
    if not isinstance(record["candidate_table"], list):
        errors.append("candidate_table_not_list")
    if not isinstance(record["gaps"], list):
        errors.append("gaps_not_list")
    else:
        gap_fields = {"index", "center", "score", "method", "start", "end", "lane_box"}
        if any(
            not isinstance(gap, dict) or not gap_fields.issubset(gap)
            for gap in record["gaps"]
        ):
            errors.append("gap_record_invalid")
    if not isinstance(record["final_review_reasons"], list):
        errors.append("final_review_reasons_not_list")
    diagnostics = record["diagnostics"]
    if isinstance(diagnostics, dict):
        deskew = diagnostics.get("deskew")
        if not isinstance(deskew, dict) or "applied" not in deskew:
            errors.append("deskew_diagnostic_invalid")
        elif bool(deskew["applied"]) and "angle" not in deskew:
            errors.append("deskew_angle_missing")
    output = record["output"]
    if isinstance(output, dict):
        required_output = {"output_files", "review_copy", "warnings", "protection_plan"}
        if not required_output.issubset(output):
            errors.append("output_section_incomplete")
        elif not isinstance(output["protection_plan"], dict):
            errors.append("output_protection_plan_invalid")
    return errors


def validate_current_report_record(record: dict[str, Any]) -> None:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError(f"Invalid current report record: {', '.join(errors)}")
