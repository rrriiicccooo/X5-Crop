"""Robust representative lines for already-bound transition families."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy.optimize import least_squares

from ...domain import FiniteInterval
from ...geometry.convex import convex_hull
from .measurement_points import TransitionPoint
from .line_observations import (
    CompleteTransitionLineEvaluation,
    CompleteTransitionLineFailureKind,
    CompleteTransitionLineSolution,
    CompleteTransitionLineWork,
    ConstrainedLineFitReceipt,
    PhysicalLineRegion,
    RobustLineFitReceipt,
)
from .model import PhotoBoundaryMeasurementSpec


# Existing closed-set arithmetic allowance, not additional physical support.
LINE_REGION_ARITHMETIC_EPSILON_PX = 1.0e-9


@dataclass(frozen=True)
class TransitionLineFit:
    slope: float
    intercept: float
    residuals: np.ndarray
    selected_points: tuple[TransitionPoint, ...]
    receipt: RobustLineFitReceipt | ConstrainedLineFitReceipt


def _clip_line_region(
    vertices: tuple[tuple[float, float], ...],
    position_coefficient: float,
    slope_coefficient: float,
    limit: float,
    *,
    _work: dict[str, int] | None = None,
) -> tuple[tuple[float, float], ...]:
    """Intersect a bounded line-parameter region with one closed half-plane."""

    if _work is not None:
        _work["polygon_clip_count"] += 1
    if not vertices:
        return ()
    result: list[tuple[float, float]] = []

    def append(point: tuple[float, float]) -> None:
        if not result or point != result[-1]:
            result.append(point)

    def distance(point: tuple[float, float]) -> float:
        if _work is not None:
            _work["polygon_vertex_evaluation_count"] += 1
        value = (
            position_coefficient * point[0]
            + slope_coefficient * point[1]
            - limit
        )
        # The existing coordinate contract admits 1e-9 px arithmetic error.
        # Keep a closed-set vertex when cancellation lands on its boundary.
        return 0.0 if abs(value) <= LINE_REGION_ARITHMETIC_EPSILON_PX else value

    previous = vertices[-1]
    previous_value = distance(previous)
    for current in vertices:
        current_value = distance(current)
        if (previous_value <= 0.0) != (current_value <= 0.0):
            fraction = previous_value / (previous_value - current_value)
            append((
                previous[0] + fraction * (current[0] - previous[0]),
                previous[1] + fraction * (current[1] - previous[1]),
            ))
        if current_value <= 0.0:
            append(current)
        previous = current
        previous_value = current_value
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return tuple(result)


def physical_line_region(
    trace_intervals: tuple[tuple[float, FiniteInterval], ...],
    maximum_slope: float,
    reference_trace_px: float,
) -> PhysicalLineRegion | None:
    """Retain all raw-physical straight-line states without another fit or LP.

    The first trace and the existing slope cap provide a bounded superset.
    Each of the 2N closed half-planes adds at most one vertex: O(N**2)
    work and O(N) storage, including valid point and segment degeneracies.
    Connection allowance does not make an infeasible physical family close.
    """

    return _physical_line_region(trace_intervals, maximum_slope, reference_trace_px)


def _physical_line_region(
    trace_intervals: tuple[tuple[float, FiniteInterval], ...],
    maximum_slope: float,
    reference_trace_px: float,
    *,
    work: dict[str, int] | None = None,
) -> PhysicalLineRegion | None:
    """Shared clipping owner; optional counters do not alter its arithmetic."""

    if (
        not trace_intervals
        or not math.isfinite(maximum_slope)
        or maximum_slope <= 0.0
        or not math.isfinite(reference_trace_px)
        or any(not math.isfinite(trace) for trace, _ in trace_intervals)
    ):
        raise ValueError("physical line inputs are invalid")
    first_trace, interval = trace_intervals[0]
    allowance = maximum_slope * abs(first_trace - reference_trace_px)
    minimum = interval.minimum - allowance
    maximum = interval.maximum + allowance
    vertices = (
        (minimum, -maximum_slope),
        (maximum, -maximum_slope),
        (maximum, maximum_slope),
        (minimum, maximum_slope),
    )
    for trace, interval in trace_intervals:
        distance = trace - reference_trace_px
        vertices = _clip_line_region(vertices, 1.0, distance, interval.maximum, _work=work)
        vertices = _clip_line_region(vertices, -1.0, -distance, -interval.minimum, _work=work)
        if not vertices:
            return None
    return PhysicalLineRegion(reference_trace_px, vertices)


def _huber_edge_minimum(
    residuals: tuple[float, ...],
    changes: tuple[float, ...],
    delta: float,
    work: dict[str, int],
) -> float:
    """Minimize one closed edge using at most two kink events per point."""

    work["edge_count"] += 1
    work["gradient_point_evaluation_count"] += len(residuals)
    derivative = math.fsum(
        change * min(delta, max(-delta, residual))
        for residual, change in zip(residuals, changes, strict=True)
    )
    if derivative >= 0.0:
        return 0.0
    active: list[float] = []
    events: list[tuple[float, float, int]] = []
    for residual, change in zip(residuals, changes, strict=True):
        if change == 0.0:
            continue
        entry, leave = sorted(((-delta - residual) / change, (delta - residual) / change))
        square = change * change
        if entry <= 0.0 < leave:
            active.append(square)
        if 0.0 < entry < 1.0:
            events.append((entry, square, 1))
        if 0.0 < leave < 1.0:
            events.append((leave, -square, -1))
    work["event_count"] += len(events)
    events.sort()
    curvature = math.fsum(active)
    active_count = len(active)
    previous = 0.0
    index = 0
    while index < len(events):
        fraction = events[index][0]
        work["event_visit_count"] += 1
        next_derivative = math.fsum((derivative, curvature * (fraction - previous)))
        if curvature > 0.0 and next_derivative >= 0.0:
            return min(fraction, max(previous, previous - derivative / curvature))
        differences = []
        first_index = index
        while index < len(events) and events[index][0] == fraction:
            differences.append(events[index][1])
            active_count += events[index][2]
            if index != first_index:
                work["event_visit_count"] += 1
            index += 1
        curvature = math.fsum((curvature, *differences)) if active_count else 0.0
        derivative = next_derivative
        previous = fraction
    if curvature > 0.0 and derivative + curvature * (1.0 - previous) >= 0.0:
        return min(1.0, max(previous, previous - derivative / curvature))
    return 1.0


def fit_complete_transition_line(
    points: tuple[TransitionPoint, ...],
    boundary_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    initial_fit: TransitionLineFit | None = None,
) -> CompleteTransitionLineEvaluation:
    """Evaluate a complete raw family on its bounded physical line polygon.

    The equal-weight Huber delta and physical allowance are fixed by the
    original measurement spec. A feasible complete initial fit can supply an
    interior optimum. Otherwise every polygon edge is scanned analytically;
    no optimizer, subset search, or iterative repair is added. If the best
    available candidate fails the full-domain first-order gap, it is withheld.
    This floating-point check is not a directed-rounding certificate.

    For N points, clipping has at most 2N half-planes and V <= 2N+4 vertices;
    the edge sweep costs O(N V log N), with O(N+V) temporary storage. Every
    returned solution is checked against all original raw intervals again.
    """

    work = {name: 0 for name in CompleteTransitionLineWork.__dataclass_fields__}
    work["input_point_count"] = len(points)

    def finish(solution=None, failure=None):
        return CompleteTransitionLineEvaluation(solution, failure, CompleteTransitionLineWork(**work))

    failure = CompleteTransitionLineFailureKind
    if (
        len(points) < 2
        or not isinstance(spec, PhotoBoundaryMeasurementSpec)
        or not math.isfinite(boundary_scale_px_per_mm)
        or boundary_scale_px_per_mm <= 0.0
        or any(
            not isinstance(point, TransitionPoint)
            or not math.isfinite(point.trace)
            or not math.isfinite(point.coordinate)
            or point.trace != point.transition.trace_coordinate_px
            or point.coordinate != point.transition.coordinate_px
            for point in points
        )
        or len({point.transition.transition_id for point in points}) != len(points)
    ):
        return finish(failure=failure.INVALID_INPUT)
    if len({point.trace for point in points}) != len(points):
        return finish(failure=failure.TRACE_IDENTITY_CONFLICT)

    ordered = tuple(sorted(points, key=lambda point: point.trace))
    reference = float(np.median([point.trace for point in ordered]))
    maximum_slope = math.tan(math.radians(spec.maximum_measurable_line_angle_degrees))
    allowance = spec.inlier_minimum_threshold_mm * boundary_scale_px_per_mm
    delta = spec.robust_loss_minimum_scale_mm * boundary_scale_px_per_mm
    if not all(math.isfinite(value) and value > 0.0 for value in (maximum_slope, allowance, delta)):
        return finish(failure=failure.INVALID_INPUT)
    try:
        intervals = tuple((point.trace, FiniteInterval(
            point.transition.physical_position_interval_px.minimum - allowance,
            point.transition.physical_position_interval_px.maximum + allowance,
        )) for point in ordered)
        work["raw_constraint_count"] = 2 * len(intervals)
        region = _physical_line_region(intervals, maximum_slope, reference, work=work)
    except (OverflowError, ValueError):
        return finish(failure=failure.NONFINITE_NUMERICAL_RESULT)
    if region is None:
        return finish(failure=failure.PHYSICAL_REGION_UNAVAILABLE)
    work["polygon_vertex_count"] = len(region.vertices)
    trace_scale = max(point.trace for point in points) - min(point.trace for point in points)
    if not math.isfinite(trace_scale) or trace_scale <= 0.0:
        return finish(failure=failure.NONFINITE_NUMERICAL_RESULT)
    normalized_traces = tuple((point.trace - reference) / trace_scale for point in points)
    vertices = tuple((position, slope * trace_scale) for position, slope in region.vertices)

    def raw_recheck(slope: float, intercept: float) -> bool:
        valid = math.isfinite(slope) and math.isfinite(intercept) and abs(slope) <= maximum_slope
        for trace, interval in intervals:
            work["raw_recheck_point_count"] += 1
            value = math.fsum((slope * trace, intercept))
            point_valid = math.isfinite(value) and interval.contains(
                value, epsilon=LINE_REGION_ARITHMETIC_EPSILON_PX,
            )
            valid = valid and point_valid
        return valid

    def evaluate(slope: float, intercept: float, *, with_gap: bool):
        residuals = tuple(point.coordinate - math.fsum((slope * point.trace, intercept)) for point in points)
        work["loss_point_evaluation_count"] += len(points)
        cost = math.fsum(
            0.5 * residual * residual if abs(residual) <= delta
            else delta * (abs(residual) - 0.5 * delta)
            for residual in residuals
        )
        gap = 0.0
        if with_gap:
            work["gradient_point_evaluation_count"] += len(points)
            clipped = tuple(min(delta, max(-delta, -residual)) for residual in residuals)
            gradient = (
                math.fsum(clipped),
                math.fsum(value * trace for value, trace in zip(clipped, normalized_traces, strict=True)),
            )
            candidate = (math.fsum((intercept, slope * reference)), slope * trace_scale)
            work["gap_vertex_evaluation_count"] += len(vertices)
            gap = max(0.0, max(math.fsum((
                gradient[0] * (candidate[0] - position),
                gradient[1] * (candidate[1] - scaled_slope),
            )) for position, scaled_slope in vertices))
        return CompleteTransitionLineSolution(slope, intercept, residuals, cost, gap)

    def accepted(solution):
        return (
            all(math.isfinite(value) for value in (
                solution.slope, solution.intercept, solution.cost,
                solution.optimality_gap, *solution.residuals,
            ))
            and solution.optimality_gap <= spec.robust_fit_tolerance * solution.cost
            and (solution.cost != 0.0 or all(value == 0.0 for value in solution.residuals))
        )

    best = None
    if isinstance(initial_fit, TransitionLineFit):
        original = {point.transition.transition_id: point for point in points}
        complete_identity = len(initial_fit.selected_points) == len(points)
        checked_ids = set()
        if complete_identity:
            for point in initial_fit.selected_points:
                work["initial_fit_point_check_count"] += 1
                identity = point.transition.transition_id
                complete_identity = complete_identity and original.get(identity) == point and identity not in checked_ids
                checked_ids.add(identity)
        try:
            if (
                complete_identity
                and math.isfinite(initial_fit.slope)
                and math.isfinite(initial_fit.intercept)
                and raw_recheck(initial_fit.slope, initial_fit.intercept)
            ):
                work["candidate_count"] += 1
                best = evaluate(initial_fit.slope, initial_fit.intercept, with_gap=True)
                if accepted(best):
                    return finish(solution=best)
        except (OverflowError, ValueError):
            return finish(failure=failure.NONFINITE_NUMERICAL_RESULT)
    try:
        for index, left in enumerate(vertices):
            right = vertices[(index + 1) % len(vertices)]
            residuals = tuple(math.fsum((left[0], left[1] * trace, -point.coordinate))
                              for point, trace in zip(points, normalized_traces, strict=True))
            changes = tuple(math.fsum((right[0] - left[0], (right[1] - left[1]) * trace))
                            for trace in normalized_traces)
            fraction = _huber_edge_minimum(residuals, changes, delta, work)
            position = left[0] + fraction * (right[0] - left[0])
            left_slope = region.vertices[index][1]
            right_slope = region.vertices[(index + 1) % len(vertices)][1]
            slope = left_slope + fraction * (right_slope - left_slope)
            intercept = position - slope * reference
            work["candidate_count"] += 1
            candidate = evaluate(slope, intercept, with_gap=False)
            if best is None or candidate.cost < best.cost:
                best = candidate
        assert best is not None
        # Re-evaluate the reported native slope/intercept, including all raw
        # loss terms and every vertex of the same complete physical domain.
        best = evaluate(best.slope, best.intercept, with_gap=True)
        if not all(math.isfinite(value) for value in (best.cost, best.optimality_gap, *best.residuals)):
            return finish(failure=failure.NONFINITE_NUMERICAL_RESULT)
        if not raw_recheck(best.slope, best.intercept):
            return finish(failure=failure.RAW_CONSTRAINT_RECHECK_FAILED)
        if not accepted(best):
            return finish(failure=failure.NUMERICAL_OPTIMALITY_UNAVAILABLE)
        return finish(solution=best)
    except (OverflowError, ValueError):
        return finish(failure=failure.NONFINITE_NUMERICAL_RESULT)


def physical_line_region_at_positions(
    region: PhysicalLineRegion,
    offset: FiniteInterval,
    positions: FiniteInterval,
) -> PhysicalLineRegion | None:
    """Project a bounded position offset, then restrict its reachable reference.

    The offset is a protective Minkowski envelope, not an independent width
    measurement. Clipping retains position/slope correlation and legal point
    or segment degeneracies without an additional LP.
    """
    if offset.width == 0.0:
        vertices = tuple((p + offset.minimum, m) for p, m in region.vertices)
    elif len({m for _, m in region.vertices}) == 1:
        slope = region.vertices[0][1]
        vertices = ((min(p for p, _ in region.vertices) + offset.minimum, slope),
                    (max(p for p, _ in region.vertices) + offset.maximum, slope))
    else:
        vertices = convex_hull(tuple(
            (p + value, m) for p, m in region.vertices
            for value in (offset.minimum, offset.maximum)
        ))
    vertices = _clip_line_region(vertices, 1.0, 0.0, positions.maximum)
    vertices = _clip_line_region(vertices, -1.0, 0.0, -positions.minimum)
    return PhysicalLineRegion(region.reference_trace_px, vertices) if vertices else None


def physical_slope_interval(
    points: tuple[TransitionPoint, ...],
    maximum_slope: float,
) -> FiniteInterval | None:
    """Return every straight-line slope allowed by measured intervals."""

    if not points or not math.isfinite(maximum_slope) or maximum_slope <= 0.0:
        raise ValueError("physical slope inputs are invalid")
    minimum = -maximum_slope
    maximum = maximum_slope
    ordered = tuple(sorted(points, key=lambda item: item.trace))
    for index, left in enumerate(ordered):
        left_interval = left.transition.physical_position_interval_px
        for right in ordered[index + 1 :]:
            delta = right.trace - left.trace
            if delta <= 0.0:
                continue
            right_interval = right.transition.physical_position_interval_px
            minimum = max(
                minimum,
                (right_interval.minimum - left_interval.maximum) / delta,
            )
            maximum = min(
                maximum,
                (right_interval.maximum - left_interval.minimum) / delta,
            )
            if minimum > maximum:
                return None
    return FiniteInterval(minimum, maximum)


@lru_cache(maxsize=1024)
def fit_transition_line(
    points: tuple[TransitionPoint, ...],
    boundary_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> TransitionLineFit:
    """Fit one exact candidate-independent family with bounded Huber loss."""

    traces = np.asarray([point.trace for point in points], dtype=np.float64)
    coordinates = np.asarray(
        [point.coordinate for point in points], dtype=np.float64
    )
    trace_reference = float(np.median(traces))
    centered_traces = traces - trace_reference
    design = np.column_stack((centered_traces, np.ones_like(traces)))
    initial, *_unused = np.linalg.lstsq(design, coordinates, rcond=None)
    maximum_slope = math.tan(
        math.radians(spec.maximum_measurable_line_angle_degrees)
    )
    initial[0] = min(maximum_slope, max(-maximum_slope, initial[0]))
    loss_scale = spec.robust_loss_minimum_scale_mm * boundary_scale_px_per_mm
    result = least_squares(
        lambda coefficients: design @ coefficients - coordinates,
        initial,
        jac=lambda _coefficients: design,
        bounds=(
            np.asarray((-maximum_slope, -np.inf), dtype=np.float64),
            np.asarray((maximum_slope, np.inf), dtype=np.float64),
        ),
        method="trf",
        ftol=spec.robust_fit_tolerance,
        xtol=spec.robust_fit_tolerance,
        gtol=spec.robust_fit_tolerance,
        loss="huber",
        f_scale=loss_scale,
        max_nfev=spec.robust_fit_maximum_evaluations,
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise ValueError("robust line fit did not converge")
    slope = float(result.x[0])
    intercept = float(result.x[1] - slope * trace_reference)
    residuals = coordinates - (slope * traces + intercept)
    residuals.flags.writeable = False

    selected: list[TransitionPoint] = []
    for trace in sorted(set(point.trace for point in points)):
        indices = np.flatnonzero(traces == trace)
        best = min(
            indices,
            key=lambda index: (
                abs(float(residuals[index])),
                -(
                    points[int(index)].transition.gradient_z
                    + max(
                        points[int(index)].transition.tone_z,
                        points[int(index)].transition.texture_z,
                    )
                ),
                str(points[int(index)].transition.transition_id),
            ),
        )
        selected.append(points[int(best)])
    if len(selected) != len(points):
        return fit_transition_line(
            tuple(selected), boundary_scale_px_per_mm, spec
        )
    return TransitionLineFit(
        slope=slope,
        intercept=intercept,
        residuals=residuals,
        selected_points=tuple(selected),
        receipt=RobustLineFitReceipt(
            method="scipy_least_squares_huber",
            converged=True,
            status=int(result.status),
            evaluation_count=int(result.nfev),
            cost=float(result.cost),
            optimality=float(result.optimality),
        ),
    )
