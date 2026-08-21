from __future__ import annotations

from dataclasses import dataclass

from ...gate_checks import GateCheck, GateStage


CANDIDATE_GATE_CHECK_CODES = (
    "scan_canvas_authority",
    "output_slot_count",
    "observation_completeness",
    "source_scan_geometry",
    "complete_placement",
    "producer_coverage",
    "sequence_authority",
    "cross_authority",
    "shared_authority",
    "local_advance_authority",
    "content_protection",
    "selected_placement",
    "dual_lane_fill",
    "slot_ordinal_assignment",
    "source_lane_authority",
    "selected_output_footprint",
    "direct_use_budget",
)


@dataclass(frozen=True)
class CandidateGateAssessment:
    checks: tuple[GateCheck, ...]

    def __post_init__(self) -> None:
        if tuple(check.code for check in self.checks) != CANDIDATE_GATE_CHECK_CODES:
            raise ValueError("candidate gate checks must be complete and ordered")
        if any(check.stage != GateStage.CANDIDATE for check in self.checks):
            raise ValueError("candidate gate owns only candidate checks")

    @property
    def blocking_checks(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.blocking_checks
