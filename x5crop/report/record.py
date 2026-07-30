from __future__ import annotations

from ..app_info import VERSION
from ..configuration.grid import CALIBRATION_RECEIPT_ID
from ..detection.final.model import FinalDetection
from ..detection.grid.model import (
    K_MAX,
    O_MAX,
    P_MAX,
)
from ..detection.workspace import DetectionWorkspace
from .identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    bind_core_facts,
)
from .read_models import gate_read_model, typed_read_model


def _lane_measurement_read_model(
    lane: object,
    separator: object,
) -> dict[str, object]:
    content = lane.content
    return {
        "domain": typed_read_model(lane.domain),
        "scan_canvas": typed_read_model(lane.scan_canvas),
        "axis_scale_intervals": typed_read_model(
            lane.scan_canvas.axis_scales
        ),
        "axis_scale_authority": "ScanCanvasEvidence",
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
        "separator": {
            "state": separator.state.value,
            "support_threshold": separator.support_threshold,
            "line_observation_count": len(separator.lines),
            "line_examples_truncated": len(separator.lines) > 64,
            "line_examples": typed_read_model(separator.lines[:64]),
            "statistics": typed_read_model(separator.statistics),
            "provenance": typed_read_model(separator.provenance),
            "owner": "x5crop.detection.evidence.separator",
            "positive_content_dependency": False,
        },
    }


def _selection_read_model(selection: object) -> dict[str, object]:
    return {
        "lane_id": selection.lane_id,
        "proposal_classes": typed_read_model(
            selection.proposal_classes
        ),
        "selected_proposal_id": (
            None
            if selection.selected_proposal is None
            else selection.selected_proposal.proposal_id
        ),
        "grid_search_coverage_state": (
            selection.grid_search_coverage_state.value
        ),
        "slot_ordinal_state": selection.ordinal_state.value,
        "slot_ownership_state": selection.ownership_state.value,
        "selection_reason": selection.selection_reason,
        "omitted_outcome_risk": selection.omitted_outcome_risk,
        "omission_summaries": typed_read_model(
            selection.omission_summaries
        ),
        "work_by_component": typed_read_model(
            selection.work_by_component
        ),
        "separator_work_by_component": typed_read_model(
            selection.separator_work_by_component
        ),
    }


