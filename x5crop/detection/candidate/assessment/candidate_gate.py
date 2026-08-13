from __future__ import annotations

from collections.abc import Mapping

from ....domain import EvidenceState
from ...gate_checks import (
    GATE_CHECK_DEPENDENCIES,
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

    evaluated_cache: dict[str, bool] = {}

    def is_evaluated(code: str, active: frozenset[str] = frozenset()) -> bool:
        if code in evaluated_cache:
            return evaluated_cache[code]
        if code in active:
            raise ValueError("candidate gate dependency graph contains a cycle")
        evaluated = all(
            is_evaluated(dependency, active | {code})
            and facts[dependency].state == EvidenceState.SUPPORTED
            for dependency in GATE_CHECK_DEPENDENCIES.get(code, ())
        )
        evaluated_cache[code] = evaluated
        return evaluated

    return CandidateGateAssessment(
        checks=tuple(
            GateCheck(
                code=code,
                stage=GateStage.CANDIDATE,
                state=(
                    facts[code].state
                    if is_evaluated(code)
                    else EvidenceState.UNAVAILABLE
                ),
                gap=facts[code].gap if is_evaluated(code) else None,
                evaluated=is_evaluated(code),
            )
            for code in CANDIDATE_GATE_CHECK_CODES
        )
    )
