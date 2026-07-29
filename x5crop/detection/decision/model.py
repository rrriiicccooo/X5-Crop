from __future__ import annotations

from dataclasses import dataclass

from ..gate_checks import GateCheck, GateStage
from .vocabulary import (
    FINAL_REASON_FRAME_GRID_AUTHORITY_UNAVAILABLE,
    FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
    FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_UNAVAILABLE,
)


DECISION_GATE_CHECK_CODES = (
    "scan_canvas_authority",
    "source_content_measurement",
    "frame_grid_authority",
)

DECISION_GATE_REASON_BY_CODE = {
    "scan_canvas_authority": FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
    "source_content_measurement": (
        FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_UNAVAILABLE
    ),
    "frame_grid_authority": FINAL_REASON_FRAME_GRID_AUTHORITY_UNAVAILABLE,
}


@dataclass(frozen=True)
class DecisionGateAssessment:
    checks: tuple[GateCheck, ...]

    def __post_init__(self) -> None:
        if tuple(check.code for check in self.checks) != DECISION_GATE_CHECK_CODES:
            raise ValueError("decision gate checks must be complete and ordered")
        if any(check.stage != GateStage.DECISION for check in self.checks):
            raise ValueError("decision gate owns only decision checks")
        if any(
            check.final_review_reason != DECISION_GATE_REASON_BY_CODE[check.code]
            for check in self.checks
        ):
            raise ValueError("decision checks require canonical reasons")

    @property
    def blocking_checks(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.blocking_checks

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return tuple(
            check.final_review_reason
            for check in self.blocking_checks
            if check.final_review_reason is not None
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
