"""Shared interval geometry for bounded short-axis template fitting."""

from __future__ import annotations

from typing import Sequence

from ...domain import FiniteInterval
from .interval_math import intersect as _intersect
from .output_model import SharedStripDirection
from .template_cross_model import CrossRoleBinding


def hull_intervals(
    intervals: Sequence[FiniteInterval],
) -> FiniteInterval:
    if not intervals:
        raise ValueError("cannot hull an empty interval set")
    return FiniteInterval(
        min(interval.minimum for interval in intervals),
        max(interval.maximum for interval in intervals),
    )


def shared_direction_for(
    direct: tuple[CrossRoleBinding, ...],
    *,
    parallel_interval: FiniteInterval | None = None,
) -> SharedStripDirection | None:
    """Close one shared direction from directly measured cross bindings."""

    if not direct or any(
        item.fit_direction_interval_degrees is None
        or item.full_direction_interval_degrees is None
        or item.canonical_direction_degrees is None
        for item in direct
    ):
        return None
    fit_intervals = tuple(item.fit_direction_interval_degrees for item in direct)
    full_intervals = tuple(item.full_direction_interval_degrees for item in direct)
    observed_intervals = tuple(
        item.observed_direction_interval_degrees for item in direct
    )
    assert all(item is not None for item in fit_intervals)
    assert all(item is not None for item in full_intervals)
    common = parallel_interval
    if common is None:
        common = fit_intervals[0]
        assert common is not None
        for item in direct[1:]:
            interval = item.fit_direction_interval_degrees
            assert interval is not None
            common = _intersect(common, interval)
            if common is None:
                return None
    canonical_values = tuple(
        float(item.canonical_direction_degrees) for item in direct
    )
    identities = tuple(item.observation_id for item in direct)
    spanning_intervals = tuple(
        item.full_direction_interval_degrees
        for item in direct
        if item.source_spanning_continuous
    )
    safety_intervals = spanning_intervals or full_intervals
    safety = hull_intervals(
        tuple(item for item in safety_intervals if item is not None)
    )
    common = _intersect(common, safety)
    if common is None:
        return None
    canonical = min(
        common.maximum,
        max(common.minimum, sum(canonical_values) / len(canonical_values)),
    )
    return SharedStripDirection(
        direction_id="template-cross-direction:" + ":".join(map(str, identities)),
        selected_observation_ids=identities,
        # Compatibility closes one canonical direction. Safety retains all
        # directly measured source-spanning variation; a local opposite side
        # may validate H without exporting its uncertainty across the source.
        full_angle_interval_degrees=safety,
        observed_angle_interval_degrees=hull_intervals(
            tuple(item for item in observed_intervals if item is not None)
        ),
        canonical_angle_degrees=canonical,
    )


def median_trace_step(values: Sequence[int]) -> float:
    ordered = tuple(sorted(set(values)))
    if len(ordered) < 2:
        return 1.0
    steps = tuple(right - left for left, right in zip(ordered, ordered[1:]))
    return float(sorted(steps)[len(steps) // 2])


def shared_trace_coordinates(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
) -> tuple[int, ...]:
    if not top.trace_coordinates_px or not bottom.trace_coordinates_px:
        return ()
    common = tuple(
        sorted(
            set(top.trace_coordinates_px).intersection(
                bottom.trace_coordinates_px
            )
        )
    )
    if common:
        return common
    maximum_distance = max(
        1.0,
        median_trace_step(
            (*top.trace_coordinates_px, *bottom.trace_coordinates_px)
        ),
    )
    return tuple(
        sorted(
            {
                int(round((left + right) / 2.0))
                for left in top.trace_coordinates_px
                for right in bottom.trace_coordinates_px
                if abs(left - right) <= maximum_distance
            }
        )
    )


def direction_closure(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
) -> tuple[FiniteInterval | None, bool, bool]:
    """Return parallel interval, readiness, and contradiction."""

    top_interval = top.fit_direction_interval_degrees
    bottom_interval = bottom.fit_direction_interval_degrees
    if top_interval is not None and bottom_interval is not None:
        common = _intersect(top_interval, bottom_interval)
        if common is None:
            top_full = top.full_direction_interval_degrees
            bottom_full = bottom.full_direction_interval_degrees
            if top_full is None or bottom_full is None:
                return None, False, True
            # Local fits may disagree on a slightly bent strip. Their full
            # measured intervals decide whether one straight direction exists.
            common = _intersect(top_full, bottom_full)
            if common is None:
                return None, False, True
        ready = (
            top.canonical_direction_degrees is not None
            and bottom.canonical_direction_degrees is not None
        )
        return common, ready, False
    if top_interval is not None:
        return top_interval, top.canonical_direction_degrees is not None, False
    if bottom_interval is not None:
        return (
            bottom_interval,
            bottom.canonical_direction_degrees is not None,
            False,
        )
    return None, False, False


def single_direction_ready(binding: CrossRoleBinding) -> bool:
    return (
        binding.fit_direction_interval_degrees is not None
        and binding.full_direction_interval_degrees is not None
        and binding.canonical_direction_degrees is not None
    )


__all__ = [
    "direction_closure",
    "hull_intervals",
    "shared_direction_for",
    "shared_trace_coordinates",
    "single_direction_ready",
]
