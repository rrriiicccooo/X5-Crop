from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from ..configuration.candidate import CandidatePlanParameters
from ..configuration.content import ContentConfiguration
from ..configuration.diagnostics import DiagnosticsConfiguration
from ..configuration.preprocess import PreprocessConfiguration
from ..configuration.separator import SeparatorConfiguration
from ..constants import FINAL_REVIEW_REASONS
from ..detection.candidate.assessment.candidate_gate import BoundaryProofPath
from ..detection.candidate.model import CandidateEvidence, EvidenceQuality
from ..detection.candidate.plan.count_hypotheses import CountHypothesis
from ..detection.candidate.selection.model import CountResolution, GeometryResolution
from ..detection.gate_checks import GateCheck
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..detection.physical.model import (
    DualLaneSolution,
    ReviewOnlyGeometry,
    SequenceSolution,
)
from ..detection.physical.spacing import (
    CorroboratedSpacingEvidence,
    ObservedSpacingEvidence,
    SpacingHypothesis,
)
from ..domain import ImageProfile, SeparatorAssignment, SeparatorBandObservation
from ..formats import FrameSizeMm
from ..output.model import FrameBleedPlan
from ..units import ScanCalibration
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


_SPACING_MODELS = {
    "observed": ObservedSpacingEvidence,
    "corroborated": CorroboratedSpacingEvidence,
    "hypothesis": SpacingHypothesis,
}


@lru_cache(maxsize=None)
def _model_hints(model: type) -> dict[str, Any]:
    return get_type_hints(model)


def _spacing_read_model_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    model = _SPACING_MODELS.get(value.get("measurement_kind"))
    if model is None:
        return False
    model_fields = {field.name for field in fields(model)}
    expected = model_fields | {
        "measurement_kind",
        "state",
        "independently_observed",
        "supports_output_protection",
    }
    hints = _model_hints(model)
    return bool(
        set(value) == expected
        and all(
            _typed_value_valid(value[name], hints[name])
            for name in model_fields
        )
        and value["state"]
        in {"supported", "contradicted", "unavailable", "not_applicable"}
        and isinstance(value["independently_observed"], bool)
        and isinstance(value["supports_output_protection"], bool)
    )


def _typed_value_valid(value: Any, annotation: Any) -> bool:
    if annotation is Any:
        return True
    if annotation is type(None):
        return value is None
    if annotation is bool:
        return isinstance(value, bool)
    if annotation is int:
        return _integer(value) is not None
    if annotation is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if annotation is str:
        return isinstance(value, str)
    if annotation is bytes:
        return isinstance(value, str) and value.startswith("<bytes:")
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return value in {item.value for item in annotation}

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {UnionType, Union}:
        if isinstance(value, dict) and "measurement_kind" in value:
            return _spacing_read_model_valid(value)
        return any(_typed_value_valid(value, item) for item in arguments)
    if origin is tuple:
        if not isinstance(value, list):
            return False
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return all(_typed_value_valid(item, arguments[0]) for item in value)
        return len(value) == len(arguments) and all(
            _typed_value_valid(item, item_type)
            for item, item_type in zip(value, arguments, strict=True)
        )
    if is_dataclass(annotation):
        if not isinstance(value, dict):
            return False
        model_fields = {field.name for field in fields(annotation)}
        if set(value) != model_fields:
            return False
        hints = _model_hints(annotation)
        return all(
            _typed_value_valid(value[name], hints[name])
            for name in model_fields
        )
    return isinstance(value, annotation) if isinstance(annotation, type) else False


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _box_valid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "left",
        "top",
        "right",
        "bottom",
    }:
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
    return bool(
        isinstance(value, dict)
        and set(value) == {"box"}
        and _box_valid(value["box"])
    )


def _geometry_valid(value: Any, *, allow_empty_frames: bool = False) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"crop_envelope", "frame_boxes"}
        and _box_valid(value["crop_envelope"])
        and isinstance(value["frame_boxes"], list)
        and (allow_empty_frames or value["frame_boxes"])
        and all(_box_valid(frame) for frame in value["frame_boxes"])
    )


def _separator_observation_valid(value: Any) -> bool:
    return _typed_value_valid(value, SeparatorBandObservation)


