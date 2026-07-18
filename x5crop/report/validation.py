from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from ..configuration.candidate import CandidatePlanParameters
from ..configuration.boundary import BoundaryPathParameters
from ..configuration.content import ContentConfiguration
from ..configuration.diagnostics import DiagnosticsConfiguration
from ..configuration.preprocess import PreprocessConfiguration
from ..configuration.separator import SeparatorConfiguration
from ..detection.decision.vocabulary import FINAL_REVIEW_REASONS
from ..detection.candidate.assessment.model import (
    CandidateGateAssessment,
    SequenceProofPath,
)
from ..detection.decision.model import DecisionGateAssessment
from ..detection.candidate.model import (
    AssessedCandidate,
    CandidateAssessment,
    CandidateEvidenceModel,
)
from ..detection.candidate.plan.model import CountHypothesis
from ..detection.candidate.selection.model import (
    CountResolution,
    GeometryCluster,
    SelectionConsensus,
    SelectionResult,
)
from ..detection.geometry_resolution import GeometryResolution
from ..detection.final.model import FinalizationPlan
from ..detection.gate_checks import GateCheck, GateRequirement, GateStage
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..detection.physical.model import (
    DualLaneFrameSolution,
    ReviewOnlyContainment,
    FrameSequenceSolution,
    GeometryIdentityError,
)
from ..domain import (
    Box,
    FrameCropEnvelope,
    EvidenceState,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    SeparatorBandObservation,
)
from ..image.workspace import WorkspaceIdentity
from ..io.model import ImageProfile
from ..formats import FrameSizeMm
from ..output.model import FrameBleedPlan, OutputGeometry
from ..units import ResolutionMetadataObservation
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    runtime_facts_sha256,
)
from .read_models import typed_read_model


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
    "runtime_facts_sha256",
)


@lru_cache(maxsize=None)
def _model_hints(model: type) -> dict[str, Any]:
    return get_type_hints(model)


def _spacing_from_read_model(value: Any) -> Any:
    if not isinstance(value, dict):
        raise TypeError("spacing read model must be a mapping")
    model_fields = {field.name for field in fields(InterFrameSpacing)}
    expected = (model_fields - {"basis"}) | {
        "measurement_basis",
        "state",
        "kind",
        "reason",
        "independently_observed",
        "supports_output_protection",
    }
    hints = _model_hints(InterFrameSpacing)
    if set(value) != expected:
        raise ValueError("spacing read model fields are incomplete")
    spacing = InterFrameSpacing(
        **{
            name: _typed_value_from_read_model(value[name], hints[name])
            for name in model_fields
            if name != "basis"
        },
        basis=InterFrameSpacingBasis(value["measurement_basis"]),
    )
    if (
        value["state"] != spacing.state.value
        or value["kind"] != spacing.kind
        or value["reason"] != spacing.reason
        or value["independently_observed"] is not spacing.independently_observed
        or value["supports_output_protection"]
        is not spacing.supports_output_protection
    ):
        raise ValueError("spacing read model projections are inconsistent")
    return spacing


