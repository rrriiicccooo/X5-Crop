from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import Any

from ..detection.gate_checks import GateCheck


_SCALAR_TYPES = frozenset((str, int, float, bool, type(None)))


@lru_cache(maxsize=256)
def _public_field_names(model_type: type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(model_type) if not field.name.startswith("_"))


def typed_read_model(value: Any) -> Any:
    # A conversion template is local to this call. Copy it on every hit so
    # repeated facts still produce independently mutable report branches.
    memo: dict[int, tuple[object, dict[str, Any]]] = {}
    opaque_containers: set[int] = set()

    def copy_tree(item):
        kind = type(item)
        if kind is dict and id(item) not in opaque_containers:
            return {key: copy_tree(child) for key, child in item.items()}
        if kind is list and id(item) not in opaque_containers:
            return [copy_tree(child) for child in item]
        return item

    def convert(item):
        if type(item) in _SCALAR_TYPES:
            return item
        if isinstance(item, bytes):
            return f"<bytes:{len(item)}>"
        if isinstance(item, Enum):
            result = item.value
            if type(result) in (dict, list):
                opaque_containers.add(id(result))
            return result
        if is_dataclass(item) and not isinstance(item, type):
            previous = memo.get(id(item))
            if previous is not None and previous[0] is item:
                return copy_tree(previous[1])
            result = {name: convert(getattr(item, name))
                      for name in _public_field_names(type(item))}
            if type(item).__dataclass_params__.frozen and len(memo) < 4096:
                memo[id(item)] = item, result
            return result
        if isinstance(item, dict):
            return {str(key): convert(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(child) for child in item]
        return item

    return convert(value)


def gate_check_read_model(check: GateCheck) -> dict[str, Any]:
    return {
        "code": check.code,
        "stage": check.stage.value,
        "state": check.state.value,
        "gap": None if check.gap is None else check.gap.value,
        "failure": typed_read_model(check.failure),
        "final_review_reason": check.final_review_reason,
        "evaluated": bool(check.evaluated),
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