def _separator_assignment_valid(value: Any) -> bool:
    return _typed_value_valid(value, SeparatorAssignment)


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
    model_by_kind = {
        "sequence": SequenceSolution,
        "dual_lane": DualLaneSolution,
        "review_only": ReviewOnlyGeometry,
    }
    model = model_by_kind.get(kind)
    if model is None or not _typed_value_valid(value, model):
        return False
    count = _integer(value.get("count")) if isinstance(value, dict) else None
    if not (
        isinstance(value, dict)
        and count is not None
        and count > 0
        and _span_valid(value["holder_span"])
        and _span_valid(value["visible_sequence_span"])
        and _span_valid(value["crop_envelope"])
    ):
        return False
    if kind == "sequence":
        return bool(
            _sequence_geometry_valid(value)
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
        )
    if kind == "dual_lane":
        lane_solutions = value["lane_solutions"]
        lane_boxes = value["lane_boxes"]
        lane_envelopes = value["lane_crop_envelopes"]
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
        return bool(
            isinstance(value["frames"], list)
            and len(value["frames"]) == count
            and all(_box_valid(frame) for frame in value["frames"])
            and isinstance(lane_solutions, list)
            and len(lane_solutions) > 1
            and all(_sequence_geometry_valid(lane) for lane in lane_solutions)
            and lane_counts_valid
            and component_count == count
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


def _gate_check_valid(value: Any) -> bool:
    expected = {field.name for field in fields(GateCheck)} | {"blocks"}
    if not (
        isinstance(value, dict)
        and set(value) == expected
        and _typed_value_valid(
            {name: value[name] for name in expected if name != "blocks"},
            GateCheck,
        )
        and isinstance(value["blocks"], bool)
    ):
        return False
    expected_blocks = value["state"] == "contradicted"
    return value["blocks"] == expected_blocks


def _candidate_gate_valid(value: Any) -> bool:
    expected = {
        "passed",
        "checks",
        "proof_paths",
        "failed_checks",
        "diagnostics",
    }
    if not (
        isinstance(value, dict)
        and set(value) == expected
        and isinstance(value["passed"], bool)
        and isinstance(value["checks"], list)
        and all(_gate_check_valid(check) for check in value["checks"])
        and _typed_value_valid(
            value["proof_paths"],
            tuple[BoundaryProofPath, ...],
        )
        and isinstance(value["failed_checks"], list)
        and all(isinstance(code, str) for code in value["failed_checks"])
        and isinstance(value["diagnostics"], list)
        and all(isinstance(item, str) for item in value["diagnostics"])
    ):
        return False
    failed = [check["code"] for check in value["checks"] if check["blocks"]]
    return value["failed_checks"] == failed and value["passed"] == (not failed)


def _candidate_valid(value: Any) -> bool:
    expected = {
        "geometry_kind",
        "candidate_geometry",
        "evidence_quality",
        "candidate_gate",
        "count_hypothesis",
        "evidence",
        "diagnostics",
    }
    if not isinstance(value, dict) or set(value) != expected:
        return False
    if not _candidate_geometry_valid(
        str(value["geometry_kind"]),
        value["candidate_geometry"],
    ):
        return False
    return bool(
        _candidate_gate_valid(value["candidate_gate"])
        and _typed_value_valid(value["evidence_quality"], EvidenceQuality)
        and _typed_value_valid(value["evidence"], CandidateEvidence)
        and (
            value["count_hypothesis"] is None
            or _typed_value_valid(value["count_hypothesis"], CountHypothesis)
        )
        and isinstance(value["diagnostics"], list)
        and all(isinstance(item, str) for item in value["diagnostics"])
    )


def _geometry_resolution_valid(value: Any) -> bool:
    return _typed_value_valid(value, GeometryResolution)


def _selection_valid(value: Any) -> bool:
    expected = {
        "selected_rank",
        "consensus",
        "geometry_resolution",
        "count_resolution",
        "candidates",
        "clusters",
    }
    if not (
        isinstance(value, dict)
        and set(value) == expected
        and value["consensus"] in {"agreed", "uncontested", "disagreed"}
        and isinstance(value["candidates"], list)
        and value["candidates"]
        and all(_candidate_valid(candidate) for candidate in value["candidates"])
        and _geometry_resolution_valid(value["geometry_resolution"])
        and (
            value["count_resolution"] is None
            or _typed_value_valid(value["count_resolution"], CountResolution)
        )
        and isinstance(value["clusters"], list)
    ):
        return False
    selected_rank = _integer(value["selected_rank"])
    if selected_rank is None:
        return False
    if not 1 <= selected_rank <= len(value["candidates"]):
        return False
    cluster_fields = {"candidate_ranks", "representative_rank"}
    return all(
        isinstance(cluster, dict)
        and set(cluster) == cluster_fields
        and isinstance(cluster["candidate_ranks"], list)
        and cluster["candidate_ranks"]
        and all(
            _integer(rank) is not None
            and 1 <= rank <= len(value["candidates"])
            for rank in cluster["candidate_ranks"]
        )
        and _integer(cluster["representative_rank"]) is not None
        and cluster["representative_rank"] in cluster["candidate_ranks"]
        for cluster in value["clusters"]
    )


def _decision_consistent(value: Any, errors: list[str]) -> None:
    if not (
        isinstance(value, dict)
        and set(value) == {"status", "final_review_reasons", "gate"}
        and value["status"] in {"approved_auto", "needs_review"}
        and isinstance(value["final_review_reasons"], list)
        and all(isinstance(reason, str) for reason in value["final_review_reasons"])
        and isinstance(value["gate"], dict)
    ):
        errors.append("decision_incomplete")
        return
    gate = value["gate"]
    if not (
        set(gate) == {"passed", "checks", "reason_inputs"}
        and isinstance(gate["passed"], bool)
        and isinstance(gate["checks"], list)
        and all(_gate_check_valid(check) for check in gate["checks"])
        and isinstance(gate["reason_inputs"], list)
        and all(
            isinstance(item, dict)
            and set(item) == {"check", "final_review_reason"}
            and isinstance(item["check"], str)
            and isinstance(item["final_review_reason"], str)
            for item in gate["reason_inputs"]
        )
    ):
        errors.append("decision_gate_incomplete")
        return
    blocking = [
        check
        for check in gate["checks"]
        if isinstance(check, dict)
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
    derived_inputs = [
        {
            "check": str(check["code"]),
            "final_review_reason": str(check["final_review_reason"]),
        }
        for check in blocking
        if check.get("final_review_reason") is not None
    ]
    if derived_inputs != gate["reason_inputs"]:
        errors.append("decision_gate_reason_inputs_mismatch")
    for reason in value["final_review_reasons"]:
        if reason not in FINAL_REVIEW_REASONS:
            errors.append(f"unknown_final_review_reason:{reason}")


def _frame_bleed_plan_valid(value: Any, frame_count: int) -> bool:
    return bool(
        _typed_value_valid(value, FrameBleedPlan)
        and len(value["frame_sides"]) == frame_count
        and value["feasible"] == (not value["unresolved_overlap_boundaries"])
    )


def _output_valid(value: Any, *, allow_empty_frames: bool) -> bool:
    expected = {
        "decision_geometry",
        "final_geometry",
        "frame_bleed_plan",
        "output_files",
        "review_copy",
        "warnings",
    }
    if not (
        isinstance(value, dict)
        and set(value) == expected
        and _geometry_valid(
            value["decision_geometry"],
            allow_empty_frames=allow_empty_frames,
        )
        and _geometry_valid(
            value["final_geometry"],
            allow_empty_frames=allow_empty_frames,
        )
        and isinstance(value["output_files"], list)
        and all(isinstance(path, str) for path in value["output_files"])
        and (value["review_copy"] is None or isinstance(value["review_copy"], str))
        and isinstance(value["warnings"], list)
        and all(isinstance(warning, str) for warning in value["warnings"])
    ):
        return False
    return _frame_bleed_plan_valid(
        value["frame_bleed_plan"],
        len(value["final_geometry"]["frame_boxes"]),
    )


def _input_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"profile", "scan_calibration"}
        and _typed_value_valid(value["profile"], ImageProfile)
        and _typed_value_valid(value["scan_calibration"], ScanCalibration)
    )


