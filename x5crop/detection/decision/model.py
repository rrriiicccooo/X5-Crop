from __future__ import annotations

from dataclasses import dataclass

from ..gate_checks import GateCheck, GateStage
from .vocabulary import (
    FINAL_REASON_CAPACITY_OUTPUT_SLOT_COUNT_UNFULFILLED,
    FINAL_REASON_GRID_SEARCH_COVERAGE_OUTCOME_RISK,
    FINAL_REASON_KNOWN_CONTENT_CONTAINMENT_UNBOUNDED,
    FINAL_REASON_OUTPUT_PROTECTION_UNAVAILABLE,
    FINAL_REASON_OUTPUT_TRANSFORM_UNAVAILABLE,
    FINAL_REASON_REQUESTED_COUNT_UNFULFILLED,
    FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
    FINAL_REASON_SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED,
    FINAL_REASON_SLOT_OWNERSHIP_UNBOUNDED,
    FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_CONTRADICTED,
    FINAL_REASON_SOURCE_LANE_GEOMETRY_INVALID,
)


DECISION_GATE_CHECK_CODES = (
    "scan_canvas_authority",
    "source_content_measurement",
    "grid_search_coverage",
    "output_slot_count",
    "slot_ordinal_assignment",
    "slot_ownership",
    "known_content_containment",
    "source_lane_geometry",
    "output_protection",
    "output_transform",
)

DECISION_GATE_REASON_BY_CODE = {
    "scan_canvas_authority": FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
    "source_content_measurement": (
        FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_CONTRADICTED
    ),
    "grid_search_coverage": FINAL_REASON_GRID_SEARCH_COVERAGE_OUTCOME_RISK,
    "output_slot_count": FINAL_REASON_REQUESTED_COUNT_UNFULFILLED,
    "slot_ordinal_assignment": (
        FINAL_REASON_SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED
    ),
    "slot_ownership": FINAL_REASON_SLOT_OWNERSHIP_UNBOUNDED,
    "known_content_containment": (
        FINAL_REASON_KNOWN_CONTENT_CONTAINMENT_UNBOUNDED
    ),
    "source_lane_geometry": FINAL_REASON_SOURCE_LANE_GEOMETRY_INVALID,
    "output_protection": FINAL_REASON_OUTPUT_PROTECTION_UNAVAILABLE,
    "output_transform": FINAL_REASON_OUTPUT_TRANSFORM_UNAVAILABLE,
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
            (
                check.final_review_reason
                not in {
                    FINAL_REASON_REQUESTED_COUNT_UNFULFILLED,
                    FINAL_REASON_CAPACITY_OUTPUT_SLOT_COUNT_UNFULFILLED,
                }
                if check.code == "output_slot_count"
                else check.final_review_reason
                != DECISION_GATE_REASON_BY_CODE[check.code]
            )
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
