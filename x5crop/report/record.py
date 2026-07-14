from __future__ import annotations

from ..app_info import VERSION
from ..detection.final.model import FinalDetection, FinalizationPlan
from ..detection.candidate.selection.model import SelectionResult
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..image.workspace import WorkspaceIdentity
from ..output.model import OutputGeometry
from ..units import ResolutionMetadataObservation
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION, bind_runtime_facts
from .read_models import (
    decision_gate_detail,
    frame_bleed_plan_read_model,
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
    workspace_identity: WorkspaceIdentity,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    configuration: dict,
    resolution_metadata: ResolutionMetadataObservation,
    transform_geometry: TransformGeometryEvidence,
    analysis_reuse_signature: dict,
) -> dict:
    output_geometry = detection.output_geometry
    record = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": str(source),
        "input": {
            "profile": dict(profile),
            "workspace_identity": typed_read_model(workspace_identity),
            "resolution_metadata": typed_read_model(resolution_metadata),
            "transform_geometry": typed_read_model(transform_geometry),
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
        "analysis_reuse_signature": dict(analysis_reuse_signature),
        "analysis_reuse": {"used": False},
    }
    return bind_runtime_facts(record)