def _configuration_valid(value: Any) -> bool:
    top_fields = {
        "configuration_id",
        "format_id",
        "strip_mode",
        "physical",
        "measurement",
        "execution",
        "diagnostics",
    }
    physical_fields = {
        "family",
        "physical_layout",
        "default_count",
        "expected_separator_count",
        "allowed_counts",
        "nominal_frame_size_mm",
        "frame_size_mm_options",
        "frame_aspect",
        "aspect_source",
        "complete_strip_can_be_underfilled",
    }
    measurement_fields = {"preprocess", "separator", "content"}
    execution_fields = {"detector_kind", "candidate_plan"}
    if not isinstance(value, dict) or set(value) != top_fields:
        return False
    physical = value["physical"]
    measurement = value["measurement"]
    execution = value["execution"]
    return bool(
        isinstance(value["configuration_id"], str)
        and isinstance(value["format_id"], str)
        and isinstance(value["strip_mode"], str)
        and isinstance(physical, dict)
        and set(physical) == physical_fields
        and isinstance(physical["family"], str)
        and physical["physical_layout"] in {"single_strip", "dual_lane"}
        and _integer(physical["default_count"]) is not None
        and _integer(physical["expected_separator_count"]) is not None
        and isinstance(physical["allowed_counts"], list)
        and all(_integer(count) is not None for count in physical["allowed_counts"])
        and _typed_value_valid(physical["nominal_frame_size_mm"], FrameSizeMm)
        and _typed_value_valid(
            physical["frame_size_mm_options"],
            tuple[FrameSizeMm, ...],
        )
        and _typed_value_valid(physical["frame_aspect"], float)
        and physical["aspect_source"] == "frame_size_mm"
        and isinstance(physical["complete_strip_can_be_underfilled"], bool)
        and isinstance(measurement, dict)
        and set(measurement) == measurement_fields
        and _typed_value_valid(measurement["preprocess"], PreprocessConfiguration)
        and _typed_value_valid(measurement["separator"], SeparatorConfiguration)
        and _typed_value_valid(measurement["content"], ContentConfiguration)
        and isinstance(execution, dict)
        and set(execution) == execution_fields
        and execution["detector_kind"]
        in {"standard_strip", "dual_lane", "review_only"}
        and _typed_value_valid(
            execution["candidate_plan"],
            CandidatePlanParameters,
        )
        and _typed_value_valid(value["diagnostics"], DiagnosticsConfiguration)
    )


