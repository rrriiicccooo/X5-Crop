from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class GateCheck:
    code: str
    stage: str
    state: EvidenceState
    consequence: str
    final_review_reason: str | None = None

    @property
    def blocks(self) -> bool:
        return self.consequence == "blocker" and self.state == EvidenceState.CONTRADICTED