def _typed_value_from_read_model(value: Any, annotation: Any) -> Any:
    if annotation is Any:
        return value
    if annotation is InterFrameSpacing:
        return _spacing_from_read_model(value)
    if annotation is type(None):
        if value is not None:
            raise TypeError("expected null")
        return None
    if annotation is bool:
        if not isinstance(value, bool):
            raise TypeError("expected bool")
        return value
    if annotation is int:
        integer = _integer(value)
        if integer is None:
            raise TypeError("expected integer")
        return integer
    if annotation is float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError("expected number")
        return float(value)
    if annotation is str:
        if not isinstance(value, str):
            raise TypeError("expected string")
        return value
    if annotation is bytes:
        if not (
            isinstance(value, str)
            and value.startswith("<bytes:")
            and value.endswith(">")
            and value[7:-1].isdigit()
        ):
            raise TypeError("expected bytes read model")
        return b""
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and issubclass(annotation, str):
        if not isinstance(value, str):
            raise TypeError("expected typed string")
        return annotation(value)

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {UnionType, Union}:
        for item in arguments:
            try:
                return _typed_value_from_read_model(value, item)
            except (KeyError, TypeError, ValueError):
                continue
        raise TypeError("value does not match union")
    if origin is tuple:
        if not isinstance(value, list):
            raise TypeError("expected tuple read model")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(
                _typed_value_from_read_model(item, arguments[0])
                for item in value
            )
        if len(value) != len(arguments):
            raise ValueError("tuple read model has the wrong length")
        return tuple(
            _typed_value_from_read_model(item, item_type)
            for item, item_type in zip(value, arguments, strict=True)
        )
    if origin is list:
        if not isinstance(value, list) or len(arguments) != 1:
            raise TypeError("expected list read model")
        return [
            _typed_value_from_read_model(item, arguments[0]) for item in value
        ]
    if origin is dict:
        if not isinstance(value, dict) or len(arguments) != 2:
            raise TypeError("expected dict read model")
        key_type, value_type = arguments
        return {
            _typed_value_from_read_model(key, key_type):
            _typed_value_from_read_model(item, value_type)
            for key, item in value.items()
        }
    if is_dataclass(annotation):
        if not isinstance(value, dict):
            raise TypeError("expected dataclass read model")
        model_fields = fields(annotation)
        field_names = {field.name for field in model_fields}
        if set(value) != field_names:
            raise ValueError("dataclass read model fields are incomplete")
        hints = _model_hints(annotation)
        instance = annotation(
            **{
                field.name: _typed_value_from_read_model(
                    value[field.name],
                    hints[field.name],
                )
                for field in model_fields
                if field.init
            }
        )
        if any(
            typed_read_model(getattr(instance, field.name)) != value[field.name]
            for field in model_fields
            if not field.init
        ):
            raise ValueError("derived dataclass projection is inconsistent")
        return instance
    if isinstance(annotation, type) and isinstance(value, annotation):
        return value
    raise TypeError("unsupported typed read model")


def _typed_value_valid(value: Any, annotation: Any) -> bool:
    try:
        _typed_value_from_read_model(value, annotation)
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _separator_observation_valid(value: Any) -> bool:
    return _typed_value_valid(value, SeparatorBandObservation)


def _provisional_geometry_from_read_model(kind: str, value: Any) -> Any:
    model = {
        "sequence": FrameSequenceSolution,
        "dual_lane": DualLaneFrameSolution,
        "review_only": ReviewOnlyContainment,
    }.get(kind)
    if model is None:
        raise ValueError(f"unknown candidate geometry kind: {kind}")
    return _typed_value_from_read_model(value, model)


def _gate_check_from_read_model(value: Any) -> GateCheck:
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
        raise ValueError("gate check read model is incomplete")
    check = GateCheck(
        code=str(value["code"]),
        stage=GateStage(value["stage"]),
        state=EvidenceState(str(value["state"])),
        requirement=GateRequirement(value["requirement"]),
        final_review_reason=(
            None
            if value["final_review_reason"] is None
            else str(value["final_review_reason"])
        ),
    )
    if value["blocks"] != check.blocks:
        raise ValueError("gate check blocking projection is inconsistent")
    return check


def _sequence_proof_path_from_read_model(value: Any) -> SequenceProofPath:
    if not _typed_value_valid(value, SequenceProofPath):
        raise ValueError("sequence proof path read model is incomplete")
    return SequenceProofPath(
        code=str(value["code"]),
        state=EvidenceState(str(value["state"])),
        supporting_evidence=tuple(
            str(item) for item in value["supporting_evidence"]
        ),
    )


