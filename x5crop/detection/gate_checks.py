from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GateCheck:
    code: str
    stage: str
    bucket: str
    passed: bool
    severity: str
    signal: str
    detail: dict[str, Any] = field(default_factory=dict)

    def report_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "bucket": self.bucket,
            "passed": bool(self.passed),
            "severity": self.severity,
            "signal": self.signal,
            "detail": dict(self.detail),
        }


def gate_check_details(checks: list[GateCheck]) -> list[dict[str, Any]]:
    return [check.report_detail() for check in checks]


def unique_signals(signals: list[str]) -> list[str]:
    return sorted({signal for signal in signals if signal})
