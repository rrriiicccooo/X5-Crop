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
_CONTAINER_TYPES = frozenset((dict, list))


@lru_cache(maxsize=256)
def _model_layout(model_type: type):
    """Cache class metadata only, in the original conversion precedence."""
    if issubclass(model_type,bytes):return 'bytes',False,()
    if issubclass(model_type,Enum):return 'enum',False,()
    if is_dataclass(model_type):
        return ('model',model_type.__dataclass_params__.frozen,
                tuple(field.name for field in fields(model_type) if not field.name.startswith('_')))
    if issubclass(model_type,dict):return 'dict',False,()
    if issubclass(model_type,(list,tuple)):return 'sequence',False,()
    return 'opaque',False,()


def typed_read_model(value: Any) -> Any:
    """Return independently mutable branches, preserving opaque leaves."""
    return _convert_read_model(value, share_frozen_templates=False)


def _report_write_view(value: Any) -> Any:
    """Owned JSON/CSV snapshot; consumers must only read this private view.

    It has exactly the public projection's values and conversion rules, but
    repeated frozen facts may share converted containers within this call.
    No raw model is retained in place of a converted model, and mutable input
    containers are still copied. The existing opaque-leaf policy is unchanged.
    """
    return _convert_read_model(value, share_frozen_templates=True)


def _convert_read_model(value: Any, *, share_frozen_templates: bool) -> Any:
    # One call-local bounded template memo. Public projections copy on hits;
    # the private write-only snapshot can retain the same converted template.
    memo: OrderedDict[int, tuple[object, dict[str, Any]]] = OrderedDict()
    opaque_containers: set[int] = set()

    def copy_tree(item):
        kind = type(item)
        if kind is dict and id(item) not in opaque_containers:
            result = item.copy()
            for key, child in item.items():
                child_type = type(child)
                if child_type is dict or child_type is list:
                    result[key] = copy_tree(child)
            return result
        if kind is list and id(item) not in opaque_containers:
            return [copy_tree(child) if type(child) in _CONTAINER_TYPES else child for child in item]
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
        kind,frozen,names = _model_layout(type(item))
        if kind == 'bytes':
            return f"<bytes:{len(item)}>"
        if kind == 'enum':
            result = item.value
            if type(result) in (dict, list):
                opaque_containers.add(id(result))
            return result
        if kind == 'model':
            if isinstance(item,type):return item
            key = id(item)
            previous = memo.get(key)
            if previous is not None and previous[0] is item:
                memo.move_to_end(key)
                return previous[1] if share_frozen_templates else copy_tree(previous[1])
            result = {name: child if type(child := getattr(item, name)) in _SCALAR_TYPES else convert(child)
                      for name in names}
            if frozen:
                memo[key] = item, result
                if len(memo) > 4096:
                    memo.popitem(last=False)
            return result
        if kind == 'dict':
            return {str(key): child if type(child) in _SCALAR_TYPES else convert(child)
                    for key, child in item.items()}
        if kind == 'sequence':
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
