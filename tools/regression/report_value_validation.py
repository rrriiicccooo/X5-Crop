"""Validate primitive values at the external report boundary."""

from __future__ import annotations

import math


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_ids(value: object, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
        and len(set(value)) == len(value)
    )


def _valid_interval(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"minimum", "maximum"}
        and _finite_number(value["minimum"])
        and _finite_number(value["maximum"])
        and float(value["minimum"]) <= float(value["maximum"])
    )


def _interval_contains(
    interval: object,
    value: object,
    *,
    epsilon: float = 1.0e-9,
) -> bool:
    return (
        _valid_interval(interval)
        and _finite_number(value)
        and float(interval["minimum"]) - epsilon
        <= float(value)
        <= float(interval["maximum"]) + epsilon
    )
