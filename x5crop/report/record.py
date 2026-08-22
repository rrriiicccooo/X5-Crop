"""Build compact production reports with optional development facts."""

from __future__ import annotations

from ..app_info import VERSION
from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from .development import development_report_facts
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from .read_models import gate_read_model, typed_read_model
from .summary import measurement_summary, photo_geometry_summary


def capture_workspace_report_facts(
    detection: FinalDetection,
    workspace: DetectionWorkspace,
    *,
    development_detail: bool,
) -> tuple[dict, dict | None]:
    """Freeze report facts that require the detection workspace."""

    return (
        measurement_summary(detection, workspace),
        (
            development_report_facts(detection, workspace)
            if development_detail
            else None
        ),
    )


def report_record_for_final_detection(
    detection: FinalDetection,
    *,
    source: str,
    profile: dict,
    measurement: dict,
    development: dict | None,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    configuration: dict,
    runtime_identity: dict,
    frame_export_requested: bool,
) -> dict:
    export_performed = bool(output_files)
    record = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "detail_level": (
            "development" if development is not None else "production"
        ),
        "script_version": VERSION,
        "source": str(source),
        "input": {"profile": dict(profile)},
        "configuration": dict(configuration),
        "measurement": dict(measurement),
        "photo_geometry": photo_geometry_summary(detection),
        "candidate_gate": gate_read_model(detection.candidate.gate),
        "decision": {
            "status": detection.decision.status,
            "final_review_reasons": list(
                detection.decision.final_review_reasons
            ),
            "gate": gate_read_model(detection.decision),
        },
        "output": {
            "finalization": {
                "frame_export_eligible": detection.frame_export_eligible,
                "frame_export_requested": frame_export_requested,
                "frame_export_performed": export_performed,
                "official_tiff_count": len(output_files),
                "reason": detection.frame_export_reason,
                "deskew_assessment": typed_read_model(
                    detection.deskew_assessment
                ),
                "output_footprints": typed_read_model(
                    detection.output_footprints
                ),
                "final_boxes": typed_read_model(detection.final_boxes),
            },
            "tiff_fidelity": {
                "validation": (
                    "header_validated" if output_files else "not_created"
                ),
            },
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
        "runtime_identity": dict(runtime_identity),
        "development": development,
    }
    return record
