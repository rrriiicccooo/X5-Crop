"""Construct an enclosing strip without inventing a measured physical line.

Inputs are outward half-plane limits, not aperture observations. The returned
slope minimizes strip area on the supplied trace domain; it has no photo-role,
material, placement-direction, or deskew authority. Those permissions belong
to the caller's independently verified evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...domain import FiniteInterval


@dataclass(frozen=True)
class EnclosureConstructionWork:
    input_constraint_count: int
    hull_line_count: int
    hull_pop_count: int
    evaluated_slope_count: int
    raw_recheck_count: int

    def __post_init__(self) -> None:
        if (
            any(type(value) is not int or value < 0 for value in vars(self).values())
            or self.input_constraint_count < 4
            or self.hull_line_count + self.hull_pop_count != self.input_constraint_count
            or not 1 <= self.evaluated_slope_count <= self.hull_line_count + 2
            or self.raw_recheck_count != self.input_constraint_count
        ):
            raise ValueError("enclosure work must preserve every input constraint")


@dataclass(frozen=True)
class ConstructedCrossEnclosure:
    """A chosen output geometry, explicitly distinct from PhysicalLineRegion."""

    reference_trace_px: float
    slope: float
    minimum_position_px: float
    maximum_position_px: float
    minimizing_slope_interval: FiniteInterval
    work: EnclosureConstructionWork

    def __post_init__(self) -> None:
        if (
            any(not math.isfinite(value) for value in (
                self.reference_trace_px, self.slope,
                self.minimum_position_px, self.maximum_position_px,
            ))
            or self.minimum_position_px >= self.maximum_position_px
            or not isinstance(self.minimizing_slope_interval, FiniteInterval)
            or not self.minimizing_slope_interval.contains(self.slope)
            or not isinstance(self.work, EnclosureConstructionWork)
        ):
            raise ValueError("constructed enclosure requires finite outward geometry")

    def at_trace(self, trace_px: float) -> FiniteInterval:
        if not math.isfinite(trace_px):
            raise ValueError("enclosure projection requires a finite trace")
        shift = self.slope * (trace_px - self.reference_trace_px)
        return FiniteInterval(
            self.minimum_position_px + shift,
            self.maximum_position_px + shift,
        )


@dataclass(frozen=True)
class _UpperHull:
    slopes: np.ndarray
    intercepts: np.ndarray
    starts: np.ndarray
    pop_count: int

    def values(self, positions: np.ndarray) -> np.ndarray:
        indices = np.searchsorted(self.starts, positions, side="right") - 1
        return self.slopes[indices] * positions + self.intercepts[indices]


def _upper_hull(slopes: np.ndarray, intercepts: np.ndarray) -> _UpperHull:
    """Increasing slopes: each input enters and leaves the stack at most once."""

    retained: list[int] = []
    starts: list[float] = []
    popped = 0
    for index in range(len(slopes)):
        begin = -math.inf
        while retained:
            previous = retained[-1]
            begin = float(
                (intercepts[previous] - intercepts[index])
                / (slopes[index] - slopes[previous])
            )
            if begin > starts[-1]:
                break
            retained.pop()
            starts.pop()
            popped += 1
        if not retained:
            begin = -math.inf
        retained.append(index)
        starts.append(begin)
    indices = np.asarray(retained, dtype=np.int64)
    return _UpperHull(slopes[indices], intercepts[indices], np.asarray(starts), popped)


def _constraints(values: tuple[tuple[float, float], ...]) -> np.ndarray:
    points = np.asarray(values, dtype=np.float64)
    if (
        points.ndim != 2
        or points.shape[1] != 2
        or len(points) < 2
        or not np.all(np.isfinite(points))
        or not np.all(np.diff(points[:, 0]) > 0.0)
    ):
        raise ValueError("enclosure limits require ordered, unique, finite trace points")
    return points


def construct_cross_enclosure(
    minimum_limits: tuple[tuple[float, float], ...],
    maximum_limits: tuple[tuple[float, float], ...],
    *,
    reference_trace_px: float,
    slope_interval: FiniteInterval,
    outward_guard_px: float,
) -> ConstructedCrossEnclosure:
    """Enclose every supplied limit with two parallel affine output boundaries.