def candidate_gate_from_read_model(value: Any) -> CandidateGateAssessment:
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
        and isinstance(value["proof_paths"], list)
        and isinstance(value["failed_checks"], list)
        and all(isinstance(code, str) for code in value["failed_checks"])
        and isinstance(value["diagnostics"], list)
        and all(isinstance(item, str) for item in value["diagnostics"])
    ):
        raise ValueError("candidate gate read model is incomplete")
    gate = CandidateGateAssessment(
        checks=tuple(
            _gate_check_from_read_model(check) for check in value["checks"]
        ),
        proof_paths=tuple(
            _sequence_proof_path_from_read_model(path)
            for path in value["proof_paths"]
        ),
        diagnostics=tuple(str(item) for item in value["diagnostics"]),
    )
    if value["passed"] != gate.passed or value["failed_checks"] != list(
        gate.failed_checks
    ):
        raise ValueError("candidate gate projections are inconsistent")
    return gate


def decision_gate_from_read_model(value: Any) -> DecisionGateAssessment:
    expected = {"passed", "checks", "reason_inputs"}
    if not (
        isinstance(value, dict)
        and set(value) == expected
        and isinstance(value["passed"], bool)
        and isinstance(value["checks"], list)
        and isinstance(value["reason_inputs"], list)
        and all(
            isinstance(item, dict)
            and set(item) == {"check", "final_review_reason"}
            and isinstance(item["check"], str)
            and isinstance(item["final_review_reason"], str)
            for item in value["reason_inputs"]
        )
    ):
        raise ValueError("decision gate read model is incomplete")
    gate = DecisionGateAssessment(
        checks=tuple(
            _gate_check_from_read_model(check) for check in value["checks"]
        )
    )
    return gate


