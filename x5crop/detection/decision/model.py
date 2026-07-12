from __future__ import annotations

from dataclasses import dataclass
from ..gate_checks import GateCheck
from .vocabulary import FINAL_REVIEW_REASONS


@dataclass(frozen=True)
class DecisionGateAssessment:
    checks: tuple[GateCheck, ...]

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError("decision gate requires checks")
        if any(check.stage != "decision" for check in self.checks):
            raise ValueError("decision gate can contain only decision-stage checks")
        if any(
            check.final_review_reason not in FINAL_REVIEW_REASONS
            for check in self.checks
        ):
            raise ValueError("decision gate final reasons must use its vocabulary")
        codes = tuple(check.code for check in self.checks)
        if len(set(codes)) != len(codes):
            raise ValueError("decision gate check codes must be unique")

    @property
    def blocking_checks(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.blocking_checks

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                check.final_review_reason
                for check in self.blocking_checks
                if check.final_review_reason is not None
            )
        )

    @property
    def reason_inputs(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (check.code, check.final_review_reason)
            for check in self.blocking_checks
            if check.final_review_reason is not None
        )

    @property
    def status(self) -> str:
        return "approved_auto" if self.passed else "needs_review"
