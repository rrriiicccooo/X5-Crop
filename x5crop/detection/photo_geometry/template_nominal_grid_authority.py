"""Compile and prove calibrated use of the one nominal placement Grid."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
from scipy.optimize import linprog

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from ...formats import APERTURE_COMPATIBILITY_SPEC, FormatSpec, FramePhysicalSpec
from .physical_identity import physical_fact_id
from .model import BoundaryRole
from .template_model import LocalAdvanceRelation, TemplateSpec
from .template_nominal_grid_model import (
    CalibratedNominalGridAuthority,
    CalibratedNominalGridEvidence,
    CalibratedNominalGridFitState,
    CalibratedNominalGridPrior,
    NominalGridFailureKind,
)


_NUMERIC_EPSILON = 1.0e-8


@dataclass(frozen=True)
class NominalGridRoleConstraint:
    role_index: int
    observation_id: ObservationId
    coordinate_px: float
    full_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            self.role_index < 0
            or not isinstance(self.observation_id, ObservationId)
            or not math.isfinite(self.coordinate_px)
            or not isinstance(self.full_interval_px, FiniteInterval)
            or not self.full_interval_px.contains(
                self.coordinate_px,
                epsilon=_NUMERIC_EPSILON,
            )
        ):
            raise ValueError("nominal Grid role constraint is invalid")


@dataclass(frozen=True)
class CalibratedNominalGridEnvelope:
    canonical_cycle_phase_px: float
    canonical_absolute_phase_px: float
    canonical_frame_width_px: float
    canonical_pitch_px: float
    canonical_scale_px_per_mm: float
    canonical_local_deltas_px: tuple[float, ...]
    cycle_phase_interval_px: FiniteInterval
    absolute_phase_interval_px: FiniteInterval
    frame_width_interval_px: FiniteInterval
    pitch_interval_px: FiniteInterval
    gap_interval_px: FiniteInterval
    scale_interval_px_per_mm: PositiveInterval
    local_delta_intervals_px: tuple[FiniteInterval, ...]
    role_positions_px: tuple[float, ...]
    role_intervals_px: tuple[FiniteInterval, ...]

    def __post_init__(self) -> None:
        canonical = (
            self.canonical_cycle_phase_px,
            self.canonical_absolute_phase_px,
            self.canonical_frame_width_px,
            self.canonical_pitch_px,
            self.canonical_scale_px_per_mm,
            *self.canonical_local_deltas_px,
            *self.role_positions_px,
        )
        if (
            any(not math.isfinite(value) for value in canonical)
            or not self.cycle_phase_interval_px.contains(
                self.canonical_cycle_phase_px,
                epsilon=_NUMERIC_EPSILON,
            )
            or not self.absolute_phase_interval_px.contains(
                self.canonical_absolute_phase_px,
                epsilon=_NUMERIC_EPSILON,
            )
            or not self.frame_width_interval_px.contains(
                self.canonical_frame_width_px,
                epsilon=_NUMERIC_EPSILON,
            )
            or not self.pitch_interval_px.contains(
                self.canonical_pitch_px,
                epsilon=_NUMERIC_EPSILON,
            )
            or not (
                self.scale_interval_px_per_mm.minimum - _NUMERIC_EPSILON
                <= self.canonical_scale_px_per_mm
                <= self.scale_interval_px_per_mm.maximum + _NUMERIC_EPSILON
            )
            or len(self.canonical_local_deltas_px)
            != len(self.local_delta_intervals_px)
            or any(
                not interval.contains(value, epsilon=_NUMERIC_EPSILON)
                for value, interval in zip(
                    self.canonical_local_deltas_px,
                    self.local_delta_intervals_px,
                    strict=True,
                )
            )
            or len(self.role_positions_px) != len(self.role_intervals_px)
            or any(
                not interval.contains(value, epsilon=_NUMERIC_EPSILON)
                for value, interval in zip(
                    self.role_positions_px,
                    self.role_intervals_px,
                    strict=True,
                )
            )
        ):
            raise ValueError("calibrated nominal Grid envelope is invalid")


def _scaled_interval(
    physical_mm: FiniteInterval,
    scale_px_per_mm: PositiveInterval,
) -> FiniteInterval:
    return FiniteInterval(
        physical_mm.minimum * scale_px_per_mm.minimum,
        physical_mm.maximum * scale_px_per_mm.maximum,
    )


def compile_calibrated_nominal_grid_prior(
    *,
    format_spec: FormatSpec,
    frame_spec: FramePhysicalSpec,
    template_id: str,
    scale_px_per_mm: PositiveInterval,
) -> CalibratedNominalGridPrior:
    """Project one explicit format calibration without granting phase."""

    pitch = format_spec.nominal_pitch_calibration
    if pitch is None:
        return CalibratedNominalGridPrior(
            prior_id=physical_fact_id(
                "calibrated-nominal-grid-prior-unavailable",
                format_spec.format_id,
                template_id,
                scale_px_per_mm,
            ),
            state=EvidenceState.UNAVAILABLE,
            format_id=format_spec.format_id,
            template_id=template_id,
            calibration_cohort_sha256=None,
            aperture_calibration_id=None,
            pitch_calibration_id=None,
            frame_width_mm=None,
            frame_height_mm=None,
            pitch_mm=None,
            scale_px_per_mm=scale_px_per_mm,
            frame_width_px=None,
            frame_height_px=None,
            pitch_px=None,
            failure_kind=NominalGridFailureKind.CALIBRATED_PRIOR_UNAVAILABLE,
            reason=(
                f"format {format_spec.format_id} has no calibrated nominal pitch"
            ),
        )
    width_guard = APERTURE_COMPATIBILITY_SPEC.width.guard_mm(
        frame_spec.frame_width_mm
    )
    height_guard = APERTURE_COMPATIBILITY_SPEC.height.guard_mm(
        frame_spec.frame_height_mm
    )
    width_mm = FiniteInterval(
        frame_spec.frame_width_mm - width_guard,
        frame_spec.frame_width_mm + width_guard,
    )
    height_mm = FiniteInterval(
        frame_spec.frame_height_mm - height_guard,
        frame_spec.frame_height_mm + height_guard,
    )
    pitch_mm = FiniteInterval(
        pitch.minimum_pitch_mm,
        pitch.maximum_pitch_mm,
    )
    width_px = _scaled_interval(width_mm, scale_px_per_mm)
    height_px = _scaled_interval(height_mm, scale_px_per_mm)
    pitch_px = _scaled_interval(pitch_mm, scale_px_per_mm)
    if pitch_px.maximum < width_px.minimum:
        raise ValueError("calibrated nominal pitch cannot contain one Frame")
    prior_id = physical_fact_id(
        "calibrated-nominal-grid-prior",
        format_spec.format_id,
        template_id,
        pitch.identity_fields,
        APERTURE_COMPATIBILITY_SPEC.identity_fields,
        scale_px_per_mm,
    )
    return CalibratedNominalGridPrior(
        prior_id=prior_id,
        state=EvidenceState.SUPPORTED,
        format_id=format_spec.format_id,
        template_id=template_id,
        calibration_cohort_sha256=pitch.development_gold_cohort_sha256,
        aperture_calibration_id=APERTURE_COMPATIBILITY_SPEC.calibration_id,
        pitch_calibration_id=pitch.calibration_id,
        frame_width_mm=width_mm,
        frame_height_mm=height_mm,
        pitch_mm=pitch_mm,
        scale_px_per_mm=scale_px_per_mm,
        frame_width_px=width_px,
        frame_height_px=height_px,
        pitch_px=pitch_px,
        failure_kind=None,
        reason=None,
    )


@dataclass(frozen=True)
class _LinearExpression:
    coefficients: np.ndarray
    constant: float = 0.0

    def value(self, values: np.ndarray) -> float:
        return self.constant + float(self.coefficients @ values)


def _append_interval_constraints(
    rows: list[np.ndarray],
    limits: list[float],
    expression: _LinearExpression,
    interval: FiniteInterval,
) -> None:
    rows.extend((expression.coefficients, -expression.coefficients))
    limits.extend(
        (
            interval.maximum - expression.constant,
            expression.constant - interval.minimum,
        )
    )


def _solve_linear(
    *,
    objective: np.ndarray,
    bounds: tuple[tuple[float | None, float | None], ...],
    rows: Sequence[np.ndarray],
    limits: Sequence[float],
) -> np.ndarray:
    result = linprog(
        objective,
        A_ub=np.asarray(rows, dtype=np.float64),
        b_ub=np.asarray(limits, dtype=np.float64),
        bounds=bounds,
        method="highs",
    )
    if not result.success or result.x is None:
        raise ValueError("calibrated nominal Grid has no joint feasible state")
    return np.asarray(result.x, dtype=np.float64)


def solve_calibrated_nominal_grid_envelope(
    *,
    prior: CalibratedNominalGridPrior,
    template: TemplateSpec,
    integer_slot_offset: int,
    role_constraints: tuple[NominalGridRoleConstraint, ...],
    relations: tuple[LocalAdvanceRelation, ...],
    phase_authority_px: FiniteInterval | None,
    retained_direct_constraint_rank: int,
) -> tuple[CalibratedNominalGridEnvelope, CalibratedNominalGridFitState]:
    """Fit one existing discrete mapping and project its complete envelope."""

    if prior.state != EvidenceState.SUPPORTED:
        raise ValueError("nominal Grid solve requires a supported prior")
    if prior.template_id != template.template_id:
        raise ValueError("nominal Grid prior belongs to another template")
    if not role_constraints:
        raise ValueError("nominal Grid requires one direct absolute anchor")
    if not 0 <= retained_direct_constraint_rank <= 3:
        raise ValueError("nominal Grid direct constraint rank is invalid")
    if not template.phase_lattice_authority.contains_offset(integer_slot_offset):
        raise ValueError("nominal Grid offset leaves the compiled lattice")
    assert prior.frame_width_mm is not None
    assert prior.pitch_mm is not None
    assert prior.frame_width_px is not None
    assert prior.pitch_px is not None
    relation_count = len(relations)
    variable_count = 4 + relation_count
    scale_index = 3 + relation_count
    width_minimum = max(
        prior.frame_width_px.minimum,
        template.frame_width_px.minimum,
    )
    width_maximum = min(
        prior.frame_width_px.maximum,
        template.frame_width_px.maximum,
    )
    pitch_minimum = max(prior.pitch_px.minimum, template.pitch_px.minimum)
    pitch_maximum = min(prior.pitch_px.maximum, template.pitch_px.maximum)
    if width_maximum < width_minimum or pitch_maximum < pitch_minimum:
        raise ValueError(
            "calibrated nominal Grid conflicts with the compiled template"
        )
    bounds: tuple[tuple[float | None, float | None], ...] = (
        (0.0, pitch_maximum),
        (width_minimum, width_maximum),
        (pitch_minimum, pitch_maximum),
        *tuple(
            (item.delta_interval_px.minimum, item.delta_interval_px.maximum)
            for item in relations
        ),
        (prior.scale_px_per_mm.minimum, prior.scale_px_per_mm.maximum),
    )
    direction = template.direction
    origin = template.phase_lattice_authority.cycle_origin_px

    def role_expression(role_index: int) -> _LinearExpression:
        role = template.roles[role_index]
        values = np.zeros(variable_count, dtype=np.float64)
        values[0] = direction
        values[1] = direction if role.role == BoundaryRole.END else 0.0
        values[2] = direction * (integer_slot_offset + role.slot_index)
        for relation_index in range(min(role.slot_index, relation_count)):
            values[3 + relation_index] = direction
        return _LinearExpression(values, origin)

    absolute_phase = np.zeros(variable_count, dtype=np.float64)
    absolute_phase[0] = direction
    absolute_phase[2] = direction * integer_slot_offset
    absolute_expression = _LinearExpression(absolute_phase, origin)
    role_expressions = tuple(
        role_expression(index) for index in range(2 * template.count)
    )
    rows: list[np.ndarray] = []
    limits: list[float] = []

    # The same source scale owns W and pitch.  These linear constraints retain
    # that correlation instead of freely combining independent pixel endpoints.
    for variable_index, physical in (
        (1, prior.frame_width_mm),
        (2, prior.pitch_mm),
    ):
        upper = np.zeros(variable_count, dtype=np.float64)
        upper[variable_index] = 1.0
        upper[scale_index] = -physical.maximum
        rows.append(upper)
        limits.append(0.0)
        lower = np.zeros(variable_count, dtype=np.float64)
        lower[variable_index] = -1.0
        lower[scale_index] = physical.minimum
        rows.append(lower)
        limits.append(0.0)
    cycle_inside_period = np.zeros(variable_count, dtype=np.float64)
    cycle_inside_period[0] = 1.0
    cycle_inside_period[2] = -1.0
    rows.append(cycle_inside_period)
    limits.append(-_NUMERIC_EPSILON)
    non_negative_gap = np.zeros(variable_count, dtype=np.float64)
    non_negative_gap[1] = 1.0
    non_negative_gap[2] = -1.0
    rows.append(non_negative_gap)
    limits.append(0.0)
    for constraint in role_constraints:
        _append_interval_constraints(
            rows,
            limits,
            role_expressions[constraint.role_index],
            constraint.full_interval_px,
        )
    if phase_authority_px is not None:
        _append_interval_constraints(
            rows,
            limits,
            absolute_expression,
            phase_authority_px,
        )

    scale_center = prior.scale_px_per_mm.minimum + (
        prior.scale_px_per_mm.maximum - prior.scale_px_per_mm.minimum
    ) / 2.0
    width_target = prior.frame_width_mm.center * scale_center
    pitch_target = prior.pitch_mm.center * scale_center
    local_targets = tuple(item.canonical_delta_px for item in relations)
    prefix_targets = [0.0]
    for slot_index in range(1, template.count):
        value = (
            local_targets[slot_index - 1]
            if slot_index <= relation_count
            else 0.0
        )
        prefix_targets.append(prefix_targets[-1] + value)
    cycle_targets = []
    for constraint in role_constraints:
        role = template.roles[constraint.role_index]
        relative = (
            (integer_slot_offset + role.slot_index) * pitch_target
            + prefix_targets[role.slot_index]
            + (width_target if role.role == BoundaryRole.END else 0.0)
        )
        cycle_targets.append(
            direction * (constraint.coordinate_px - origin) - relative
        )
    cycle_target = float(np.median(np.asarray(cycle_targets, dtype=np.float64)))
    target = np.asarray(
        (
            cycle_target,
            width_target,
            pitch_target,
            *local_targets,
            scale_center,
        ),
        dtype=np.float64,
    )
    # Choose a deterministic feasible representative nearest the calibrated
    # zero-deviation state.  This representative never selects a candidate;
    # every safety decision consumes the complete envelope below.
    base_variable_count = variable_count
    augmented_count = 2 * base_variable_count
    augmented_rows = [
        np.pad(row, (0, base_variable_count)) for row in rows
    ]
    augmented_limits = list(limits)
    for index in range(base_variable_count):
        positive = np.zeros(augmented_count, dtype=np.float64)
        positive[index] = 1.0
        positive[base_variable_count + index] = -1.0
        augmented_rows.append(positive)
        augmented_limits.append(float(target[index]))
        negative = np.zeros(augmented_count, dtype=np.float64)
        negative[index] = -1.0
        negative[base_variable_count + index] = -1.0
        augmented_rows.append(negative)
        augmented_limits.append(float(-target[index]))
    augmented_bounds = (
        *bounds,
        *((0.0, None) for _ in range(base_variable_count)),
    )
    objective = np.zeros(augmented_count, dtype=np.float64)
    for index, (minimum, maximum) in enumerate(bounds):
        objective[base_variable_count + index] = 1.0 / max(
            1.0,
            maximum - minimum,
        )
    canonical = _solve_linear(
        objective=objective,
        bounds=augmented_bounds,
        rows=augmented_rows,
        limits=augmented_limits,
    )[:base_variable_count]

    def intersect_interval(
        left: FiniteInterval,
        right: FiniteInterval,
    ) -> FiniteInterval:
        minimum = max(left.minimum, right.minimum)
        maximum = min(left.maximum, right.maximum)
        if maximum < minimum - _NUMERIC_EPSILON:
            raise ValueError("calibrated nominal Grid intervals do not intersect")
        return FiniteInterval(minimum, max(minimum, maximum))

    def add_interval(
        left: FiniteInterval,
        right: FiniteInterval,
    ) -> FiniteInterval:
        return FiniteInterval(
            left.minimum + right.minimum,
            left.maximum + right.maximum,
        )

    def subtract_interval(
        left: FiniteInterval,
        right: FiniteInterval,
    ) -> FiniteInterval:
        return FiniteInterval(
            left.minimum - right.maximum,
            left.maximum - right.minimum,
        )

    def scale_interval(
        interval: FiniteInterval,
        coefficient: float,
    ) -> FiniteInterval:
        values = (
            coefficient * interval.minimum,
            coefficient * interval.maximum,
        )
        return FiniteInterval(min(values), max(values))

    local_intervals = tuple(item.delta_interval_px for item in relations)
    prefix_intervals = [FiniteInterval.exact(0.0)]
    for slot_index in range(1, template.count):
        interval = (
            local_intervals[slot_index - 1]
            if slot_index <= relation_count
            else FiniteInterval.exact(0.0)
        )
        prefix_intervals.append(add_interval(prefix_intervals[-1], interval))
    width_interval = FiniteInterval(
        width_minimum,
        width_maximum,
    )
    pitch_interval = FiniteInterval(
        pitch_minimum,
        pitch_maximum,
    )
    constraints_by_index = {
        item.role_index: item for item in role_constraints
    }
    ordered_constraints = tuple(
        constraints_by_index[index] for index in sorted(constraints_by_index)
    )
    # Pairwise direct anchors safely narrow W/pitch without treating their raw
    # count as rank.  Interval propagation is deliberately conservative; the
    # selected-output LP later retains the exact shared state.
    for _iteration in range(4):
        prior_width = width_interval
        prior_pitch = pitch_interval
        for left_index, left in enumerate(ordered_constraints):
            left_role = template.roles[left.role_index]
            for right in ordered_constraints[left_index + 1 :]:
                right_role = template.roles[right.role_index]
                observed_difference = subtract_interval(
                    right.full_interval_px,
                    left.full_interval_px,
                )
                width_coefficient = direction * (
                    int(right_role.role == BoundaryRole.END)
                    - int(left_role.role == BoundaryRole.END)
                )
                pitch_coefficient = direction * (
                    right_role.slot_index - left_role.slot_index
                )
                local_difference = scale_interval(
                    subtract_interval(
                        prefix_intervals[right_role.slot_index],
                        prefix_intervals[left_role.slot_index],
                    ),
                    direction,
                )
                if pitch_coefficient:
                    remainder = subtract_interval(
                        subtract_interval(
                            observed_difference,
                            scale_interval(width_interval, width_coefficient),
                        ),
                        local_difference,
                    )
                    pitch_interval = intersect_interval(
                        pitch_interval,
                        scale_interval(remainder, 1.0 / pitch_coefficient),
                    )
                if width_coefficient:
                    remainder = subtract_interval(
                        subtract_interval(
                            observed_difference,
                            scale_interval(pitch_interval, pitch_coefficient),
                        ),
                        local_difference,
                    )
                    width_interval = intersect_interval(
                        width_interval,
                        scale_interval(remainder, 1.0 / width_coefficient),
                    )
        if width_interval == prior_width and pitch_interval == prior_pitch:
            break

    phase_intervals: list[FiniteInterval] = []
    for constraint in ordered_constraints:
        role = template.roles[constraint.role_index]
        relative = add_interval(
            scale_interval(pitch_interval, role.slot_index),
            prefix_intervals[role.slot_index],
        )
        if role.role == BoundaryRole.END:
            relative = add_interval(relative, width_interval)
        phase_intervals.append(
            subtract_interval(
                constraint.full_interval_px,
                scale_interval(relative, direction),
            )
        )
    absolute_interval = phase_intervals[0]
    for interval in phase_intervals[1:]:
        absolute_interval = intersect_interval(absolute_interval, interval)
    if phase_authority_px is not None:
        absolute_interval = intersect_interval(
            absolute_interval,
            phase_authority_px,
        )
    normalized_absolute = scale_interval(
        FiniteInterval(
            absolute_interval.minimum - origin,
            absolute_interval.maximum - origin,
        ),
        direction,
    )
    cycle_interval = subtract_interval(
        normalized_absolute,
        scale_interval(pitch_interval, integer_slot_offset),
    )
    cycle_interval = intersect_interval(
        cycle_interval,
        FiniteInterval(0.0, pitch_interval.maximum),
    )
    gap_interval = FiniteInterval(
        max(0.0, pitch_interval.minimum - width_interval.maximum),
        pitch_interval.maximum - width_interval.minimum,
    )
    role_intervals = []
    for role in template.roles:
        relative = add_interval(
            scale_interval(pitch_interval, role.slot_index),
            prefix_intervals[role.slot_index],
        )
        if role.role == BoundaryRole.END:
            relative = add_interval(relative, width_interval)
        role_intervals.append(
            add_interval(
                absolute_interval,
                scale_interval(relative, direction),
            )
        )
    role_intervals = tuple(role_intervals)
    role_positions = tuple(item.value(canonical) for item in role_expressions)
    envelope = CalibratedNominalGridEnvelope(
        canonical_cycle_phase_px=float(canonical[0]),
        canonical_absolute_phase_px=absolute_expression.value(canonical),
        canonical_frame_width_px=float(canonical[1]),
        canonical_pitch_px=float(canonical[2]),
        canonical_scale_px_per_mm=float(canonical[scale_index]),
        canonical_local_deltas_px=tuple(
            float(canonical[3 + index]) for index in range(relation_count)
        ),
        cycle_phase_interval_px=cycle_interval,
        absolute_phase_interval_px=absolute_interval,
        frame_width_interval_px=width_interval,
        pitch_interval_px=pitch_interval,
        gap_interval_px=gap_interval,
        scale_interval_px_per_mm=prior.scale_px_per_mm,
        local_delta_intervals_px=local_intervals,
        role_positions_px=role_positions,
        role_intervals_px=role_intervals,
    )
    anchor_indices = tuple(sorted(constraints_by_index))
    fit_state = CalibratedNominalGridFitState(
        prior_id=prior.prior_id,
        scale_px_per_mm=prior.scale_px_per_mm,
        frame_width_mm=prior.frame_width_mm,
        pitch_mm=prior.pitch_mm,
        canonical_scale_px_per_mm=float(canonical[scale_index]),
        phase_anchor_role_indices=anchor_indices,
        phase_anchor_observation_ids=tuple(
            constraints_by_index[index].observation_id
            for index in anchor_indices
        ),
        retained_direct_constraint_rank=retained_direct_constraint_rank,
    )
    return envelope, fit_state


def nominal_grid_evidence_id(
    fit_state: CalibratedNominalGridFitState,
    inferred_adjacency_ordinals: tuple[int, ...],
    unobserved_frame_ordinals: tuple[int, ...],
    covering_query_ids: tuple[str, ...],
) -> str:
    return physical_fact_id(
        "calibrated-nominal-grid-evidence",
        fit_state.prior_id,
        fit_state.phase_anchor_role_indices,
        fit_state.phase_anchor_observation_ids,
        inferred_adjacency_ordinals,
        unobserved_frame_ordinals,
        covering_query_ids,
    )


def failed_nominal_grid_evidence(
    fit_state: CalibratedNominalGridFitState,
    *,
    inferred_adjacency_ordinals: tuple[int, ...],
    unobserved_frame_ordinals: tuple[int, ...] = (),
    covering_query_ids: tuple[str, ...],
    state: EvidenceState,
    failure_kind: NominalGridFailureKind,
    reason: str,
) -> CalibratedNominalGridEvidence:
    return CalibratedNominalGridEvidence(
        evidence_id=nominal_grid_evidence_id(
            fit_state,
            inferred_adjacency_ordinals,
            unobserved_frame_ordinals,
            covering_query_ids,
        ),
        state=state,
        prior_id=fit_state.prior_id,
        phase_anchor_role_indices=fit_state.phase_anchor_role_indices,
        phase_anchor_observation_ids=fit_state.phase_anchor_observation_ids,
        inferred_adjacency_ordinals=inferred_adjacency_ordinals,
        unobserved_frame_ordinals=unobserved_frame_ordinals,
        covering_query_ids=covering_query_ids,
        failure_kind=failure_kind,
        reason=reason,
    )


def assess_calibrated_nominal_grid_authority(
    evidence: CalibratedNominalGridEvidence | None,
    *,
    placement_id: str | None,
    output_geometry_ids: tuple[str, ...],
) -> CalibratedNominalGridAuthority:
    """Bind selected-only output geometry without duplicating budget ownership."""

    if evidence is None:
        return CalibratedNominalGridAuthority(
            authority_id=physical_fact_id(
                "calibrated-nominal-grid-authority-not-applicable"
            ),
            state=EvidenceState.NOT_APPLICABLE,
            evidence_id=None,
            placement_id=None,
            output_geometry_ids=(),
            failure_kind=None,
            reason=None,
        )
    authority_id = physical_fact_id(
        "calibrated-nominal-grid-authority",
        evidence.evidence_id,
        placement_id,
        output_geometry_ids,
    )
    if (
        evidence.state != EvidenceState.SUPPORTED
        or not placement_id
        or not output_geometry_ids
    ):
        return CalibratedNominalGridAuthority(
            authority_id=authority_id,
            state=(
                EvidenceState.CONTRADICTED
                if evidence.state == EvidenceState.CONTRADICTED
                else EvidenceState.UNAVAILABLE
            ),
            evidence_id=evidence.evidence_id,
            placement_id=placement_id,
            output_geometry_ids=output_geometry_ids,
            failure_kind=(
                evidence.failure_kind
                or NominalGridFailureKind.OUTPUT_FOOTPRINT_UNAVAILABLE
            ),
            reason=(
                evidence.reason
                or "calibrated nominal Grid has no complete selected output"
            ),
        )
    return CalibratedNominalGridAuthority(
        authority_id=authority_id,
        state=EvidenceState.SUPPORTED,
        evidence_id=evidence.evidence_id,
        placement_id=placement_id,
        output_geometry_ids=output_geometry_ids,
        failure_kind=None,
        reason=None,
    )
