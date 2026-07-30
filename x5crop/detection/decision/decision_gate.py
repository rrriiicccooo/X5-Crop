from __future__ import annotations

from ...configuration.model import FrameCountMode
from ..candidate.assessment.model import CandidateGateAssessment
from ..gate_checks import GateCheck, GateRequirement, GateStage
from .model import DECISION_GATE_REASON_BY_CODE, DecisionGateAssessment


def apply_decision_gate(
    candidate_gate: CandidateGateAssessment,
    count_mode: FrameCountMode,
) -> DecisionGateAssessment:
    return DecisionGateAssessment(
        checks=tuple(
            GateCheck(
                code=check.code,
                stage=GateStage.DECISION,
                state=check.state,
                requirement=check.requirement,
                final_review_reason=(
                    (
                        "capacity_output_slot_count_unfulfilled"
                        if count_mode == FrameCountMode.AUTO
                        else "requested_count_unfulfilled"
                    )
                    if check.code == "output_slot_count"
                    else DECISION_GATE_REASON_BY_CODE[check.code]
                ),
            )
            for check in candidate_gate.checks
        )
    )
