from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState
from ...gate_checks import GateCheck


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
    supporting_evidence: tuple[str, ...]


@dataclass(frozen=True)
class CandidateGateInput:
    frame_topology: EvidenceState
    content_preservation: EvidenceState
    photo_geometry: EvidenceState
    sequence_conservation: EvidenceState
    evidence_independence: EvidenceState
    proof_paths: tuple[BoundaryProofPath, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateGateAssessment:
    checks: tuple[GateCheck, ...]
    proof_paths: tuple[BoundaryProofPath, ...]
    diagnostics: tuple[str, ...]

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(check.code for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.failed_checks


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
            code="frame_sequence_conservation",
            stage="candidate",
            state=gate_input.sequence_conservation,
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
        ),
    )
    return CandidateGateAssessment(
        checks=checks,
        proof_paths=gate_input.proof_paths,
        diagnostics=tuple(sorted(set(gate_input.diagnostics))),
    )
