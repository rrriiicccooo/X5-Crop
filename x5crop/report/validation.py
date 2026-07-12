from __future__ import annotations

from typing import Any

from ..constants import FINAL_REVIEW_REASONS
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION


CURRENT_REPORT_SECTIONS = (
    "schema_id",
    "schema_revision",
    "script_version",
    "source",
    "input",
    "configuration",
    "selection",
    "decision",
    "output",
    "analysis_reuse_signature",
    "analysis_reuse",
    "schema_validation",
    "diagnostics",
)


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _box_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    left = _integer(value.get("left"))
    top = _integer(value.get("top"))
    right = _integer(value.get("right"))
    bottom = _integer(value.get("bottom"))
    return bool(
        None not in {left, top, right, bottom}
        and right is not None
        and left is not None
        and bottom is not None
        and top is not None
        and right > left
        and bottom > top
    )


def _span_valid(value: Any) -> bool:
    return isinstance(value, dict) and _box_valid(value.get("box"))


def _geometry_valid(value: Any, *, allow_empty_frames: bool = False) -> bool:
    return bool(
        isinstance(value, dict)
        and _box_valid(value.get("crop_envelope"))
        and isinstance(value.get("frame_boxes"), list)
        and (allow_empty_frames or value["frame_boxes"])
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


def _sequence_geometry_valid(value: Any) -> bool:
    count = _integer(value.get("count")) if isinstance(value, dict) else None
    return bool(
        isinstance(value, dict)
        and count is not None
        and count > 0
        and isinstance(value.get("frames"), list)
        and len(value["frames"]) == count
        and all(_box_valid(frame) for frame in value["frames"])
        and isinstance(value.get("photo_intervals"), list)
        and len(value["photo_intervals"]) == count
        and isinstance(value.get("frame_boundaries"), list)
        and len(value["frame_boundaries"]) == count - 1
        and isinstance(value.get("inter_frame_spacings"), list)
        and len(value["inter_frame_spacings"]) == count - 1
    )


def _candidate_geometry_valid(kind: str, value: Any) -> bool:
    common_fields = {
        "format_id",
        "layout",
        "strip_mode",
        "count",
        "holder_span",
        "visible_sequence_span",
        "crop_envelope",
        "photo_intervals",
        "frames",
        "separator_observations",
        "separator_assignments",
        "frame_boundaries",
        "inter_frame_spacings",
        "holder_occlusion",
        "frame_dimension_prior",
        "residuals",
        "search_budget_exhausted",
        "source",
        "automatic_processing_supported",
        "sequence_hypothesis_name",
        "sequence_hypothesis_strategy",
        "sequence_provenance",
        "boundary_observations",
    }
    count = _integer(value.get("count")) if isinstance(value, dict) else None
    if not (
        isinstance(value, dict)
        and common_fields.issubset(value)
        and count is not None
        and count > 0
        and _span_valid(value["holder_span"])
        and _span_valid(value["visible_sequence_span"])
        and _span_valid(value["crop_envelope"])
        and isinstance(value["separator_observations"], list)
        and all(
            _separator_observation_valid(item)
            for item in value["separator_observations"]
        )
        and isinstance(value["separator_assignments"], list)
        and all(
            _separator_assignment_valid(item)
            for item in value["separator_assignments"]
        )
    ):
        return False
    if kind == "sequence":
        return _sequence_geometry_valid(value)
    if kind == "dual_lane":
        lane_solutions = value.get("lane_solutions")
        lane_boxes = value.get("lane_boxes")
        lane_envelopes = value.get("lane_crop_envelopes")
        lane_counts = (
            tuple(
                _integer(lane.get("count"))
                if isinstance(lane, dict)
                else None
                for lane in lane_solutions
            )
            if isinstance(lane_solutions, list)
            else ()
        )
        lane_counts_valid = bool(
            lane_counts
            and all(item is not None and item > 0 for item in lane_counts)
        )
        component_count = (
            sum(item for item in lane_counts if item is not None)
            if lane_counts_valid
            else 0
        )
        component_boundaries = (
            sum(item - 1 for item in lane_counts if item is not None)
            if lane_counts_valid
            else 0
        )
        return bool(
            isinstance(value["frames"], list)
            and len(value["frames"]) == count
            and all(_box_valid(frame) for frame in value["frames"])
            and isinstance(value["photo_intervals"], list)
            and len(value["photo_intervals"]) == count
            and isinstance(value["frame_boundaries"], list)
            and len(value["frame_boundaries"]) == component_boundaries
            and isinstance(value["inter_frame_spacings"], list)
            and len(value["inter_frame_spacings"]) == component_boundaries
            and isinstance(lane_solutions, list)
            and len(lane_solutions) > 1
            and lane_counts_valid
            and component_count == count
            and all(
                _candidate_geometry_valid("sequence", lane)
                for lane in lane_solutions
            )
            and isinstance(lane_boxes, list)
            and len(lane_boxes) == len(lane_solutions)
            and all(_box_valid(box) for box in lane_boxes)
            and isinstance(lane_envelopes, list)
            and len(lane_envelopes) == len(lane_solutions)
            and all(_span_valid(envelope) for envelope in lane_envelopes)
        )
    if kind == "review_only":
        return bool(
            value["frames"] == []
            and value["photo_intervals"] == []
            and value["separator_observations"] == []
            and value["separator_assignments"] == []
            and value["frame_boundaries"] == []
            and value["inter_frame_spacings"] == []
            and not value["automatic_processing_supported"]
        )
    return False


def _candidate_valid(value: Any) -> bool:
    if not (
        isinstance(value, dict)
        and {
            "geometry_kind",
            "candidate_geometry",
            "evidence_quality",
            "candidate_gate",
            "count_hypothesis",
            "evidence",
            "diagnostics",
        }.issubset(value)
    ):
        return False
    if not _candidate_geometry_valid(
        str(value["geometry_kind"]),
        value["candidate_geometry"],
    ):
        return False
    gate = value["candidate_gate"]
    return bool(
        isinstance(gate, dict)
        and isinstance(gate.get("passed"), bool)
        and isinstance(gate.get("checks"), list)
        and isinstance(gate.get("proof_paths"), list)
        and isinstance(gate.get("failed_checks"), list)
        and isinstance(gate.get("diagnostics"), list)
        and isinstance(value["evidence_quality"], dict)
        and isinstance(value["evidence"], dict)
        and isinstance(value["diagnostics"], list)
    )


def _selection_valid(value: Any) -> bool:
    if not (
        isinstance(value, dict)
        and {
            "selected_rank",
            "consensus",
            "geometry_resolution",
            "count_resolution",
            "candidates",
            "clusters",
        }.issubset(value)
        and isinstance(value["candidates"], list)
        and value["candidates"]
        and all(_candidate_valid(candidate) for candidate in value["candidates"])
        and isinstance(value["clusters"], list)
    ):
        return False
    selected_rank = _integer(value["selected_rank"])
    if selected_rank is None:
        return False
    return 1 <= selected_rank <= len(value["candidates"])


def _decision_consistent(value: Any, errors: list[str]) -> None:
    if not (
        isinstance(value, dict)
        and {"status", "final_review_reasons", "gate"}.issubset(value)
        and value["status"] in {"approved_auto", "needs_review"}
        and isinstance(value["final_review_reasons"], list)
        and isinstance(value["gate"], dict)
    ):
        errors.append("decision_incomplete")
        return
    gate = value["gate"]
    if not (
        isinstance(gate.get("passed"), bool)
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
    if gate["passed"] != (value["status"] == "approved_auto"):
        errors.append("decision_gate_status_mismatch")
    if derived_reasons != value["final_review_reasons"]:
        errors.append("decision_gate_reason_mismatch")
    for reason in value["final_review_reasons"]:
        if reason not in FINAL_REVIEW_REASONS:
            errors.append(f"unknown_final_review_reason:{reason}")


def _frame_bleed_plan_valid(value: Any, frame_count: int) -> bool:
    if not (
        isinstance(value, dict)
        and {
            "user_bleed",
            "frame_sides",
            "overlap_protection",
            "unresolved_overlap_boundaries",
            "feasible",
            "reason",
        }.issubset(value)
        and isinstance(value["user_bleed"], dict)
        and {"long_axis", "short_axis"}.issubset(value["user_bleed"])
        and isinstance(value["frame_sides"], list)
        and len(value["frame_sides"]) == frame_count
        and isinstance(value["overlap_protection"], list)
        and isinstance(value["unresolved_overlap_boundaries"], list)
        and isinstance(value["feasible"], bool)
        and isinstance(value["reason"], str)
    ):
        return False
    side_fields = {
        "frame_index",
        "leading_px",
        "trailing_px",
        "short_axis_px",
    }
    protection_fields = {
        "boundary_index",
        "left_frame_index",
        "right_frame_index",
        "required_px",
        "left_trailing_available_px",
        "right_leading_available_px",
        "provenance",
    }
    return bool(
        all(
            isinstance(side, dict) and side_fields.issubset(side)
            for side in value["frame_sides"]
        )
        and all(
            isinstance(protection, dict)
            and protection_fields.issubset(protection)
            for protection in value["overlap_protection"]
        )
    )


def _output_valid(value: Any, *, allow_empty_frames: bool) -> bool:
    if not (
        isinstance(value, dict)
        and {
            "decision_geometry",
            "final_geometry",
            "frame_bleed_plan",
            "output_files",
            "review_copy",
            "warnings",
        }.issubset(value)
        and _geometry_valid(
            value["decision_geometry"],
            allow_empty_frames=allow_empty_frames,
        )
        and _geometry_valid(
            value["final_geometry"],
            allow_empty_frames=allow_empty_frames,
        )
        and isinstance(value["output_files"], list)
        and isinstance(value["warnings"], list)
    ):
        return False
    return _frame_bleed_plan_valid(
        value["frame_bleed_plan"],
        len(value["final_geometry"]["frame_boxes"]),
    )


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
    if record["schema_validation"]:
        errors.append("schema_validation_not_empty")
    input_detail = record["input"]
    if not (
        isinstance(input_detail, dict)
        and isinstance(input_detail.get("profile"), dict)
        and isinstance(input_detail.get("scan_calibration"), dict)
    ):
        errors.append("input_incomplete")
    configuration = record["configuration"]
    if not (
        isinstance(configuration, dict)
        and isinstance(configuration.get("configuration_id"), str)
    ):
        errors.append("configuration_incomplete")
    if not _selection_valid(record["selection"]):
        candidates = (
            record["selection"].get("candidates", [])
            if isinstance(record["selection"], dict)
            else []
        )
        invalid_observation = any(
            not _separator_observation_valid(observation)
            for candidate in candidates
            if isinstance(candidate, dict)
            for observation in candidate.get("candidate_geometry", {}).get(
                "separator_observations",
                [],
            )
        )
        errors.append(
            "separator_observation_invalid"
            if invalid_observation
            else "selection_incomplete"
        )
    _decision_consistent(record["decision"], errors)
    selection = record["selection"]
    selected_kind = None
    if (
        isinstance(selection, dict)
        and isinstance(selection.get("candidates"), list)
        and selection["candidates"]
    ):
        selected_rank = _integer(selection.get("selected_rank"))
        if (
            selected_rank is not None
            and 1 <= selected_rank <= len(selection["candidates"])
        ):
            selected_kind = selection["candidates"][selected_rank - 1].get(
                "geometry_kind"
            )
    decision = record["decision"] if isinstance(record["decision"], dict) else {}
    allow_empty_frames = bool(
        selected_kind == "review_only"
        and decision.get("status") == "needs_review"
    )
    if not _output_valid(
        record["output"],
        allow_empty_frames=allow_empty_frames,
    ):
        errors.append("output_incomplete")
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
    if not isinstance(record["analysis_reuse_signature"], dict):
        errors.append("analysis_reuse_signature_invalid")
    if not isinstance(record["analysis_reuse"], dict):
        errors.append("analysis_reuse_invalid")
    return errors


def validate_current_report_record(record: dict[str, Any]) -> None:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError("invalid current report record: " + ", ".join(errors))
