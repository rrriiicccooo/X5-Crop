from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from x5crop.domain import EvidenceState


class GateStage(str, Enum):
    CANDIDATE = "candidate"
    DECISION = "decision"


class GateRequirement(str, Enum):
    SUPPORTED_REQUIRED = "supported_required"
    NOT_CONTRADICTED = "not_contradicted"


@dataclass(frozen=True)
class GateCheck:
    code: str
    stage: GateStage
    state: EvidenceState
    requirement: GateRequirement
    final_review_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("gate check code must not be empty")
        if not isinstance(self.stage, GateStage):
            raise TypeError("gate check requires a typed stage")
        if not isinstance(self.requirement, GateRequirement):
            raise TypeError("gate check requires a typed requirement")
        if self.stage == GateStage.CANDIDATE:
            if self.final_review_reason is not None:
                raise ValueError("candidate gate checks cannot own final reasons")
        elif self.stage == GateStage.DECISION:
            if not self.final_review_reason:
                raise ValueError("decision gate checks require a final reason")

    @property
    def blocks(self) -> bool:
        if self.requirement == GateRequirement.SUPPORTED_REQUIRED:
            return self.state != EvidenceState.SUPPORTED
        return self.state == EvidenceState.CONTRADICTED
