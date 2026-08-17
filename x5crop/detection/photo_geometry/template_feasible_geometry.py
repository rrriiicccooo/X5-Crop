"""Joint continuous geometry for one already-selected template placement."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from ...domain import FiniteInterval
from ...run_local_identity import run_local_id
from .model import BoundaryRole
from .output_model import OutputBoundaryUse
from .template_placement import FormatPlacement


@dataclass(frozen=True)
class FeasiblePlacementProjection:
    """Marginal boundary projections from one shared feasible parameter set."""

    projection_id: str
    placement_id: str
    sequence_role_intervals_px: tuple[FiniteInterval, ...]
    top_at_lane_reference_px: FiniteInterval
    bottom_at_lane_reference_px: FiniteInterval
    extreme_evaluation_count: int

    def __post_init__(self) -> None:
        if (
            not self.projection_id
            or not self.placement_id
            or not self.sequence_role_intervals_px
            or not isinstance(self.top_at_lane_reference_px, FiniteInterval)
            or not isinstance(self.bottom_at_lane_reference_px, FiniteInterval)
            or self.extreme_evaluation_count
            != 2 * (len(self.sequence_role_intervals_px) + 2)
        ):
            raise ValueError("feasible placement projection is invalid")


def _constraints(
    expressions: tuple[tuple[np.ndarray, float, FiniteInterval], ...],
) -> tuple[np.ndarray, np.ndarray]:
    rows: list[np.ndarray] = []
    limits: list[float] = []
    for coefficients, constant, interval in expressions:
        rows.extend((coefficients, -coefficients))
        limits.extend((interval.maximum - constant, constant - interval.minimum))
    return np.asarray(rows, dtype=np.float64), np.asarray(limits, dtype=np.float64)


def _extreme_interval(
    coefficients: np.ndarray,
    constant: float,
    *,
    bounds: tuple[tuple[float, float], ...],
    inequalities: tuple[np.ndarray, np.ndarray],
) -> FiniteInterval:
    values: list[float] = []
    for direction in (1.0, -1.0):
        result = linprog(
            direction * coefficients,
            A_ub=inequalities[0],
            b_ub=inequalities[1],
            bounds=bounds,
            method="highs",
        )
        if not result.success or result.fun is None:
            raise ValueError("selected placement has no joint feasible state")
        objective = float(result.fun) / direction
        values.append(constant + objective)
    return FiniteInterval(min(values), max(values))


def _sequence_projection(
    placement: FormatPlacement,
) -> tuple[FiniteInterval, ...]:
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

    def role_expression(role_index: int) -> tuple[np.ndarray, float]:
        role = sequence.template.roles[role_index]
        values = np.zeros(variable_count, dtype=np.float64)
        values[0] = direction
        values[1] = direction if role.role == BoundaryRole.END else 0.0
        values[2] = direction * (offset + role.slot_index)
        for relation_index in range(min(role.slot_index, len(relations))):
            values[3 + relation_index] = direction
        return values, origin

    expressions = tuple(
        (*role_expression(index), interval)
        for index, interval in enumerate(sequence.role_positions_px)
    )
    absolute_phase = np.zeros(variable_count, dtype=np.float64)
    absolute_phase[0] = direction
    absolute_phase[2] = direction * offset
    gap = np.zeros(variable_count, dtype=np.float64)
    gap[1] = -1.0
    gap[2] = 1.0
    inequalities = _constraints(
        (
            *expressions,
            (absolute_phase, origin, lattice.absolute_phase_interval_px),
            (gap, 0.0, sequence.pitch_fit.gap_interval_px),
        )
    )
    return tuple(
        _extreme_interval(
            coefficients,
            constant,
            bounds=bounds,
            inequalities=inequalities,
        )
        for coefficients, constant, _interval in expressions
    )


def _cross_projection(
    placement: FormatPlacement,
) -> tuple[FiniteInterval, FiniteInterval]:
    cross = placement.cross_fit
    if cross.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR:
        support = cross.enclosing_support_pair
        if support is None:
            raise ValueError("enclosing output requires its direct support pair")
        return support.top_full_interval_px, support.bottom_full_interval_px
    bounds = (
        (
            cross.top_full_interval_px.minimum,
            cross.top_full_interval_px.maximum,
        ),
        (cross.fixed_height_px.minimum, cross.fixed_height_px.maximum),
    )
    top = np.asarray((1.0, 0.0), dtype=np.float64)
    bottom = np.asarray((1.0, 1.0), dtype=np.float64)
    inequalities = _constraints(
        (
            (top, 0.0, cross.top_full_interval_px),
            (bottom, 0.0, cross.bottom_full_interval_px),
        )
    )
    return (
        _extreme_interval(top, 0.0, bounds=bounds, inequalities=inequalities),
        _extreme_interval(bottom, 0.0, bounds=bounds, inequalities=inequalities),
    )


def project_selected_placement(
    placement: FormatPlacement,
) -> FeasiblePlacementProjection:
    """Project one placement's correlated low-dimensional feasible set."""

    if not isinstance(placement, FormatPlacement):
        raise TypeError("joint projection requires a selected placement")
    sequence = _sequence_projection(placement)
    top, bottom = _cross_projection(placement)
    return FeasiblePlacementProjection(
        projection_id=run_local_id("joint-placement-projection", placement.placement_id),
        placement_id=placement.placement_id,
        sequence_role_intervals_px=sequence,
        top_at_lane_reference_px=top,
        bottom_at_lane_reference_px=bottom,
        extreme_evaluation_count=2 * (len(sequence) + 2),
    )


__all__ = ["FeasiblePlacementProjection", "project_selected_placement"]
