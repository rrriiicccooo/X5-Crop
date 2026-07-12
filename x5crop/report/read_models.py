from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..detection.candidate.model import AssessedCandidate
from ..detection.decision.model import FinalDetection
from ..detection.physical.model import (
    DualLaneSolution,
    ReviewOnlyGeometry,
    SequenceSolution,
)
from ..detection.physical.spacing import (
    ObservedSpacingEvidence,
    SpacingHypothesis,
)


def typed_read_model(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (ObservedSpacingEvidence, SpacingHypothesis)):
        return {
            "measurement_kind": (
                "observed"
                if isinstance(value, ObservedSpacingEvidence)
                else "hypothesis"
            ),
            "index": int(value.index),
            "state": value.state.value,
            "kind": value.kind,
            "signed_width_px": typed_read_model(value.signed_width_px),
            "provenance": typed_read_model(value.provenance),
            "reason": value.reason,
            "lane_index": value.lane_index,
            "independently_observed": bool(value.independently_observed),
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
    if isinstance(geometry, SequenceSolution):
        geometry_kind = "sequence"
    elif isinstance(geometry, DualLaneSolution):
        geometry_kind = "dual_lane"
    elif isinstance(geometry, ReviewOnlyGeometry):
        geometry_kind = "review_only"
    else:
        raise TypeError(f"unsupported candidate geometry: {type(geometry).__name__}")
    return {
        "geometry_kind": geometry_kind,
        "candidate_geometry": typed_read_model(geometry),
        "evidence_quality": typed_read_model(candidate.assessment.quality),
        "candidate_gate": candidate_gate_read_model(candidate),
        "count_hypothesis": typed_read_model(candidate.count_hypothesis),
        "evidence": candidate_evidence_read_model(candidate),
        "diagnostics": list(candidate.assessment.diagnostics),
    }


def selection_read_model(detection: FinalDetection) -> dict[str, Any]:
    selection = detection.require_selection()
    ranks = {
        id(candidate): index
        for index, candidate in enumerate(selection.ranked_candidates, start=1)
    }
    return {
        "selected_rank": ranks[id(selection.selected)],
        "consensus": selection.consensus,
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


def frame_bleed_plan_read_model(plan: Any) -> dict[str, Any]:
    return {
        "user_bleed": typed_read_model(plan.user_bleed),
        "frame_sides": typed_read_model(plan.frame_sides),
        "overlap_protection": typed_read_model(plan.overlap_protection),
        "unresolved_overlap_boundaries": list(
            plan.unresolved_overlap_boundaries
        ),
        "feasible": bool(plan.feasible),
        "reason": str(plan.reason),
    }
