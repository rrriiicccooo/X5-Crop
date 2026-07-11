from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...evidence.state import EvidenceState
from ...gate_checks import GateCheck, gate_check_details


BOUNDARY_PROOF_PATH_CODES = frozenset(
    {
        "separator_led",
        "geometry_led",
        "partial_occupancy_led",
        "mode_composition",
    }
)


@dataclass(frozen=True)
class BoundaryProofPath:
    code: str
    state: EvidenceState
    detail: dict[str, Any] = field(default_factory=dict)

    def report_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "state": self.state.value,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class CandidateGateInput:
    frame_topology: EvidenceState
    content_preservation: EvidenceState
    photo_geometry: EvidenceState
    evidence_independence: EvidenceState
    proof_paths: tuple[BoundaryProofPath, ...]
    diagnostics: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateGateAssessment:
    passed: bool
    checks: tuple[GateCheck, ...]
    proof_paths: tuple[BoundaryProofPath, ...]
    failed_checks: tuple[str, ...]
    diagnostics: tuple[str, ...]

    def report_detail(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "checks": gate_check_details(list(self.checks)),
            "proof_paths": [path.report_detail() for path in self.proof_paths],
            "failed_checks": list(self.failed_checks),
            "diagnostics": list(self.diagnostics),
        }


def candidate_gate_assessment(gate_input: CandidateGateInput) -> CandidateGateAssessment:
    unknown_paths = sorted(
        {path.code for path in gate_input.proof_paths} - BOUNDARY_PROOF_PATH_CODES
    )
    if unknown_paths:
        raise ValueError(f"unowned boundary proof path: {','.join(unknown_paths)}")
    boundary_state = (
        EvidenceState.SUPPORTED
        if any(path.state == EvidenceState.SUPPORTED for path in gate_input.proof_paths)
        else EvidenceState.CONTRADICTED
    )
    checks = (
        GateCheck(
            code="frame_topology_integrity",
            stage="candidate",
            state=gate_input.frame_topology,
            consequence="blocker",
        ),
        GateCheck(
            code="content_preservation",
            stage="candidate",
            state=gate_input.content_preservation,
            consequence="blocker",
        ),
        GateCheck(
            code="photo_geometry_consistency",
            stage="candidate",
            state=gate_input.photo_geometry,
            consequence="blocker",
        ),
        GateCheck(
            code="evidence_independence",
            stage="candidate",
            state=gate_input.evidence_independence,
            consequence="blocker",
        ),
        GateCheck(
            code="boundary_proof",
            stage="candidate",
            state=boundary_state,
            consequence="blocker",
            detail={
                "supported_paths": [
                    path.code
                    for path in gate_input.proof_paths
                    if path.state == EvidenceState.SUPPORTED
                ],
                **dict(gate_input.detail),
            },
        ),
    )
    failed_checks = tuple(check.code for check in checks if check.blocks)
    return CandidateGateAssessment(
        passed=not failed_checks,
        checks=checks,
        proof_paths=gate_input.proof_paths,
        failed_checks=failed_checks,
        diagnostics=tuple(sorted(set(gate_input.diagnostics))),
    )
