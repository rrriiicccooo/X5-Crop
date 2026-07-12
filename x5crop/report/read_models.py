from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..detection.candidate.model import AssessedCandidate
from ..detection.decision.model import FinalDetection


def typed_read_model(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: typed_read_model(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): typed_read_model(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [typed_read_model(item) for item in value]
    return value


def gate_check_read_model(check: Any) -> dict[str, Any]:
    return {
        "code": check.code,
        "stage": check.stage,
        "state": check.state.value,
        "consequence": check.consequence,
        "final_review_reason": check.final_review_reason,
        "blocks": bool(check.blocks),
    }


def candidate_gate_read_model(candidate: AssessedCandidate) -> dict[str, Any]:
    gate = candidate.assessment.gate
    return {
        "passed": bool(gate.passed),
        "checks": [gate_check_read_model(check) for check in gate.checks],
        "proof_paths": typed_read_model(gate.proof_paths),
        "failed_checks": list(gate.failed_checks),
        "diagnostics": list(gate.diagnostics),
    }


def candidate_evidence_read_model(candidate: AssessedCandidate) -> dict[str, Any]:
    return typed_read_model(candidate.assessment.evidence)


def candidate_read_model(candidate: AssessedCandidate) -> dict[str, Any]:
    geometry = candidate.geometry
    return {
        "format_id": geometry.format_id,
        "strip_mode": geometry.strip_mode,
        "count": int(geometry.count),
        "source": geometry.source,
        "sequence_hypothesis": geometry.sequence_hypothesis_name,
        "sequence_strategy": geometry.sequence_hypothesis_strategy,
        "holder_span": typed_read_model(geometry.holder_span),
        "visible_sequence_span": typed_read_model(geometry.visible_sequence_span),
        "crop_envelope": typed_read_model(geometry.crop_envelope),
        "boundary_observations": typed_read_model(geometry.boundary_observations),
        "separator_observations": typed_read_model(geometry.separator_observations),
        "separator_assignments": typed_read_model(geometry.separator_assignments),
        "frame_boundaries": typed_read_model(geometry.frame_boundaries),
        "frame_dimension_prior": typed_read_model(
            geometry.frame_dimension_prior
        ),
        "frame_boxes": typed_read_model(geometry.frames),
        "lane_boxes": typed_read_model(geometry.lane_boxes),
        "lane_crop_envelopes": typed_read_model(geometry.lane_crop_envelopes),
        "evidence_quality": typed_read_model(candidate.assessment.quality),
        "candidate_gate": candidate_gate_read_model(candidate),
        "count_hypothesis": typed_read_model(candidate.count_hypothesis),
        "evidence": candidate_evidence_read_model(candidate),
        "diagnostics": list(candidate.assessment.diagnostics),
    }


def candidate_table(detection: FinalDetection) -> list[dict[str, Any]]:
    selection = detection.require_selection()
    return [
        {
            "rank": index,
            "selected": candidate is selection.selected,
            **candidate_read_model(candidate),
        }
        for index, candidate in enumerate(selection.ranked_candidates, start=1)
    ]


def selection_read_model(detection: FinalDetection) -> dict[str, Any]:
    selection = detection.require_selection()
    return {
        "consensus": selection.consensus,
        "geometry_resolution": typed_read_model(selection.geometry_resolution),
        "count_resolution": typed_read_model(selection.count_resolution),
        "clusters": [
            {
                "candidate_count": len(cluster.candidates),
                "representative": candidate_read_model(cluster.representative),
            }
            for cluster in selection.clusters
        ],
    }


def decision_gate_detail(detection: FinalDetection) -> dict[str, Any]:
    gate = detection.decision_gate
    return {
        "passed": bool(gate.passed),
        "checks": [gate_check_read_model(check) for check in gate.checks],
        "reason_inputs": [
            {"check": check, "final_review_reason": reason}
            for check, reason in gate.reason_inputs
        ],
    }


def scan_calibration_read_model(calibration: Any) -> dict[str, Any]:
    return typed_read_model(calibration)


def output_bleed_read_model(plan: Any) -> dict[str, Any]:
    return typed_read_model(plan)
