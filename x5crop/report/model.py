from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .validation import validate_current_report_record


@dataclass(frozen=True)
class ReportResult:
    record: dict[str, Any]

    def __post_init__(self) -> None:
        validate_current_report_record(self.record)
