from __future__ import annotations

from dataclasses import dataclass

from ...gate_checks import GateCheck, GateStage


CANDIDATE_GATE_CHECK_CODES = (
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
