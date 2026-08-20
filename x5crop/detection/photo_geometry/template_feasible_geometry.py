"""Joint continuous states for one already-selected template placement."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import linprog

from ...domain import FiniteInterval
from ...run_local_identity import run_local_id
from .model import BoundaryRole
from .output_model import OutputBoundaryUse
from .template_placement import FormatPlacement


_INITIAL_SUPPORT_DIRECTIONS = (
    (1.0, 0.0),
    (-1.0, 0.0),
    (0.0, 1.0),
    (0.0, -1.0),
    (1.0, 1.0),
    (1.0, -1.0),
    (-1.0, 1.0),
    (-1.0, -1.0),
)
_MAX_SUPPORT_EVALUATIONS = 64
_MAX_PROJECTED_VERTICES = 32
_GEOMETRY_EPSILON = 1.0e-7


@dataclass(frozen=True)
class JointFrameState:
    """One feasible low-dimensional state for all four frame boundaries."""

    sequence_start_px: float
    sequence_end_px: float
    top_at_lane_reference_px: float
    bottom_at_lane_reference_px: float
    angle_degrees: float
    sequence_start_model_residual_px: float
    sequence_end_model_residual_px: float

    def __post_init__(self) -> None:
        values = (
            self.sequence_start_px,
            self.sequence_end_px,
            self.top_at_lane_reference_px,
            self.bottom_at_lane_reference_px,
            self.angle_degrees,
            self.sequence_start_model_residual_px,
            self.sequence_end_model_residual_px,
        )
        if any(not math.isfinite(value) for value in values) or any(
            value < 0.0
            for value in (
                self.sequence_start_model_residual_px,
                self.sequence_end_model_residual_px,
            )
        ):
            raise ValueError("joint frame state must be finite")


@dataclass(frozen=True)
class FeasiblePlacementProjection:
    """Bounded joint states from one shared feasible parameter set."""

    projection_id: str
    placement_id: str
    frame_states: tuple[tuple[JointFrameState, ...], ...]
    extreme_evaluation_count: int

    def __post_init__(self) -> None:
        if (
            not self.projection_id
            or not self.placement_id
            or not self.frame_states
            or any(not states for states in self.frame_states)
            or self.extreme_evaluation_count <= 0
            or self.extreme_evaluation_count
            > (
                (2 * _MAX_SUPPORT_EVALUATIONS + 2)
                * len(self.frame_states)
                + _MAX_SUPPORT_EVALUATIONS
            )
        ):
            raise ValueError("feasible placement projection is invalid")


@dataclass(frozen=True)
class _LinearExpression:
    coefficients: np.ndarray
    constant: float

    def value(self, solution: np.ndarray) -> float:
        return self.constant + float(self.coefficients @ solution)


@dataclass(frozen=True)
class _FeasibleSystem:
    bounds: tuple[tuple[float, float], ...]
    inequalities: tuple[np.ndarray, np.ndarray]


def _constraints(
    expressions: tuple[tuple[_LinearExpression, FiniteInterval], ...],
) -> tuple[np.ndarray, np.ndarray]:
    rows: list[np.ndarray] = []
    limits: list[float] = []
    for expression, interval in expressions:
        coefficients = expression.coefficients
        constant = expression.constant
        rows.extend((coefficients, -coefficients))
        limits.extend((interval.maximum - constant, constant - interval.minimum))
    return np.asarray(rows, dtype=np.float64), np.asarray(limits, dtype=np.float64)


def _point_key(point: tuple[float, float]) -> tuple[int, int]:
    return round(point[0] / _GEOMETRY_EPSILON), round(
        point[1] / _GEOMETRY_EPSILON
    )


def _ordered_hull(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    unique = sorted({_point_key(point): point for point in points}.values())
    if len(unique) <= 2:
        return tuple(unique)

    def cross(
        origin: tuple[float, float],
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return (
            (left[0] - origin[0]) * (right[1] - origin[1])
            - (left[1] - origin[1]) * (right[0] - origin[0])
        )

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def _support_point(
    system: _FeasibleSystem,
    first: _LinearExpression,
    second: _LinearExpression,
    direction: tuple[float, float],
) -> tuple[float, float]:
    objective = -(
        direction[0] * first.coefficients
        + direction[1] * second.coefficients
    )
    result = linprog(
        objective,
        A_ub=system.inequalities[0],
        b_ub=system.inequalities[1],
        bounds=system.bounds,
        method="highs",
    )
    if not result.success or result.x is None:
        raise ValueError("selected placement has no joint feasible state")
    solution = np.asarray(result.x, dtype=np.float64)
    return first.value(solution), second.value(solution)


def _support_solution(
    system: _FeasibleSystem,
    first: _LinearExpression,
    second: _LinearExpression,
    direction: tuple[float, float],
) -> tuple[tuple[float, float], np.ndarray]:
    objective = -(
        direction[0] * first.coefficients
        + direction[1] * second.coefficients
    )
    result = linprog(
        objective,
        A_ub=system.inequalities[0],
        b_ub=system.inequalities[1],
        bounds=system.bounds,
        method="highs",
    )
    if not result.success or result.x is None:
        raise ValueError("selected placement has no joint feasible state")
    solution = np.asarray(result.x, dtype=np.float64)
    return (first.value(solution), second.value(solution)), solution


def _project_pair_vertices(
    system: _FeasibleSystem,
    first: _LinearExpression,
    second: _LinearExpression,
) -> tuple[tuple[tuple[float, float], ...], int]:
    points: dict[tuple[int, int], tuple[float, float]] = {}
    evaluations = 0

    def query(direction: tuple[float, float]) -> None:
        nonlocal evaluations
        if evaluations >= _MAX_SUPPORT_EVALUATIONS:
            raise ValueError("joint feasible projection exceeded its work bound")
        point = _support_point(system, first, second, direction)
        points[_point_key(point)] = point
        evaluations += 1

    for direction in _INITIAL_SUPPORT_DIRECTIONS:
        query(direction)
    while True:
        hull = _ordered_hull(tuple(points.values()))
        if len(hull) <= 2:
            return hull, evaluations
        added = False
        for left, right in zip(hull, (*hull[1:], hull[0]), strict=True):
            if evaluations >= _MAX_SUPPORT_EVALUATIONS:
                raise ValueError("joint feasible projection exceeded its work bound")
            edge_x = right[0] - left[0]
            edge_y = right[1] - left[1]
            norm = math.hypot(edge_x, edge_y)
            if norm <= _GEOMETRY_EPSILON:
                continue
            outward = (edge_y / norm, -edge_x / norm)
            candidate = _support_point(system, first, second, outward)
            evaluations += 1
            edge_support = outward[0] * left[0] + outward[1] * left[1]
            candidate_support = (
                outward[0] * candidate[0] + outward[1] * candidate[1]
            )
            if candidate_support > edge_support + _GEOMETRY_EPSILON:
                points[_point_key(candidate)] = candidate
                added = True
                if len(points) > _MAX_PROJECTED_VERTICES:
                    raise ValueError(
                        "joint feasible projection exceeded its vertex bound"
                    )
        if not added:
            return _ordered_hull(tuple(points.values())), evaluations


def _project_pair_solutions(
    system: _FeasibleSystem,
    first: _LinearExpression,
    second: _LinearExpression,
) -> tuple[tuple[np.ndarray, ...], int]:
    """Retain the shared parameter solution behind every projected vertex."""

    solutions: dict[tuple[int, int], np.ndarray] = {}
    points: dict[tuple[int, int], tuple[float, float]] = {}
    evaluations = 0

    def query(direction: tuple[float, float]) -> None:
        nonlocal evaluations
        if evaluations >= _MAX_SUPPORT_EVALUATIONS:
            raise ValueError("joint feasible projection exceeded its work bound")
        point, solution = _support_solution(system, first, second, direction)
        key = _point_key(point)
        points[key] = point
        solutions[key] = solution
        evaluations += 1

    for direction in _INITIAL_SUPPORT_DIRECTIONS:
        query(direction)
    while True:
        hull = _ordered_hull(tuple(points.values()))
        if len(hull) <= 2:
            keys = tuple(_point_key(point) for point in hull)
            return tuple(solutions[key] for key in keys), evaluations
        added = False
        for left, right in zip(hull, (*hull[1:], hull[0]), strict=True):
            if evaluations >= _MAX_SUPPORT_EVALUATIONS:
                raise ValueError("joint feasible projection exceeded its work bound")
            edge_x = right[0] - left[0]
            edge_y = right[1] - left[1]
            norm = math.hypot(edge_x, edge_y)
            if norm <= _GEOMETRY_EPSILON:
                continue
            outward = (edge_y / norm, -edge_x / norm)
            candidate, solution = _support_solution(
                system,
                first,
                second,
                outward,
            )
            evaluations += 1
            edge_support = outward[0] * left[0] + outward[1] * left[1]
            candidate_support = (
                outward[0] * candidate[0] + outward[1] * candidate[1]
            )
            if candidate_support > edge_support + _GEOMETRY_EPSILON:
                key = _point_key(candidate)
                points[key] = candidate
                solutions[key] = solution
                added = True
                if len(points) > _MAX_PROJECTED_VERTICES:
                    raise ValueError(
                        "joint feasible projection exceeded its vertex bound"
                    )
        if not added:
            keys = tuple(_point_key(point) for point in _ordered_hull(tuple(points.values())))
            return tuple(solutions[key] for key in keys), evaluations


def _sequence_model_residuals(
    placement: FormatPlacement,
    roles: tuple[_LinearExpression, ...],
    solution: np.ndarray,
    frame_index: int,
) -> tuple[float, float]:
    """Measure local direct residuals and bounded inferred-edge inheritance."""

    direction = placement.sequence_fit.template.direction
    by_role: dict[BoundaryRole, list[tuple[int, float]]] = {
        BoundaryRole.START: [],
        BoundaryRole.END: [],
    }
    for index, (expression, interval, observation_id) in enumerate(
        zip(
            roles,
            placement.sequence_fit.role_full_position_intervals_px,
            placement.sequence_fit.role_observation_ids,
            strict=True,
        )
    ):
        if observation_id is None:
            continue
        predicted = expression.value(solution)
        if index % 2 == 0:
            role = BoundaryRole.START
            outward = interval.minimum if direction > 0 else interval.maximum
            residual = (
                predicted - outward
                if direction > 0
                else outward - predicted
            )
        else:
            role = BoundaryRole.END
            outward = interval.maximum if direction > 0 else interval.minimum
            residual = (
                outward - predicted
                if direction > 0
                else predicted - outward
            )
        by_role[role].append((index, max(0.0, residual)))

    def selected(role: BoundaryRole, role_index: int) -> float:
        direct = dict(by_role[role])
        if role_index in direct:
            return direct[role_index]
        # A missing edge still represents one fixed-format frame. Its local
        # straight-model departure is bounded by the nearest direct occurrence
        # of the same physical role on either side; a remote outlier elsewhere
        # on the strip is not copied into this frame. Width already varies in
        # this joint solution and must not be added again as an independent
        # maximum.
        left = tuple(
            value for index, value in direct.items() if index < role_index
        )
        right = tuple(
            value for index, value in direct.items() if index > role_index
        )
        neighbours = (
            *((left[-1],) if left else ()),
            *((right[0],) if right else ()),
        )
        return max(neighbours, default=0.0)

    return (
        selected(BoundaryRole.START, 2 * frame_index),
        selected(BoundaryRole.END, 2 * frame_index + 1),
    )


def _sequence_system(
    placement: FormatPlacement,
) -> tuple[_FeasibleSystem, tuple[_LinearExpression, ...]]:
    sequence = placement.sequence_fit
    lattice = sequence.phase_lattice_fit
    relations = sequence.local_advance_relations
    variable_count = 3 + len(relations)
    bounds = (
        (
            lattice.cycle_phase_interval_px.minimum,
            lattice.cycle_phase_interval_px.maximum,
        ),
        (
            sequence.pitch_fit.frame_width_px.minimum,
            sequence.pitch_fit.frame_width_px.maximum,
        ),
        (
            sequence.pitch_fit.pitch_interval_px.minimum,
            sequence.pitch_fit.pitch_interval_px.maximum,
        ),
        *tuple(
            (item.delta_interval_px.minimum, item.delta_interval_px.maximum)
            for item in relations
        ),
    )
    origin = lattice.authority.cycle_origin_px
    direction = lattice.direction
    offset = lattice.integer_slot_offset

    def role_expression(role_index: int) -> _LinearExpression:
        role = sequence.template.roles[role_index]
        values = np.zeros(variable_count, dtype=np.float64)
        values[0] = direction
        values[1] = direction if role.role == BoundaryRole.END else 0.0
        values[2] = direction * (offset + role.slot_index)
        for relation_index in range(min(role.slot_index, len(relations))):
            values[3 + relation_index] = direction
        return _LinearExpression(values, origin)

    roles = tuple(
        role_expression(index) for index in range(2 * sequence.template.count)
    )
    absolute_phase = np.zeros(variable_count, dtype=np.float64)
    absolute_phase[0] = direction
    absolute_phase[2] = direction * offset
    gap = np.zeros(variable_count, dtype=np.float64)
    gap[1] = -1.0
    gap[2] = 1.0
    constraints = tuple(
        (expression, interval)
        for expression, interval in zip(
            roles,
            sequence.role_positions_px,
            strict=True,
        )
    ) + (
        (
            _LinearExpression(absolute_phase, origin),
            lattice.absolute_phase_interval_px,
        ),
        (_LinearExpression(gap, 0.0), sequence.pitch_fit.gap_interval_px),
    )
    return _FeasibleSystem(bounds, _constraints(constraints)), roles


def _aperture_cross_vertices(
    placement: FormatPlacement,
) -> tuple[tuple[tuple[float, float], ...], int]:
    cross = placement.cross_fit
    top = _LinearExpression(np.asarray((1.0, 0.0)), 0.0)
    bottom = _LinearExpression(np.asarray((1.0, 1.0)), 0.0)
    if cross.boundary_use != OutputBoundaryUse.APERTURE_PAIR:
        raise ValueError("aperture projection cannot consume support geometry")
    bounds = (
        (
            cross.top_full_interval_px.minimum,
            cross.top_full_interval_px.maximum,
        ),
        (
            cross.fixed_height_px.minimum,
            cross.fixed_height_px.maximum,
        ),
    )
    intervals = (
        (top, cross.top_full_interval_px),
        (bottom, cross.bottom_full_interval_px),
    )
    return _project_pair_vertices(
        _FeasibleSystem(bounds, _constraints(intervals)),
        top,
        bottom,
    )


def _support_system(
    placement: FormatPlacement,
) -> _FeasibleSystem:
    support = placement.cross_fit.enclosing_support_pair
    if support is None:
        raise ValueError("enclosing output requires its direct support pair")
    direction = placement.direction.full_angle_interval_degrees
    bounds = (
        (
            support.top_full_interval_px.minimum,
            support.top_full_interval_px.maximum,
        ),
        (
            support.bottom_full_interval_px.minimum,
            support.bottom_full_interval_px.maximum,
        ),
        (
            math.tan(math.radians(direction.minimum)),
            math.tan(math.radians(direction.maximum)),
        ),
    )
    top_reference = _LinearExpression(np.asarray((1.0, 0.0, 0.0)), 0.0)
    bottom_reference = _LinearExpression(np.asarray((0.0, 1.0, 0.0)), 0.0)
    span = _LinearExpression(np.asarray((-1.0, 1.0, 0.0)), 0.0)
    constraints: list[tuple[_LinearExpression, FiniteInterval]] = [
        (top_reference, support.top_full_interval_px),
        (bottom_reference, support.bottom_full_interval_px),
        (span, support.observed_span_px),
    ]
    for trace, top_interval, bottom_interval in zip(
        support.trace_coordinates_px,
        support.top_trace_intervals_px,
        support.bottom_trace_intervals_px,
        strict=True,
    ):
        distance = float(trace) - support.reference_trace_px
        top_feasible = FiniteInterval(
            top_interval.minimum
            - support.top_straight_model_residual_px,
            top_interval.maximum
            + support.top_straight_model_residual_px,
        )
        bottom_feasible = FiniteInterval(
            bottom_interval.minimum
            - support.bottom_straight_model_residual_px,
            bottom_interval.maximum
            + support.bottom_straight_model_residual_px,
        )
        constraints.extend(
            (
                (
                    _LinearExpression(
                        np.asarray((1.0, 0.0, distance)),
                        0.0,
                    ),
                    top_feasible,
                ),
                (
                    _LinearExpression(
                        np.asarray((0.0, 1.0, distance)),
                        0.0,
                    ),
                    bottom_feasible,
                ),
            )
        )
    return _FeasibleSystem(bounds, _constraints(tuple(constraints)))


def _support_cross_states(
    placement: FormatPlacement,
    system: _FeasibleSystem,
    target_trace_px: float,
) -> tuple[tuple[tuple[float, float, float], ...], int]:
    support = placement.cross_fit.enclosing_support_pair
    if support is None:
        raise ValueError("support projection lost its direct authority")
    distance = target_trace_px - support.reference_trace_px
    top_at_target = _LinearExpression(
        np.asarray((1.0, 0.0, distance)),
        0.0,
    )
    bottom_at_target = _LinearExpression(
        np.asarray((0.0, 1.0, distance)),
        0.0,
    )
    solutions, evaluations = _project_pair_solutions(
        system,
        top_at_target,
        bottom_at_target,
    )
    slope = _LinearExpression(np.asarray((0.0, 0.0, 1.0)), 0.0)
    zero = _LinearExpression(np.zeros(3, dtype=np.float64), 0.0)
    slope_solutions = tuple(
        _support_solution(system, slope, zero, direction)[1]
        for direction in ((1.0, 0.0), (-1.0, 0.0))
    )
    evaluations += len(slope_solutions)
    unique = {
        tuple(round(float(value), 12) for value in solution): solution
        for solution in (*solutions, *slope_solutions)
    }
    return (
        tuple(
            (
                float(solution[0]),
                float(solution[1]),
                math.degrees(math.atan(float(solution[2]))),
            )
            for solution in unique.values()
        ),
        evaluations,
    )


def project_selected_placement(
    placement: FormatPlacement,
) -> FeasiblePlacementProjection:
    """Project one placement into bounded same-state frame geometry."""

    if not isinstance(placement, FormatPlacement):
        raise TypeError("joint projection requires a selected placement")
    sequence_system, roles = _sequence_system(placement)
    support_system = (
        _support_system(placement)
        if placement.cross_fit.boundary_use
        == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        else None
    )
    if support_system is None:
        cross_vertices, evaluation_count = _aperture_cross_vertices(placement)
        angles = tuple(
            dict.fromkeys(
                (
                    placement.direction.full_angle_interval_degrees.minimum,
                    placement.direction.canonical_angle_degrees,
                    placement.direction.full_angle_interval_degrees.maximum,
                )
            )
        )
        aperture_states = tuple(
            (top, bottom, angle)
            for top, bottom in cross_vertices
            for angle in angles
        )
    else:
        evaluation_count = 0
        aperture_states = ()
    frames: list[tuple[JointFrameState, ...]] = []
    for ordinal in range(placement.output_slot_count):
        sequence_solutions, evaluations = _project_pair_solutions(
            sequence_system,
            roles[2 * ordinal],
            roles[2 * ordinal + 1],
        )
        evaluation_count += evaluations
        if support_system is None:
            cross_states = aperture_states
        else:
            cross_states, evaluations = _support_cross_states(
                placement,
                support_system,
                placement.frames[ordinal].top.reference_trace_px,
            )
            evaluation_count += evaluations
        states = []
        for solution in sequence_solutions:
            start = roles[2 * ordinal].value(solution)
            end = roles[2 * ordinal + 1].value(solution)
            start_residual, end_residual = _sequence_model_residuals(
                placement,
                roles,
                solution,
                ordinal,
            )
            states.extend(
                JointFrameState(
                    start,
                    end,
                    top,
                    bottom,
                    angle,
                    start_residual,
                    end_residual,
                )
                for top, bottom, angle in cross_states
            )
        if not states:
            raise ValueError("selected placement projected no feasible frame state")
        frames.append(tuple(states))
    return FeasiblePlacementProjection(
        projection_id=run_local_id(
            "joint-placement-projection",
            placement.placement_id,
        ),
        placement_id=placement.placement_id,
        frame_states=tuple(frames),
        extreme_evaluation_count=evaluation_count,
    )


__all__ = [
    "FeasiblePlacementProjection",
    "JointFrameState",
    "project_selected_placement",
]