Each minimum boundary must be <= its limit minus guard; each maximum boundary
must be >= its limit plus guard. Both sides must cover the same trace endpoints.
Their interior trace positions may differ. No point is dropped or selected by
strength. A flat area minimum chooses the smallest absolute rotation.

The two upper hulls take linear stack work; sorting their combined breakpoints
costs O(N log N). Full raw rechecking protects against hull roundoff. Finite
input limits and a finite direction range are mandatory, not inferred here.
"""

    if (
        not math.isfinite(reference_trace_px)
        or not isinstance(slope_interval, FiniteInterval)
        or not math.isfinite(outward_guard_px)
        or outward_guard_px < 0.0
    ):
        raise ValueError("enclosure construction requires finite direction and guard")
    lower = _constraints(minimum_limits)
    upper = _constraints(maximum_limits)
    if not np.array_equal(lower[[0, -1], 0], upper[[0, -1], 0]):
        raise ValueError("both enclosing sides must cover the same trace domain")
    lower_delta = lower[:, 0] - reference_trace_px
    upper_delta = upper[:, 0] - reference_trace_px
    if (
        not np.all(np.isfinite(lower_delta))
        or not np.all(np.isfinite(upper_delta))
        or not np.all(np.diff(lower_delta) > 0.0)
        or not np.all(np.diff(upper_delta) > 0.0)
    ):
        raise ValueError("enclosure reference loses finite trace resolution")
    low_hull = _upper_hull(lower_delta, -lower[:, 1])
    high_hull = _upper_hull(-upper_delta[::-1], upper[::-1, 1])
    starts = np.concatenate((low_hull.starts, high_hull.starts))
    starts = starts[
        (starts >= slope_interval.minimum) & (starts <= slope_interval.maximum)
    ]
    candidates = np.unique(
        np.r_[slope_interval.minimum, starts, slope_interval.maximum]
    )
    widths = low_hull.values(candidates) + high_hull.values(candidates)
    if not np.all(np.isfinite(widths)):
        raise ValueError("enclosure geometry exceeded finite numerical range")
    optimum = float(np.min(widths))
    # This tolerance only absorbs arithmetic error in a constructed output.
    # It is not a material tolerance, a measured angle interval, or a budget.
    roundoff = 8.0 * np.finfo(np.float64).eps * max(1.0, float(np.max(np.abs(widths))))
    optimal = candidates[np.abs(widths - optimum) <= roundoff]
    minimizing = FiniteInterval(float(optimal[0]), float(optimal[-1]))
    slope = min(minimizing.maximum, max(minimizing.minimum, 0.0))
    minimum_position = float(np.min(lower[:, 1] - slope * lower_delta)) - outward_guard_px
    maximum_position = float(np.max(upper[:, 1] - slope * upper_delta)) + outward_guard_px
    if minimum_position >= maximum_position:
        raise ValueError("enclosure limits do not define a positive strip")
    # Use the complete constraints for the final coordinates, then move only
    # outward by a floating-point bound. Never accept an inward epsilon.
    coordinate_scale = max(
        1.0, abs(minimum_position), abs(maximum_position),
        float(np.max(np.abs(slope * lower_delta))),
        float(np.max(np.abs(slope * upper_delta))),
    )
    coordinate_roundoff = 8.0 * np.finfo(np.float64).eps * coordinate_scale
    minimum_position -= coordinate_roundoff
    maximum_position += coordinate_roundoff
    if (
        not math.isfinite(minimum_position)
        or not math.isfinite(maximum_position)
        or minimum_position >= maximum_position
        or np.any(minimum_position + slope * lower_delta > lower[:, 1] - outward_guard_px)
        or np.any(maximum_position + slope * upper_delta < upper[:, 1] + outward_guard_px)
    ):
        raise ValueError("constructed enclosure failed complete outward recheck")
    count = len(lower) + len(upper)
    return ConstructedCrossEnclosure(
        reference_trace_px, slope, minimum_position, maximum_position, minimizing,
        EnclosureConstructionWork(
            input_constraint_count=count,
            hull_line_count=len(low_hull.starts) + len(high_hull.starts),
            hull_pop_count=low_hull.pop_count + high_hull.pop_count,
            evaluated_slope_count=len(candidates),
            raw_recheck_count=count,
        ),
    )
