from __future__ import annotations

from ..runtime.report import ReportPolicy


def report_policy() -> ReportPolicy:
    return ReportPolicy()


__all__ = [
    "report_policy",
]
