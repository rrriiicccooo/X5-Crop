from __future__ import annotations

from ..app_info import VERSION
from ..detection.decision.model import FinalDetection
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..utils import json_safe
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from .read_models import (
    candidate_evidence_read_model,
    candidate_gate_read_model,
    candidate_table,
    decision_gate_detail,
    output_bleed_read_model,
    scan_calibration_read_model,
    selection_read_model,
    typed_read_model,
)


def _transform_detail(transform: TransformGeometryEvidence) -> dict[str, object]:
    return {
        "state": transform.state.value,
        "applied": bool(transform.applied),
        "estimated_angle_degrees": float(transform.estimated_angle_degrees),
        "applied_angle_degrees": float(transform.applied_angle_degrees),
        "reason": transform.reason,
        "span_px": transform.span_px,
        "span_threshold_px": transform.span_threshold_px,
    }


def report_record_for_final_detection(
    detection: FinalDetection,
    *,
    source: str,
    profile: dict,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    policy_id: str,
    runtime_policy: dict,
    transform_geometry: TransformGeometryEvidence,
    analysis_reuse_signature: dict,
) -> dict:
    selection = detection.require_selection()
    selected_evidence = selection.selected.assessment.evidence
    selected_candidate = selection.selected
    record = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": str(source),
        "profile": dict(profile),
        "format_id": detection.format_id,
        "strip_mode": detection.strip_mode,
        "layout": detection.layout,
        "count": int(detection.count),
        "count_resolution": (
            None
            if selection.count_resolution is None
            else typed_read_model(selection.count_resolution)
        ),
        "holder_span": typed_read_model(selected_candidate.geometry.holder_span),
        "visible_sequence_span": typed_read_model(
            selected_candidate.geometry.visible_sequence_span
        ),
        "crop_envelope": typed_read_model(
            selected_candidate.geometry.crop_envelope
        ),
        "boundary_observations": typed_read_model(
            selected_candidate.geometry.boundary_observations
        ),
        "strip_completeness": typed_read_model(
            selected_evidence.holder_occupancy.strip_completeness
        ),
        "holder_occupancy": typed_read_model(selected_evidence.holder_occupancy),
        "status": detection.status,
        "final_review_reasons": list(detection.final_review_reasons),
        "decision_geometry": {
            "crop_envelope": typed_read_model(
                detection.decision_geometry.crop_envelope.box
            ),
            "frame_boxes": typed_read_model(detection.decision_geometry.frames),
        },
        "output_geometry": {
            "crop_envelope": typed_read_model(
                detection.output_geometry.crop_envelope.box
            ),
            "frame_boxes": typed_read_model(detection.output_geometry.frames),
        },
        "separator_observations": typed_read_model(
            detection.separator_observations
        ),
        "separator_assignments": typed_read_model(
            detection.separator_assignments
        ),
        "frame_boundaries": typed_read_model(detection.frame_boundaries),
        "holder_occlusion": typed_read_model(
            selected_evidence.frame_sequence.holder_occlusion
        ),
        "inter_frame_spacing": typed_read_model(
            selected_evidence.frame_sequence.spacings
        ),
        "sequence_conservation": typed_read_model(
            selected_evidence.frame_sequence.conservation
        ),
        "candidate_table": candidate_table(detection),
        "selection": selection_read_model(detection),
        "policy": dict(runtime_policy),
        "policy_id": policy_id,
        "evidence_summary": {
            **candidate_evidence_read_model(selected_candidate),
        },
        "candidate_gate": candidate_gate_read_model(selected_candidate),
        "decision_gate": decision_gate_detail(detection),
        "scan_calibration": scan_calibration_read_model(
            detection.scan_calibration
        ),
        "analysis_reuse_signature": dict(analysis_reuse_signature),
        "analysis_reuse": {"used": False},
        "schema_validation": [],
        "diagnostics": {
            "transform_geometry": _transform_detail(transform_geometry),
            "detection": list(detection.diagnostics),
        },
        "output": {
            "bleed_plan": output_bleed_read_model(
                detection.output_bleed_plan
            ),
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
    }
    return json_safe(record)
