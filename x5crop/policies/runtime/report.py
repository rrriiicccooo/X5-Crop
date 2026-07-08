from __future__ import annotations

from dataclasses import dataclass

from ..ids import REPORT_SCHEMA_VERSION


@dataclass(frozen=True)
class ReportPolicy:
    schema_version: str = REPORT_SCHEMA_VERSION
    sections: tuple[str, ...] = (
        "version",
        "format",
        "result",
        "selected_candidate",
        "policy",
        "evidence",
        "candidate_gate",
        "decision_gate",
        "evidence_summary",
        "decision_signals",
        "decision_policy_detail",
        "policy_id",
        "candidate_table",
        "diagnostics",
        "output",
    )


__all__ = [
    "ReportPolicy",
]
