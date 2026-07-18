from __future__ import annotations

from ...gate_checks import GateCheck, GateRequirement, GateStage
from .model import (
    CandidateGateAssessment,
    CandidateGateInput,
    sequence_proof_state,
)


def candidate_gate_assessment(gate_input: CandidateGateInput) -> CandidateGateAssessment:
    proof_state = sequence_proof_state(gate_input.proof_paths)
    checks = (
        GateCheck(
            code="frame_slot_topology",
            stage=GateStage.CANDIDATE,
            state=gate_input.frame_slot_topology,
            requirement=GateRequirement.SUPPORTED_REQUIRED,
        ),
        GateCheck(
            code="content_preservation",
            stage=GateStage.CANDIDATE,
            state=gate_input.content_preservation,
            requirement=GateRequirement.NOT_CONTRADICTED,
        ),
        GateCheck(
            code="frame_dimension_consistency",
            stage=GateStage.CANDIDATE,
            state=gate_input.frame_dimensions,
            requirement=GateRequirement.NOT_CONTRADICTED,
        ),
        GateCheck(
            code="evidence_independence",
            stage=GateStage.CANDIDATE,
            state=gate_input.evidence_independence,
            requirement=GateRequirement.SUPPORTED_REQUIRED,
        ),
        GateCheck(
            code="sequence_proof",
            stage=GateStage.CANDIDATE,
            state=proof_state,
            requirement=GateRequirement.SUPPORTED_REQUIRED,
        ),
    )
    return CandidateGateAssessment(
        checks=checks,
        proof_paths=gate_input.proof_paths,
        diagnostics=tuple(sorted(set(gate_input.diagnostics))),
    )