def _candidate_from_read_model(value: Any) -> AssessedCandidate:
    expected = {
        "geometry_kind",
        "provisional_geometry",
        "evidence_quality",
        "candidate_gate",
        "count_hypothesis",
        "evidence",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("candidate read model is incomplete")
    candidate = AssessedCandidate(
        geometry=_provisional_geometry_from_read_model(
            str(value["geometry_kind"]),
            value["provisional_geometry"],
        ),
        count_hypothesis=_typed_value_from_read_model(
            value["count_hypothesis"],
            CountHypothesis,
        ),
        assessment=CandidateAssessment(
            evidence=_typed_value_from_read_model(
                value["evidence"],
                CandidateEvidenceModel,
            ),
            gate=(
                None
                if value["candidate_gate"] is None
                else candidate_gate_from_read_model(value["candidate_gate"])
            ),
        ),
    )
    if typed_read_model(candidate.evidence_quality) != value["evidence_quality"]:
        raise ValueError("candidate evidence quality projection is inconsistent")
    return candidate


def _selection_from_read_model(value: Any) -> SelectionResult:
    expected = {
        "selected_rank",
        "consensus",
        "geometry_resolution",
        "count_resolution",
        "candidates",
        "clusters",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("selection read model is incomplete")
    if not isinstance(value["candidates"], list) or not value["candidates"]:
        raise ValueError("selection requires candidates")
    candidates = tuple(
        _candidate_from_read_model(candidate) for candidate in value["candidates"]
    )
    selected_rank = _integer(value["selected_rank"])
    if selected_rank is None or not 1 <= selected_rank <= len(candidates):
        raise ValueError("selection rank is invalid")
    cluster_fields = {"candidate_ranks", "representative_rank"}
    if not isinstance(value["clusters"], list):
        raise ValueError("selection clusters must be a list")
    clusters: list[GeometryCluster] = []
    for cluster in value["clusters"]:
        if (
            not isinstance(cluster, dict)
            or set(cluster) != cluster_fields
            or not isinstance(cluster["candidate_ranks"], list)
            or not cluster["candidate_ranks"]
        ):
            raise ValueError("geometry cluster read model is incomplete")
        ranks = tuple(_integer(rank) for rank in cluster["candidate_ranks"])
        representative_rank = _integer(cluster["representative_rank"])
        if (
            any(rank is None or not 1 <= rank <= len(candidates) for rank in ranks)
            or representative_rank is None
            or representative_rank not in ranks
        ):
            raise ValueError("geometry cluster ranks are invalid")
        valid_ranks = tuple(int(rank) for rank in ranks if rank is not None)
        cluster_candidates = tuple(
            candidates[rank - 1] for rank in valid_ranks
        )
        clusters.append(
            GeometryCluster(
                cluster_candidates,
                candidates[representative_rank - 1],
            )
        )
    return SelectionResult(
        selected=candidates[selected_rank - 1],
        ranked_candidates=candidates,
        clusters=tuple(clusters),
        consensus=_typed_value_from_read_model(
            value["consensus"],
            SelectionConsensus,
        ),
        geometry_resolution=_typed_value_from_read_model(
            value["geometry_resolution"],
            GeometryResolution,
        ),
        count_resolution=_typed_value_from_read_model(
            value["count_resolution"],
            CountResolution | None,
        ),
    )


def _decision_consistent(
    value: Any,
    errors: list[str],
) -> None:
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
    for reason in value["final_review_reasons"]:
        if reason not in FINAL_REVIEW_REASONS:
            errors.append(f"unknown_final_review_reason:{reason}")
    try:
        gate = decision_gate_from_read_model(value["gate"])
    except (KeyError, TypeError, ValueError):
        errors.append("decision_gate_incomplete")
        return
    gate_read_model = value["gate"]
    if gate_read_model["passed"] != gate.passed:
        errors.append("decision_gate_passed_mismatch")
    if gate_read_model["passed"] != (value["status"] == "approved_auto"):
        errors.append("decision_gate_status_mismatch")
    if list(gate.final_review_reasons) != value["final_review_reasons"]:
        errors.append("decision_gate_reason_mismatch")
    reason_inputs = [
        {"check": code, "final_review_reason": reason}
        for code, reason in gate.reason_inputs
    ]
    if gate_read_model["reason_inputs"] != reason_inputs:
        errors.append("decision_gate_reason_inputs_mismatch")


def finalization_plan_from_read_model(value: Any) -> FinalizationPlan:
    expected = {
        "layout",
        "image_width",
        "image_height",
        "base_geometry",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("finalization plan read model is incomplete")
    return FinalizationPlan(
        layout=_typed_value_from_read_model(value["layout"], str),
        image_width=_typed_value_from_read_model(value["image_width"], int),
        image_height=_typed_value_from_read_model(value["image_height"], int),
        base_geometry=output_geometry_from_read_model(
            value["base_geometry"]
        ),
    )


def frame_bleed_plan_from_read_model(value: Any) -> FrameBleedPlan:
    return _typed_value_from_read_model(value, FrameBleedPlan)


def output_geometry_from_read_model(value: Any) -> OutputGeometry:
    if not (
        isinstance(value, dict)
        and set(value) == {"frame_crop_envelopes", "final_boxes"}
        and isinstance(value["frame_crop_envelopes"], list)
        and isinstance(value["final_boxes"], list)
    ):
        raise ValueError("output geometry read model is incomplete")
    return OutputGeometry(
        frame_crop_envelopes=tuple(
            _typed_value_from_read_model(item, FrameCropEnvelope)
            for item in value["frame_crop_envelopes"]
        ),
        final_boxes=tuple(
            _typed_value_from_read_model(frame, Box)
            for frame in value["final_boxes"]
        ),
    )


def _output_valid(value: Any, *, geometry_resolved: bool) -> bool:
    expected = {
        "frame_bleed_plan",
        "finalization_plan",
        "final_geometry",
        "export_eligibility",
        "output_files",
        "review_copy",
        "warnings",
    }
    if not isinstance(value, dict) or set(value) != expected:
        return False
    try:
        frame_bleed_plan = frame_bleed_plan_from_read_model(
            value["frame_bleed_plan"]
        )
    except (KeyError, TypeError, ValueError):
        return False
    eligibility = value["export_eligibility"]
    expected_eligibility = {
        "frame_export_eligible": geometry_resolved,
        "reason": (
            "geometry_resolved"
            if geometry_resolved
            else "geometry_resolution_unavailable"
        ),
    }
    if eligibility != expected_eligibility:
        return False
    if geometry_resolved:
        try:
            plan = finalization_plan_from_read_model(value["finalization_plan"])
            final_geometry = output_geometry_from_read_model(
                value["final_geometry"]
            )
        except (KeyError, TypeError, ValueError):
            return False
        geometry_valid = bool(
            final_geometry.final_boxes
            and final_geometry.frame_crop_envelopes
            == plan.base_geometry.frame_crop_envelopes
            and len(final_geometry.final_boxes)
            == len(frame_bleed_plan.frame_sides)
        )
    else:
        geometry_valid = bool(
            value["finalization_plan"] is None
            and value["final_geometry"] is None
            and value["output_files"] == []
        )
    return bool(
        geometry_valid
        and isinstance(value["output_files"], list)
        and all(isinstance(path, str) for path in value["output_files"])
        and (value["review_copy"] is None or isinstance(value["review_copy"], str))
        and isinstance(value["warnings"], list)
        and all(isinstance(warning, str) for warning in value["warnings"])
    )


def _input_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {
            "profile",
            "workspace_identity",
            "resolution_metadata",
            "transform_geometry",
        }
        and _typed_value_valid(value["profile"], ImageProfile)
        and _typed_value_valid(value["workspace_identity"], WorkspaceIdentity)
        and _typed_value_valid(
            value["resolution_metadata"], ResolutionMetadataObservation
        )
        and _typed_value_valid(
            value["transform_geometry"],
            TransformGeometryEvidence,
        )
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
        "physical_layout",
        "default_count",
        "expected_separator_count",
        "allowed_partial_counts",
        "nominal_frame_size_mm",
        "frame_size_mm_options",
        "frame_aspect",
        "aspect_source",
        "complete_strip_can_be_underfilled",
    }
    measurement_fields = {
        "boundary_path",
        "preprocess",
        "separator",
        "content",
    }
    execution_fields = {"detector_kind", "candidate_plan"}
    if not isinstance(value, dict) or set(value) != top_fields:
        return False
    physical = value["physical"]
    measurement = value["measurement"]
    execution = value["execution"]
    allowed_partial_counts = (
        tuple(physical.get("allowed_partial_counts", ()))
        if isinstance(physical, dict)
        and isinstance(physical.get("allowed_partial_counts"), list)
        else ()
    )
    nominal_size = (
        physical.get("nominal_frame_size_mm", {})
        if isinstance(physical, dict)
        else {}
    )
    frame_options = (
        physical.get("frame_size_mm_options", ())
        if isinstance(physical, dict)
        else ()
    )
    default_count = (
        _integer(physical.get("default_count"))
        if isinstance(physical, dict)
        else None
    )
    return bool(
        isinstance(value["configuration_id"], str)
        and isinstance(value["format_id"], str)
        and value["configuration_id"]
        == f"detection:{value['format_id']}:{value['strip_mode']}"
        and value["strip_mode"] in {"full", "partial"}
        and isinstance(physical, dict)
        and set(physical) == physical_fields
        and physical["physical_layout"] in {"single_strip", "dual_lane"}
        and default_count is not None
        and default_count > 0
        and _integer(physical["expected_separator_count"]) is not None
        and all(
            _integer(count) is not None and count > 0
            for count in allowed_partial_counts
        )
        and allowed_partial_counts == tuple(sorted(allowed_partial_counts))
        and len(set(allowed_partial_counts)) == len(allowed_partial_counts)
        and all(count <= default_count for count in allowed_partial_counts)
        and (
            (default_count in allowed_partial_counts)
            == physical["complete_strip_can_be_underfilled"]
        )
        and _typed_value_valid(physical["nominal_frame_size_mm"], FrameSizeMm)
        and _typed_value_valid(
            physical["frame_size_mm_options"],
            tuple[FrameSizeMm, ...],
        )
        and nominal_size in frame_options
        and _typed_value_valid(physical["frame_aspect"], float)
        and float(physical["frame_aspect"])
        == float(nominal_size["width_mm"]) / float(nominal_size["height_mm"])
        and physical["aspect_source"] == "frame_size_mm"
        and isinstance(physical["complete_strip_can_be_underfilled"], bool)
        and isinstance(measurement, dict)
        and set(measurement) == measurement_fields
        and _typed_value_valid(
            measurement["boundary_path"],
            BoundaryPathParameters,
        )
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
        "implementation_fingerprint",
        "source",
        "config",
        "configuration_fingerprint",
        "workspace_identity",
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
        and isinstance(value["implementation_fingerprint"], str)
        and len(value["implementation_fingerprint"]) == 64
        and isinstance(value["configuration_fingerprint"], str)
        and len(value["configuration_fingerprint"]) == 64
        and _typed_value_valid(value["workspace_identity"], WorkspaceIdentity)
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


def _record_identities_valid(
    record: dict[str, Any],
    selection: SelectionResult,
) -> bool:
    configuration = record["configuration"]
    physical = configuration["physical"]
    signature_config = record["analysis_reuse_signature"]["config"]
    signature_source = record["analysis_reuse_signature"]["source"]
    input_profile = record["input"]["profile"]
    format_id = configuration["format_id"]
    strip_mode = configuration["strip_mode"]
    layout = signature_config["layout"]
    if strip_mode == "full" or configuration["execution"]["detector_kind"] == "review_only":
        candidate_counts = {physical["default_count"]}
    else:
        candidate_counts = set(physical["allowed_partial_counts"])
    requested_count = signature_config["requested_count"]
    plan = (
        finalization_plan_from_read_model(
            record["output"]["finalization_plan"]
        )
        if record["output"]["finalization_plan"] is not None
        else None
    )
    workspace_identity = _typed_value_from_read_model(
        record["input"]["workspace_identity"],
        WorkspaceIdentity,
    )
    frame_bleed_plan = frame_bleed_plan_from_read_model(
        record["output"]["frame_bleed_plan"]
    )
    final_geometry = (
        None
        if record["output"]["final_geometry"] is None
        else output_geometry_from_read_model(record["output"]["final_geometry"])
    )
    selected = selection.selected.geometry
    resolved = selection.geometry_resolution.supported
    frame_plan_matches_resolution = bool(
        (
            len(frame_bleed_plan.frame_sides) == selected.count
            and len(frame_bleed_plan.frame_output_bounds) == selected.count
        )
        if resolved
        else (
            not frame_bleed_plan.frame_sides
            and not frame_bleed_plan.frame_output_bounds
        )
    )
    output_identity_valid = bool(
        (plan is None) == (not resolved)
        and (final_geometry is None) == (not resolved)
        and frame_plan_matches_resolution
        and frame_bleed_plan.user_bleed.long_axis
        == signature_config["bleed_x"]
        and frame_bleed_plan.user_bleed.short_axis
        == signature_config["bleed_y"]
    )
    if plan is not None and final_geometry is not None:
        output_identity_valid = bool(
            output_identity_valid
            and plan.layout == selected.layout
            and plan.image_width == workspace_identity.extent.width
            and plan.image_height == workspace_identity.extent.height
            and len(plan.base_geometry.frame_crop_envelopes) == selected.count
            and final_geometry.frame_crop_envelopes
            == plan.base_geometry.frame_crop_envelopes
        )
    return bool(
        signature_config["format_id"] == format_id
        and signature_config["strip_mode"] == strip_mode
        and signature_source["name"] == Path(record["source"]).name
        and record["analysis_reuse_signature"]["workspace_identity"]
        == record["input"]["workspace_identity"]
        and all(
            signature_source[name] == input_profile[name]
            for name in ("shape", "dtype", "axes", "photometric")
        )
        and all(
            candidate.geometry.format_id == format_id
            and candidate.geometry.strip_mode == strip_mode
            and candidate.geometry.layout == layout
            and candidate.geometry.count in candidate_counts
            for candidate in selection.ranked_candidates
        )
        and (requested_count is None or selected.count == requested_count)
        and output_identity_valid
        and record["output"]["export_eligibility"]
        == {
            "frame_export_eligible": selection.geometry_resolution.supported,
            "reason": (
                "geometry_resolved"
                if selection.geometry_resolution.supported
                else "geometry_resolution_unavailable"
            ),
        }
    )


_PROVENANCE_READ_MODEL_FIELDS = (
    "root_measurement",
    "observation_id",
    "dependencies",
    "description",
    "boundary_anchors",
)
_PROVENANCE_READ_MODEL_FIELD_SET = frozenset(_PROVENANCE_READ_MODEL_FIELDS)


def _observation_identity_collision(value: Any) -> bool:
    identities: dict[str, tuple[Any, ...]] = {}

    def visit(item: Any) -> bool:
        if isinstance(item, dict):
            if item.keys() >= _PROVENANCE_READ_MODEL_FIELD_SET:
                observation_id = item.get("observation_id")
                if isinstance(observation_id, str):
                    signature = tuple(
                        item[field]
                        for field in _PROVENANCE_READ_MODEL_FIELDS
                    )
                    existing = identities.get(observation_id)
                    if existing is not None and existing != signature:
                        return True
                    identities[observation_id] = signature
            return any(visit(child) for child in item.values())
        if isinstance(item, list):
            return any(visit(child) for child in item)
        return False

    return visit(value)


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
    if _observation_identity_collision(record):
        errors.append("observation_identity_collision")
    input_detail = record["input"]
    input_valid = _input_valid(input_detail)
    if not input_valid:
        errors.append("input_incomplete")
    configuration = record["configuration"]
    configuration_valid = _configuration_valid(configuration)
    if not configuration_valid:
        errors.append("configuration_incomplete")
    selection_result: SelectionResult | None = None
    try:
        selection_result = _selection_from_read_model(record["selection"])
    except GeometryIdentityError:
        errors.append("record_identity_mismatch")
    except (KeyError, TypeError, ValueError):
        candidates = (
            record["selection"].get("candidates", [])
            if isinstance(record["selection"], dict)
            else []
        )
        invalid_observation = any(
            not _separator_observation_valid(observation)
            for candidate in candidates
            if isinstance(candidate, dict)
            for observation in candidate.get("provisional_geometry", {}).get(
                "separator_observations",
                [],
            )
        )
        errors.append(
            "separator_observation_invalid"
            if invalid_observation
            else "selection_incomplete"
        )
    geometry_resolved = bool(
        selection_result is not None
        and selection_result.geometry_resolution.supported
    )
    output_valid = _output_valid(
        record["output"],
        geometry_resolved=geometry_resolved,
    )
    if not output_valid:
        errors.append("output_incomplete")
    _decision_consistent(record["decision"], errors)
    if not _analysis_reuse_signature_valid(record["analysis_reuse_signature"]):
        errors.append("analysis_reuse_signature_invalid")
    elif (
        selection_result is not None
        and configuration_valid
        and output_valid
    ):
        try:
            identities_valid = _record_identities_valid(
                record,
                selection_result,
            )
        except (KeyError, TypeError, ValueError):
            identities_valid = False
        if not identities_valid:
            errors.append("record_identity_mismatch")
    if not (
        isinstance(record["analysis_reuse"], dict)
        and set(record["analysis_reuse"]) == {"used"}
        and isinstance(record["analysis_reuse"]["used"], bool)
    ):
        errors.append("analysis_reuse_invalid")
    fingerprint = record["runtime_facts_sha256"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        errors.append("runtime_facts_fingerprint_invalid")
    else:
        try:
            expected_fingerprint = runtime_facts_sha256(record)
        except (KeyError, TypeError, ValueError):
            expected_fingerprint = None
        if fingerprint != expected_fingerprint:
            errors.append("runtime_facts_fingerprint_mismatch")
    return errors


def validate_current_report_record(record: dict[str, Any]) -> None:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError("invalid current report record: " + ", ".join(errors))