def _analysis_reuse_signature_valid(value: Any) -> bool:
    top_fields = {
        "script",
        "script_version",
        "source",
        "config",
        "configuration_fingerprint",
    }
    source_fields = {
        "name",
        "size",
        "mtime_ns",
        "content_sha256",
        "page",
        "shape",
        "dtype",
        "axes",
        "photometric",
    }
    config_fields = {
        "format_id",
        "layout",
        "strip_mode",
        "requested_count",
        "page",
        "deskew",
        "deskew_fallback",
        "deskew_min_angle",
        "deskew_max_angle",
        "bleed_x",
        "bleed_y",
    }
    if not isinstance(value, dict) or set(value) != top_fields:
        return False
    source = value["source"]
    config = value["config"]
    return bool(
        isinstance(value["script"], str)
        and isinstance(value["script_version"], str)
        and isinstance(value["configuration_fingerprint"], str)
        and isinstance(source, dict)
        and set(source) == source_fields
        and isinstance(source["name"], str)
        and all(
            _integer(source[field]) is not None
            for field in ("size", "mtime_ns", "page")
        )
        and isinstance(source["content_sha256"], str)
        and len(source["content_sha256"]) == 64
        and isinstance(source["shape"], list)
        and all(_integer(item) is not None for item in source["shape"])
        and all(
            isinstance(source[field], str)
            for field in ("dtype", "axes", "photometric")
        )
        and isinstance(config, dict)
        and set(config) == config_fields
        and all(
            isinstance(config[field], str)
            for field in (
                "format_id",
                "layout",
                "strip_mode",
                "deskew",
                "deskew_fallback",
            )
        )
        and (
            config["requested_count"] is None
            or _integer(config["requested_count"]) is not None
        )
        and all(
            _integer(config[field]) is not None
            for field in ("page", "bleed_x", "bleed_y")
        )
        and all(
            _typed_value_valid(config[field], float)
            for field in ("deskew_min_angle", "deskew_max_angle")
        )
    )


def _diagnostics_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"transform_geometry", "detection"}
        and isinstance(value["detection"], list)
        and all(isinstance(item, str) for item in value["detection"])
        and _typed_value_valid(
            value["transform_geometry"],
            TransformGeometryEvidence,
        )
    )


def current_report_record_errors(record: dict[str, Any]) -> list[str]:
    errors = [
        f"missing_section:{key}"
        for key in CURRENT_REPORT_SECTIONS
        if key not in record
    ]
    if errors:
        return errors
    unexpected = sorted(set(record) - set(CURRENT_REPORT_SECTIONS))
    if unexpected:
        errors.extend(f"unexpected_section:{key}" for key in unexpected)
    if record["schema_id"] != REPORT_SCHEMA_ID:
        errors.append("schema_id_mismatch")
    if record["schema_revision"] != REPORT_SCHEMA_REVISION:
        errors.append("schema_revision_mismatch")
    if not isinstance(record["script_version"], str):
        errors.append("script_version_invalid")
    if not isinstance(record["source"], str):
        errors.append("source_invalid")
    if not isinstance(record["schema_validation"], list) or record["schema_validation"]:
        errors.append("schema_validation_not_empty")
    input_detail = record["input"]
    if not _input_valid(input_detail):
        errors.append("input_incomplete")
    configuration = record["configuration"]
    if not _configuration_valid(configuration):
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
    if not _diagnostics_valid(record["diagnostics"]):
        errors.append("transform_geometry_incomplete")
    if not _analysis_reuse_signature_valid(record["analysis_reuse_signature"]):
        errors.append("analysis_reuse_signature_invalid")
    if not (
        isinstance(record["analysis_reuse"], dict)
        and set(record["analysis_reuse"]) == {"used"}
        and isinstance(record["analysis_reuse"]["used"], bool)
    ):
        errors.append("analysis_reuse_invalid")
    return errors


def validate_current_report_record(record: dict[str, Any]) -> None:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError("invalid current report record: " + ", ".join(errors))
