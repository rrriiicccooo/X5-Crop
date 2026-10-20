from __future__ import annotations

from collections import OrderedDict
from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import Any

from ..detection.gate_checks import GateCheck
from ..domain import FiniteInterval, PositiveInterval


_SCALAR_TYPES = frozenset((str, int, float, bool, type(None)))
_INTERVAL_TYPES = frozenset((FiniteInterval, PositiveInterval))


@lru_cache(maxsize=256)
def _public_field_names(model_type: type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(model_type) if not field.name.startswith("_"))


def typed_read_model(value: Any) -> Any:
    # A conversion template is local to this call. Copy it on every hit so
    # repeated facts still produce independently mutable report branches.
    # The report graph can retain thousands of shared frozen proof objects.
    # Keep the same bounded capacity while retaining recently reused objects;
    # the memo remains local so report branches cannot share mutable state.
    memo: OrderedDict[int, tuple[object, dict[str, Any]]] = OrderedDict()
    opaque_containers: set[int] = set()

    def copy_tree(item):
        kind = type(item)
        if kind is dict and id(item) not in opaque_containers:
            if all(type(child) in _SCALAR_TYPES for child in item.values()):
                return dict(item)
            return {key: child if type(child) in _SCALAR_TYPES else copy_tree(child)
                    for key, child in item.items()}
        if kind is list and id(item) not in opaque_containers:
            return [child if type(child) in _SCALAR_TYPES else copy_tree(child) for child in item]
        return item

    def convert(item):
        if type(item) in _SCALAR_TYPES:
            return item
        if type(item) in _INTERVAL_TYPES:
            # Fixed value objects have only these two public fields. A fresh
            # leaf dict is cheaper than occupying a frozen graph memo slot.
            minimum, maximum = item.minimum, item.maximum
            return {"minimum": minimum if type(minimum) in _SCALAR_TYPES else convert(minimum),
                    "maximum": maximum if type(maximum) in _SCALAR_TYPES else convert(maximum)}
        if isinstance(item, bytes):
            return f"<bytes:{len(item)}>"
        if isinstance(item, Enum):
            result = item.value
            if type(result) in (dict, list):
                opaque_containers.add(id(result))
            return result
        if is_dataclass(item) and not isinstance(item, type):
            key = id(item)
            previous = memo.get(key)
            if previous is not None and previous[0] is item:
                memo.move_to_end(key)
                return copy_tree(previous[1])
            result = {name: child if type(child := getattr(item, name)) in _SCALAR_TYPES else convert(child)
                      for name in _public_field_names(type(item))}
            if type(item).__dataclass_params__.frozen:
                memo[key] = item, result
                if len(memo) > 4096:
                    memo.popitem(last=False)
            return result
        if isinstance(item, dict):
            return {str(key): child if type(child) in _SCALAR_TYPES else convert(child)
                    for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [child if type(child) in _SCALAR_TYPES else convert(child) for child in item]
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
