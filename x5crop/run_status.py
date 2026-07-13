from __future__ import annotations

from enum import Enum


class RunTerminalOutcome(str, Enum):
    COMPLETED = "completed"
    RUNTIME_ERROR = "runtime_error"
