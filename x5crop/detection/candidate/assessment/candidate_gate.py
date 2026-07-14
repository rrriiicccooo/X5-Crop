from __future__ import annotations

from ...gate_checks import GateCheck, GateStage
from .model import (
    CandidateGateAssessment,
    CandidateGateInput,
    boundary_proof_state,
)


def candidate_gate_assessment(gate_input: CandidateGateInput) -> CandidateGateAssessment:
    boundary_state = boundary_proof_state(gate_input.proof_paths)
    checks = (
        GateCheck(
            code="content_preservation",
            stage=GateStage.CANDIDATE,
            state=gate_input.content_preservation,
        ),
        GateCheck(
            code="photo_geometry_consistency",
            stage=GateStage.CANDIDATE,
            state=gate_input.photo_geometry,
        ),
        GateCheck(
            code="frame_sequence_conservation",
            stage=GateStage.CANDIDATE,
            state=gate_input.sequence_conservation,
        ),
        GateCheck(
            code="evidence_independence",
            stage=GateStage.CANDIDATE,
            state=gate_input.evidence_independence,
        ),
        GateCheck(
            code="boundary_proof",
            stage=GateStage.CANDIDATE,
            state=boundary_state,
        ),
    )
    return CandidateGateAssessment(
        checks=checks,
        proof_paths=gate_input.proof_paths,
        diagnostics=tuple(sorted(set(gate_input.diagnostics))),
    )
