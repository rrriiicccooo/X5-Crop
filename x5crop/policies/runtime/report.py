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
        "gates",
        "evidence_summary",
        "risk_summary",
        "decision_policy_detail",
        "policy_id",
        "candidate_table",
        "diagnostics",
        "output",
    )


__all__ = [
    "ReportPolicy",
]
