from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..detection.candidate.model import AssessedCandidate
from ..detection.decision.model import DecisionGateAssessment
from ..detection.evidence.scan_canvas import ScanCanvasEvidence
from ..detection.gate_checks import GateCheck
from ..detection.candidate.selection.model import SelectionResult
from ..detection.physical.model import (
    DualLaneFrameSolution,
    ReviewOnlyContainment,
    FrameSequenceSolution,
)
from ..domain import InterFrameSpacing
from ..output.model import FrameBleedPlan


MILLIMETERS_PER_INCH = 25.4


def typed_read_model(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, InterFrameSpacing):
        return {
            "measurement_basis": value.basis.value,
            "boundary": typed_read_model(value.boundary),
            "state": value.state.value,
            "kind": value.kind,
            "signed_width_px": typed_read_model(value.signed_width_px),
            "provenance": typed_read_model(value.provenance),
            "reason": value.reason,
            "independently_observed": bool(value.independently_observed),
            "supports_output_protection": bool(
                value.supports_output_protection
            ),
        }
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


def scan_canvas_evidence_read_model(
    evidence: ScanCanvasEvidence,
) -> dict[str, Any]:
    detail = typed_read_model(evidence)
    scale = evidence.pixel_scale
    if scale is not None:
        detail["effective_ppi"] = {
            "long_axis": (
                scale.long_axis_px_per_mm * MILLIMETERS_PER_INCH
            ),
            "short_axis": (
                scale.short_axis_px_per_mm * MILLIMETERS_PER_INCH
            ),
        }
    return detail


def gate_check_read_model(check: GateCheck) -> dict[str, Any]:
    return {
        "code": check.code,
        "stage": typed_read_model(check.stage),
        "state": check.state.value,
        "requirement": check.requirement.value,
        "final_review_reason": check.final_review_reason,
        "blocks": bool(check.blocks),
    }


def candidate_gate_read_model(
    candidate: AssessedCandidate,
) -> dict[str, Any] | None:
    gate = candidate.assessment.gate
    if gate is None:
        return None
    return {
        "passed": bool(gate.passed),
        "checks": [gate_check_read_model(check) for check in gate.checks],
        "proof_paths": typed_read_model(gate.proof_paths),
        "failed_checks": list(gate.failed_checks),
        "diagnostics": list(gate.diagnostics),
    }


def candidate_read_model(candidate: AssessedCandidate) -> dict[str, Any]:
    geometry = candidate.geometry
    if isinstance(geometry, FrameSequenceSolution):
        geometry_kind = "sequence"
    elif isinstance(geometry, DualLaneFrameSolution):
        geometry_kind = "dual_lane"
    elif isinstance(geometry, ReviewOnlyContainment):
        geometry_kind = "review_only"
    else:
        raise TypeError(f"unsupported candidate geometry: {type(geometry).__name__}")
    return {
        "geometry_kind": geometry_kind,
        "provisional_geometry": typed_read_model(geometry),
        "evidence_quality": typed_read_model(candidate.evidence_quality),
        "candidate_gate": candidate_gate_read_model(candidate),
        "count_hypothesis": typed_read_model(candidate.count_hypothesis),
        "evidence": typed_read_model(candidate.assessment.evidence),
    }


def selection_read_model(selection: SelectionResult) -> dict[str, Any]:
    ranks = {
        id(candidate): index
        for index, candidate in enumerate(selection.ranked_candidates, start=1)
    }
    return {
        "selected_rank": ranks[id(selection.selected)],
        "consensus": typed_read_model(selection.consensus),
        "geometry_resolution": typed_read_model(selection.geometry_resolution),
        "count_resolution": typed_read_model(selection.count_resolution),
        "candidates": [
            candidate_read_model(candidate)
            for candidate in selection.ranked_candidates
        ],
        "clusters": [
            {
                "candidate_ranks": [
                    ranks[id(candidate)] for candidate in cluster.candidates
                ],
                "representative_rank": ranks[id(cluster.representative)],
            }
            for cluster in selection.clusters
        ],
    }


def decision_gate_detail(gate: DecisionGateAssessment) -> dict[str, Any]:
    return {
        "passed": bool(gate.passed),
        "checks": [gate_check_read_model(check) for check in gate.checks],
        "reason_inputs": [
            {"check": check, "final_review_reason": reason}
            for check, reason in gate.reason_inputs
        ],
    }


def frame_bleed_plan_read_model(plan: FrameBleedPlan) -> dict[str, Any]:
    return {
        "user_bleed": typed_read_model(plan.user_bleed),
        "frame_output_bounds": typed_read_model(plan.frame_output_bounds),
        "frame_sides": typed_read_model(plan.frame_sides),
        "overlap_protection": typed_read_model(plan.overlap_protection),
        "unresolved_overlap_boundaries": typed_read_model(
            plan.unresolved_overlap_boundaries
        ),
        "feasible": bool(plan.feasible),
        "reason": str(plan.reason),
    }
