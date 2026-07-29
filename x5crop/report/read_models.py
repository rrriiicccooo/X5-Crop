from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..detection.gate_checks import GateCheck


def typed_read_model(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: typed_read_model(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): typed_read_model(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [typed_read_model(item) for item in value]
    return value


def gate_check_read_model(check: GateCheck) -> dict[str, Any]:
    return {
        "code": check.code,
        "stage": check.stage.value,
        "state": check.state.value,
        "requirement": check.requirement.value,
        "final_review_reason": check.final_review_reason,
        "blocks": bool(check.blocks),
    }


def gate_read_model(gate: Any) -> dict[str, Any]:
    return {
        "passed": bool(gate.passed),
        "checks": [
            gate_check_read_model(check)
            for check in gate.checks
        ],
    }
