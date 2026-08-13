"""In-process report value; external readers own schema validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReportResult:
    record: dict[str, Any]
