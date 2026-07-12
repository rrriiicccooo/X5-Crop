from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class GateCheck:
    code: str
    stage: str
    state: EvidenceState
    final_review_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("gate check code must not be empty")
        if self.stage == "candidate":
            if self.final_review_reason is not None:
                raise ValueError("candidate gate checks cannot own final reasons")
        elif self.stage == "decision":
            if not self.final_review_reason:
                raise ValueError("decision gate checks require a final reason")
        else:
            raise ValueError(f"unsupported gate stage: {self.stage}")

    @property
    def blocks(self) -> bool:
        return self.state == EvidenceState.CONTRADICTED
