from __future__ import annotations

from ..app_info import VERSION
from ..detection.decision.model import FinalDetection
from ..detection.candidate.selection.model import SelectionResult
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..output.model import OutputGeometry
from ..utils import json_safe
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from .read_models import (
    decision_gate_detail,
    frame_bleed_plan_read_model,
    scan_calibration_read_model,
    selection_read_model,
    typed_read_model,
)


def _transform_read_model(
    transform: TransformGeometryEvidence,
) -> dict[str, object]:
    return {
        "state": transform.state.value,
        "applied": bool(transform.applied),
        "estimated_angle_degrees": float(transform.estimated_angle_degrees),
        "applied_angle_degrees": float(transform.applied_angle_degrees),
        "reason": transform.reason,
        "span_px": (
            None if transform.span_px is None else float(transform.span_px)
        ),
        "span_threshold_px": (
            None
            if transform.span_threshold_px is None
            else float(transform.span_threshold_px)
        ),
    }


def _geometry_read_model(geometry: OutputGeometry) -> dict[str, object]:
    return {
        "crop_envelope": typed_read_model(geometry.crop_envelope.box),
        "frame_boxes": typed_read_model(geometry.frames),
    }


def report_record_for_final_detection(
    detection: FinalDetection,
    selection: SelectionResult,
    *,
    source: str,
    profile: dict,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    configuration: dict,
    transform_geometry: TransformGeometryEvidence,
    analysis_reuse_signature: dict,
) -> dict:
    record = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": str(source),
        "input": {
            "profile": dict(profile),
            "scan_calibration": scan_calibration_read_model(
                detection.scan_calibration
            ),
        },
        "configuration": dict(configuration),
        "selection": selection_read_model(selection),
        "decision": {
            "status": detection.status,
            "final_review_reasons": list(detection.final_review_reasons),
            "gate": decision_gate_detail(detection),
        },
        "output": {
            "decision_geometry": _geometry_read_model(
                detection.decision_geometry
            ),
            "final_geometry": _geometry_read_model(detection.output_geometry),
            "frame_bleed_plan": frame_bleed_plan_read_model(
                detection.frame_bleed_plan
            ),
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
        "analysis_reuse_signature": dict(analysis_reuse_signature),
        "analysis_reuse": {"used": False},
        "schema_validation": [],
        "diagnostics": {
            "transform_geometry": _transform_read_model(transform_geometry),
            "detection": list(detection.diagnostics),
        },
    }
    return json_safe(record)
