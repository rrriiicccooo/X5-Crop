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

    def __post_init__(self) -> None:
        values = (
            self.sequence_start_px,
            self.sequence_end_px,
            self.top_at_lane_reference_px,
            self.bottom_at_lane_reference_px,
            self.angle_degrees,
        )
        if any(not math.isfinite(value) for value in values):
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
            > _MAX_SUPPORT_EVALUATIONS * (len(self.frame_states) + 1)
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
            sequence.role_full_position_intervals_px,
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


def _cross_vertices(
    placement: FormatPlacement,
) -> tuple[tuple[tuple[float, float], ...], int]:
    cross = placement.cross_fit
    top = _LinearExpression(np.asarray((1.0, 0.0)), 0.0)
    bottom = _LinearExpression(np.asarray((1.0, 1.0)), 0.0)
    if cross.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR:
        support = cross.enclosing_support_pair
        if support is None:
            raise ValueError("enclosing output requires its direct support pair")
        bounds = (
            (
                support.top_full_interval_px.minimum,
                support.top_full_interval_px.maximum,
            ),
            (
                support.observed_span_px.minimum,
                support.observed_span_px.maximum,
            ),
        )
        intervals = (
            (top, support.top_full_interval_px),
            (bottom, support.bottom_full_interval_px),
        )
    else:
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


def project_selected_placement(
    placement: FormatPlacement,
) -> FeasiblePlacementProjection:
    """Project one placement into bounded same-state frame geometry."""

    if not isinstance(placement, FormatPlacement):
        raise TypeError("joint projection requires a selected placement")
    sequence_system, roles = _sequence_system(placement)
    cross_vertices, evaluation_count = _cross_vertices(placement)
    angles = tuple(
        dict.fromkeys(
            (
                placement.direction.full_angle_interval_degrees.minimum,
                placement.direction.canonical_angle_degrees,
                placement.direction.full_angle_interval_degrees.maximum,
            )
        )
    )
    frames: list[tuple[JointFrameState, ...]] = []
    for ordinal in range(placement.output_slot_count):
        sequence_vertices, evaluations = _project_pair_vertices(
            sequence_system,
            roles[2 * ordinal],
            roles[2 * ordinal + 1],
        )
        evaluation_count += evaluations
        states = tuple(
            JointFrameState(start, end, top, bottom, angle)
            for start, end in sequence_vertices
            for top, bottom in cross_vertices
            for angle in angles
        )
        if not states:
            raise ValueError("selected placement projected no feasible frame state")
        frames.append(states)
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
