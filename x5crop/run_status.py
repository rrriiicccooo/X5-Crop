from __future__ import annotations

from enum import Enum


class RunTerminalOutcome(str, Enum):
    APPROVED_AUTO = "approved_auto"
    NEEDS_REVIEW = "needs_review"
    RUNTIME_ERROR = "runtime_error"