def _work_totals(detection: FinalDetection) -> dict[str, object]:
    work = tuple(
        item
        for selection in detection.candidate.lane_selections
        for item in selection.work_by_component
    )
    lane_components = {
        (item.lane_id, item.component_id) for item in work
    }
    separator_work = tuple(
        item
        for selection in detection.candidate.lane_selections
        for item in selection.separator_work_by_component
    )
    return {
        "limits": {
            "P_MAX_per_lane_component": P_MAX,
            "O_MAX_per_internal_corridor_observed": O_MAX,
            "K_MAX_per_internal_corridor_total": K_MAX,
            "count_12_state_upper_per_lane_component": 198,
            "count_12_transition_upper_per_lane_component": 558,
        },
        "lane_component_count": len(lane_components),
        "lane_component_evaluations": len(work),
        "seed_count": sum(item.seed_count for item in work),
        "candidate_builds": sum(item.candidate_builds for item in work),
        "observed_candidate_count": sum(
            item.observed_candidate_count for item in work
        ),
        "model_candidate_count": sum(
            item.model_candidate_count for item in work
        ),
        "dp_states": sum(item.dp_states for item in work),
        "dp_transitions": sum(item.dp_transitions for item in work),
        "state_upper": sum(item.state_upper for item in work),
        "transition_upper": sum(item.transition_upper for item in work),
        "retained_proposal_count": sum(
            item.retained_proposal_count for item in work
        ),
        "separator_raw_line_count": sum(
            item.raw_line_count for item in separator_work
        ),
        "separator_pair_query_count": sum(
            item.pair_query_count for item in separator_work
        ),
        "separator_compatible_pair_count": sum(
            item.compatible_pair_count for item in separator_work
        ),
        "separator_retained_band_count": sum(
            item.retained_band_count for item in separator_work
        ),
        "separator_truncated_pair_count": sum(
            item.truncated_pair_count for item in separator_work
        ),
        "search_incomplete": any(item.search_incomplete for item in work),
        "budget_exhausted": any(item.budget_exhausted for item in work),
        "omitted_outcome_risk": any(
            item.omitted_outcome_risk for item in work
        ),
        "omission_scope_count": sum(
            len(item.omission_summaries) for item in work
        ),
        "omitted_alternative_count": sum(
            summary.omitted_count
            for item in work
            for summary in item.omission_summaries
        ),
        "absorbed_omitted_alternative_count": sum(
            summary.absorbed_count
            for item in work
            for summary in item.omission_summaries
        ),
        "unresolved_omitted_outcome_count": sum(
            summary.unresolved_outcome_count
            for item in work
            for summary in item.omission_summaries
        ),
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
    diagnostics = bool(
        analysis_identity["runtime_configuration"]["diagnostics"]
    )
    export_performed = bool(output_files)
    selected_profile_id = (
        None
        if not core.lanes
        else core.lanes[0].scan_canvas.selected_profile.profile_id
    )
    resolved_slots = detection.resolved_output_slots
    output_slot_count = detection.output_slot_count
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
        "measurement": {
            "lanes": [
                _lane_measurement_read_model(lane, separator)
                for lane, separator in zip(
                    core.lanes,
                    workspace.separator_fields,
                    strict=True,
                )
            ],
            "scan_canvas_state": core.scan_canvas_state.value,
            "source_content_state": core.content_state.value,
            "incomplete_reasons": list(core.incomplete_reasons),
        },
        "grid_selection": {
            "calibration_receipt_id": CALIBRATION_RECEIPT_ID,
            "prior_authority": "search_only",
            "confirmed_geometry_runtime_observation": False,
            "selected_scan_canvas_profile_id": selected_profile_id,
            "resolved_output_slots": typed_read_model(resolved_slots),
            "output_slot_count": output_slot_count,
            "slot_identities": typed_read_model(
                detection.output_slot_identities
            ),
            "lanes": [
                _selection_read_model(selection)
                for selection in detection.candidate.lane_selections
            ],
            "work_totals": _work_totals(detection),
        },
        "candidate_gate": gate_read_model(detection.candidate.gate),
        "decision": {
            "status": detection.decision.status,
            "final_review_reasons": list(
                detection.decision.final_review_reasons
            ),
            "reason_inputs": typed_read_model(
                detection.decision.reason_inputs
            ),
            "gate": gate_read_model(detection.decision),
        },
        "output": {
            "finalization": {
                "frame_export_eligible": detection.frame_export_eligible,
                "frame_export_requested": not diagnostics,
                "frame_export_performed": export_performed,
                "reason": (
                    "diagnostics_read_only"
                    if detection.frame_export_eligible and diagnostics
                    else detection.frame_export_reason
                ),
                "resolved_output_slots": typed_read_model(resolved_slots),
                "output_slot_count": output_slot_count,
                "slot_identities": typed_read_model(
                    detection.output_slot_identities
                ),
                "transform_assessment": typed_read_model(
                    detection.transform_assessment
                ),
                "protected_envelopes": typed_read_model(
                    detection.protected_envelopes
                ),
                "final_boxes": typed_read_model(detection.final_boxes),
                "post_decision_mutation": False,
            },
            "tiff_fidelity": {
                "source_sample_count_per_roi": 1,
                "write_readback_validated": bool(output_files),
                "preserved_properties": [
                    "dtype",
                    "axes",
                    "channels",
                    "icc_color_space",
                    "resolution",
                    "metadata",
                    "lossless_compression_none_or_lzw",
                ],
                "success_receipt": (
                    "validated"
                    if export_performed
                    else "not_requested_diagnostics"
                    if detection.frame_export_eligible and diagnostics
                    else "not_created"
                ),
            },
            "output_files": list(output_files),
            "review_copy": review_copy,
            "warnings": list(warnings),
        },
        "analysis_identity": dict(analysis_identity),
    }
    return bind_core_facts(record)
