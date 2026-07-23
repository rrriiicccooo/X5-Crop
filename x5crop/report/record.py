from __future__ import annotations

from ..app_info import VERSION
from ..detection.final.model import FinalDetection, FinalizationPlan
from ..detection.candidate.selection.model import SelectionResult
from ..detection.workspace import DetectionWorkspace
from ..output.model import OutputGeometry
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION, bind_runtime_facts
from .read_models import (
    decision_gate_detail,
    frame_bleed_plan_read_model,
    scan_canvas_evidence_read_model,
    selection_read_model,
    typed_read_model,
)


def _geometry_read_model(geometry: OutputGeometry) -> dict[str, object]:
    return {
        "frame_crop_envelopes": typed_read_model(
            geometry.frame_crop_envelopes
        ),
        "final_boxes": typed_read_model(geometry.final_boxes),
    }


def _finalization_plan_read_model(
    plan: FinalizationPlan | None,
) -> dict[str, object] | None:
    if plan is None:
        return None
    return {
        "layout": plan.layout,
        "image_width": int(plan.image_width),
        "image_height": int(plan.image_height),
        "base_geometry": _geometry_read_model(plan.base_geometry),
    }


def report_record_for_final_detection(
    detection: FinalDetection,
    selection: SelectionResult,
    *,
    source: str,
    profile: dict,
    workspace: DetectionWorkspace,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    configuration: dict,
    analysis_identity: dict,
) -> dict:
    output_geometry = detection.output_geometry
    record = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": str(source),
        "input": {
            "profile": dict(profile),
            "workspace_identity": typed_read_model(workspace.identity),
            "scan_canvas_evidence": scan_canvas_evidence_read_model(
                workspace.scan_canvas_evidence
            ),
            "transform_geometry": typed_read_model(workspace.transform_geometry),
            "source_photo_edge_pairs": typed_read_model(
                workspace.source_photo_edge_pairs
            ),
            "mapped_photo_edge_pairs": typed_read_model(
                workspace.mapped_photo_edge_pairs
            ),
            "shared_short_axes": typed_read_model(workspace.shared_short_axes),
            "source_lane_divider": typed_read_model(workspace.source_lane_divider),
            "lane_divider": typed_read_model(workspace.lane_divider),
        },
        "configuration": dict(configuration),
        "selection": selection_read_model(selection),
        "decision": {
            "status": detection.decision.status,
            "final_review_reasons": list(
                detection.decision.final_review_reasons
            ),
            "gate": decision_gate_detail(detection.decision),
        },
        "output": {
            "frame_bleed_plan": frame_bleed_plan_read_model(
                detection.frame_bleed_plan
            ),
            "finalization_plan": _finalization_plan_read_model(
                detection.finalization_plan
            ),
            "final_geometry": (
                None
                if output_geometry is None
                else _geometry_read_model(output_geometry)
            ),
            "export_eligibility": {
                "frame_export_eligible": detection.frame_export_eligible,
                "reason": detection.frame_export_reason,
            },
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
        "analysis_identity": dict(analysis_identity),
    }
    return bind_runtime_facts(record)
