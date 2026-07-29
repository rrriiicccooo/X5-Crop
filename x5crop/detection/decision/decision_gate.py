from __future__ import annotations

from ..candidate.assessment.model import CandidateGateAssessment
from ..gate_checks import GateCheck, GateRequirement, GateStage
from .model import DECISION_GATE_REASON_BY_CODE, DecisionGateAssessment


def apply_decision_gate(
    candidate_gate: CandidateGateAssessment,
) -> DecisionGateAssessment:
    return DecisionGateAssessment(
        checks=tuple(
            GateCheck(
                code=check.code,
                stage=GateStage.DECISION,
                state=check.state,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
                final_review_reason=DECISION_GATE_REASON_BY_CODE[check.code],
            )
            for check in candidate_gate.checks
        )
    )
