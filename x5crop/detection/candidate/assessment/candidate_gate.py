from __future__ import annotations

from collections.abc import Mapping

from ...gate_checks import (
    GateCheck,
    GateStage,
    TypedAssessment,
)
from ..assessment.model import (
    CANDIDATE_GATE_CHECK_CODES,
    CandidateGateAssessment,
)


def candidate_gate_assessment(
    facts: Mapping[str, TypedAssessment],
) -> CandidateGateAssessment:
    if set(facts) != set(CANDIDATE_GATE_CHECK_CODES):
        raise ValueError("candidate gate requires exact keyed assessments")
    return CandidateGateAssessment(
        checks=tuple(
            GateCheck(
                code=code,
                stage=GateStage.CANDIDATE,
                state=facts[code].state,
                gap=facts[code].gap,
            )
            for code in CANDIDATE_GATE_CHECK_CODES
        )
    )
