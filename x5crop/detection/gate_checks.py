from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .evidence.state import EvidenceState


@dataclass(frozen=True)
class GateCheck:
    code: str
    stage: str
    state: EvidenceState
    consequence: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def blocks(self) -> bool:
        return self.consequence == "blocker" and self.state == EvidenceState.CONTRADICTED

    def report_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "state": self.state.value,
            "consequence": self.consequence,
            "blocks": bool(self.blocks),
            "detail": dict(self.detail),
        }


def gate_check_details(checks: list[GateCheck]) -> list[dict[str, Any]]:
    return [check.report_detail() for check in checks]
