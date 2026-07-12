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
CANDIDATE_GATE_CHECK_CODES = (
    "frame_topology_integrity",
    "content_preservation",
    "photo_geometry_consistency",
    "frame_sequence_conservation",
    "evidence_independence",
    "boundary_proof",
)


@dataclass(frozen=True)
class BoundaryProofPath:
    code: str
    state: EvidenceState
    supporting_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.code not in BOUNDARY_PROOF_PATH_CODES:
            raise ValueError(f"unowned boundary proof path: {self.code}")
        if any(not item for item in self.supporting_evidence) or len(
            set(self.supporting_evidence)
        ) != len(self.supporting_evidence):
            raise ValueError("boundary proof evidence names must be non-empty and unique")


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

    def __post_init__(self) -> None:
        if tuple(check.code for check in self.checks) != CANDIDATE_GATE_CHECK_CODES:
            raise ValueError("candidate gate checks must be complete and ordered")
        if any(check.stage != "candidate" for check in self.checks):
            raise ValueError("candidate gate can contain only candidate-stage checks")
        if len({path.code for path in self.proof_paths}) != len(self.proof_paths):
            raise ValueError("candidate boundary proof paths must be unique")
        if any(not item for item in self.diagnostics) or len(
            set(self.diagnostics)
        ) != len(self.diagnostics):
            raise ValueError("candidate diagnostics must be non-empty and unique")

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(check.code for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.failed_checks


def candidate_gate_assessment(gate_input: CandidateGateInput) -> CandidateGateAssessment:
    if any(
        path.state == EvidenceState.SUPPORTED
        for path in gate_input.proof_paths
    ):
        boundary_state = EvidenceState.SUPPORTED
    elif gate_input.proof_paths and all(
        path.state == EvidenceState.NOT_APPLICABLE
        for path in gate_input.proof_paths
    ):
        boundary_state = EvidenceState.NOT_APPLICABLE
    else:
        boundary_state = EvidenceState.CONTRADICTED
    checks = (
        GateCheck(
            code="frame_topology_integrity",
            stage="candidate",
            state=gate_input.frame_topology,
        ),
        GateCheck(
            code="content_preservation",
            stage="candidate",
            state=gate_input.content_preservation,
        ),
        GateCheck(
            code="photo_geometry_consistency",
            stage="candidate",
            state=gate_input.photo_geometry,
        ),
        GateCheck(
            code="frame_sequence_conservation",
            stage="candidate",
            state=gate_input.sequence_conservation,
        ),
        GateCheck(
            code="evidence_independence",
            stage="candidate",
            state=gate_input.evidence_independence,
        ),
        GateCheck(
            code="boundary_proof",
            stage="candidate",
            state=boundary_state,
        ),
    )
    return CandidateGateAssessment(
        checks=checks,
        proof_paths=gate_input.proof_paths,
        diagnostics=tuple(sorted(set(gate_input.diagnostics))),
    )
