from __future__ import annotations

from ..app_info import VERSION
from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    bind_core_facts,
)
from .read_models import gate_read_model, typed_read_model


def _lane_read_model(lane: object) -> dict[str, object]:
    content = lane.content
    return {
        "domain": typed_read_model(lane.domain),
        "scan_canvas": typed_read_model(lane.scan_canvas),
        "axis_scale_intervals": typed_read_model(lane.scales),
        "content": {
            "state": content.state.value,
            "intensity_threshold": content.intensity_threshold,
            "texture_threshold": content.texture_threshold,
            "statistics": typed_read_model(content.statistics),
            "component_count": len(content.components),
            "component_examples_truncated": len(content.components) > 64,
            "component_examples": [
                {
                    "component_id": component.component_id,
                    "footprint": typed_read_model(component.footprint),
                    "row_run_count": component.row_run_count,
                    "positive_cells": component.positive_cells,
                    "censored": component.censored,
                    "provenance": typed_read_model(component.provenance),
                }
                for component in content.components[:64]
            ],
            "provenance": typed_read_model(content.provenance),
        },
    }


def report_record_for_final_detection(
    detection: FinalDetection,
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
    core = detection.source_core
    record = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": str(source),
        "input": {
            "profile": dict(profile),
            "workspace_identity": typed_read_model(workspace.identity),
        },
        "configuration": dict(configuration),
        "source_core": {
            "lanes": [_lane_read_model(lane) for lane in core.lanes],
            "scan_canvas_state": core.scan_canvas_state.value,
            "content_state": core.content_state.value,
            "frame_grid": typed_read_model(core.grid),
            "photo_containment": typed_read_model(core.containment),
            "output_protection_authority": typed_read_model(
                core.protection_authority
            ),
            "visual_deskew_outcome": core.visual_deskew_outcome.value,
            "incomplete_reasons": list(core.incomplete_reasons),
        },
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
                "reason": detection.frame_export_reason,
                "final_boxes": typed_read_model(detection.final_boxes),
            },
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
        "analysis_identity": dict(analysis_identity),
    }
    return bind_core_facts(record)
