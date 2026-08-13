"""Finite-interval arithmetic shared by physical-chain reconstruction."""

from __future__ import annotations

from ...domain import FiniteInterval


def intersect(
    left: FiniteInterval,
    right: FiniteInterval,
    *,
    epsilon: float = 0.0,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if maximum < minimum:
        if minimum - maximum > epsilon:
            return None
        return FiniteInterval.exact((minimum + maximum) / 2.0)
    return FiniteInterval(minimum, maximum)


def hull(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    if not values:
        raise ValueError("interval hull requires at least one value")
    return FiniteInterval(
        min(value.minimum for value in values),
        max(value.maximum for value in values),
    )


def add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )


def subtract(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def multiply(interval: FiniteInterval, coefficient: float) -> FiniteInterval:
    values = (interval.minimum * coefficient, interval.maximum * coefficient)
    return FiniteInterval(min(values), max(values))


def common(values: tuple[FiniteInterval, ...]) -> FiniteInterval | None:
    if not values:
        return None
    minimum = max(value.minimum for value in values)
    maximum = min(value.maximum for value in values)
    return None if maximum < minimum else FiniteInterval(minimum, maximum)
