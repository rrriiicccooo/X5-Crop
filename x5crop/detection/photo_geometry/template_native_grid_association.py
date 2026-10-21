"""Necessary same-state bounds for native/fully unobserved Grid neighbours.

The projected set is a conservative relaxation: local native coordinates keep
their own full intervals; they never become additional phase anchors. A bound
crossing zero is missing proof, not evidence that an overlap is physically
possible. Neither a projection nor its representative creates an Overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import math

import numpy as np
from scipy.optimize import linprog

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .template_lattice_authority import global_lattice_authority_matches_fit
from .template_model import ContactRelation, SeparatorRelation, SequenceBindingUse, SequenceFit
from .template_phase_model import GlobalLatticeConstraintKind, PhaseFitResult


_EPSILON = 1.0e-7


class NativeGridBoundaryBasis(str, Enum):
    GRID = "joint_grid_role"
    NATIVE = "independent_native_interval"
    NATIVE_ANCHOR = "existing_native_grid_anchor"
    NATIVE_WIDTH = "native_and_shared_width"
    ANCHOR_GRID_WIDTH = "existing_anchor_and_joint_grid_width"


@dataclass(frozen=True)
class NativeGridBoundarySource:
    role_index: int
    basis: NativeGridBoundaryBasis
    native_role_index: int | None
    observation_id: ObservationId | None
    native_full_interval_px: FiniteInterval | None
    coordinate_authorized: bool
    shared_width_authorized: bool

    def __post_init__(self) -> None:
        if (type(self.role_index) is not int or self.role_index < 0
                or not isinstance(self.basis, NativeGridBoundaryBasis)
                or type(self.coordinate_authorized) is not bool
                or type(self.shared_width_authorized) is not bool):
            raise ValueError("native/Grid boundary source is invalid")
        native = self.basis != NativeGridBoundaryBasis.GRID
        if native != (type(self.native_role_index) is int
                      and self.native_role_index >= 0
                      and isinstance(self.observation_id, ObservationId)
                      and isinstance(self.native_full_interval_px, FiniteInterval)):
            raise ValueError("native/Grid boundary lost its original native input")
        if not native and any(value is not None for value in (
                self.native_role_index, self.observation_id, self.native_full_interval_px)):
            raise ValueError("Grid boundary cannot invent a native input")
        if self.basis in (NativeGridBoundaryBasis.NATIVE_WIDTH, NativeGridBoundaryBasis.ANCHOR_GRID_WIDTH):
            if self.native_role_index != self.role_index ^ 1:
                raise ValueError("shared-W inference changed the opposite role")
        elif native and self.native_role_index != self.role_index:
            raise ValueError("native coordinate changed its role")
        elif self.shared_width_authorized:
            raise ValueError("only an inferred opposite can consume shared W")


@dataclass(frozen=True)
class NativeGridGapFact:
    relation_ordinal: int
    end: NativeGridBoundarySource
    next_start: NativeGridBoundarySource
    signed_gap_interval_px: FiniteInterval | None
    canonical_signed_gap_px: float
    joint_system_feasible: bool | None
    state: EvidenceState = field(init=False)

    def __post_init__(self) -> None:
        if (type(self.relation_ordinal) is not int or self.relation_ordinal <= 0
                or self.end.role_index != 2 * self.relation_ordinal - 1
                or self.next_start.role_index != 2 * self.relation_ordinal
                or self.joint_system_feasible is not None and type(self.joint_system_feasible) is not bool
                or type(self.canonical_signed_gap_px) not in (int, float)
                or not math.isfinite(self.canonical_signed_gap_px)
                or (self.joint_system_feasible is True) != isinstance(self.signed_gap_interval_px, FiniteInterval)):
            raise ValueError("native/Grid gap lost its physical relation or projection")
        authorized = self.end.coordinate_authorized and self.next_start.coordinate_authorized
        interval = self.signed_gap_interval_px
        state = EvidenceState.UNAVAILABLE
        if authorized:
            if self.joint_system_feasible is False or interval is not None and interval.maximum < -_EPSILON:
                state = EvidenceState.CONTRADICTED
            elif (interval is not None and interval.minimum >= -_EPSILON
                    and self.canonical_signed_gap_px >= -_EPSILON
                    and interval.contains(self.canonical_signed_gap_px, epsilon=_EPSILON)):
                state = EvidenceState.SUPPORTED
        object.__setattr__(self, "state", state)


class NativeGridConstraintKind(str, Enum):
    NATIVE_FRAME_WIDTH = "native_frame_physical_width"
    MEASURED_RELATION = "registered_measured_relation"


@dataclass(frozen=True)
class NativeGridIndependentConstraint:
    kind: NativeGridConstraintKind
    ordinal: int
    first_role_index: int
    second_role_index: int
    observation_ids: tuple[ObservationId, ObservationId]
    signed_span_interval_px: FiniteInterval

    def __post_init__(self):
        if (not isinstance(self.kind, NativeGridConstraintKind)
                or type(self.ordinal) is not int or self.ordinal < 1
                or any(type(i) is not int or i < 0 for i in (self.first_role_index, self.second_role_index))
                or self.second_role_index != self.first_role_index + 1
                or len(self.observation_ids) != 2
                or any(not isinstance(i, ObservationId) for i in self.observation_ids)
                or not isinstance(self.signed_span_interval_px, FiniteInterval)):
            raise ValueError("native/Grid independent constraint lost its physical inputs")
        first = 2 * (self.ordinal - 1) if self.kind == NativeGridConstraintKind.NATIVE_FRAME_WIDTH else 2 * self.ordinal - 1
        if self.first_role_index != first or (
                self.kind == NativeGridConstraintKind.NATIVE_FRAME_WIDTH
                and self.signed_span_interval_px.minimum <= 0):
            raise ValueError("native/Grid independent constraint changed its role pair")


@dataclass(frozen=True)
class NativeGridAssociationProof:
    input_fingerprint: str
    facts: tuple[NativeGridGapFact, ...]
    variable_count: int
    inequality_count: int
    lp_solve_count: int
    native_variable_observation_ids: tuple[ObservationId, ...] = ()
    independent_constraints: tuple[NativeGridIndependentConstraint, ...] = ()
    grid_authority_failure: str | None = None
    unqualified_grid_anchor_role_indices: tuple[int, ...] = ()
    unqualified_native_role_indices: tuple[int, ...] = ()
    uncompiled_grid_anchor_role_indices: tuple[int, ...] = ()
    state: EvidenceState = field(init=False)

    def __post_init__(self) -> None:
        ordinals = tuple(f.relation_ordinal for f in self.facts)
        for indices in (self.unqualified_grid_anchor_role_indices, self.unqualified_native_role_indices,
                        self.uncompiled_grid_anchor_role_indices):
            if (not isinstance(indices, tuple) or any(type(i) is not int or i < 0 for i in indices)
                    or tuple(sorted(set(indices))) != indices):
                raise ValueError("native/Grid qualification lost its original role indices")
        if (len(self.input_fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in self.input_fingerprint)
                or not self.facts or ordinals != tuple(sorted(set(ordinals)))
                or any(type(value) is not int or value < 0 for value in (
                    self.variable_count, self.inequality_count, self.lp_solve_count))
                or self.variable_count not in (0,) and self.variable_count < 3
                or bool(self.variable_count) != bool(self.inequality_count)
                or bool(self.variable_count) != bool(self.lp_solve_count)
                or len(set(self.native_variable_observation_ids)) != len(self.native_variable_observation_ids)
                or any(not isinstance(i, ObservationId) for i in self.native_variable_observation_ids)
                or len(set(self.independent_constraints)) != len(self.independent_constraints)
                or not self.variable_count and (self.native_variable_observation_ids or self.independent_constraints)
                or self.grid_authority_failure is not None and (
                    type(self.grid_authority_failure) is not str or not self.grid_authority_failure or self.lp_solve_count)
                or self.unqualified_grid_anchor_role_indices and self.grid_authority_failure is None
                or self.uncompiled_grid_anchor_role_indices and (
                    self.grid_authority_failure is None or self.lp_solve_count
                    or not set(self.uncompiled_grid_anchor_role_indices).intersection(
                        self.unqualified_grid_anchor_role_indices).issubset(self.unqualified_native_role_indices))
                or not 0 <= self.lp_solve_count <= 2 * len(self.facts)
                or self.lp_solve_count == 0 and any(f.joint_system_feasible is not None for f in self.facts)):
            raise ValueError("native/Grid association lost complete bounded work")
        object.__setattr__(self, "state", (
            EvidenceState.CONTRADICTED if any(f.state == EvidenceState.CONTRADICTED for f in self.facts)
            else EvidenceState.UNAVAILABLE if any(f.state != EvidenceState.SUPPORTED for f in self.facts)
            else EvidenceState.SUPPORTED))

    def matches_inputs(self, phase, source_frame_width_authority) -> bool:
        return self.input_fingerprint == _input_fingerprint(phase, source_frame_width_authority)


def _qualified_global(phase):
    authority = phase.global_lattice_authority
    return (authority if authority is not None and authority.state == EvidenceState.SUPPORTED
            and global_lattice_authority_matches_fit(authority, phase.best) else None)


def _input_fingerprint(phase, width):
    fit = phase.best
    if fit is None:
        raise ValueError("native/Grid proof requires its own fit")
    grid = phase.calibrated_nominal_grid_evidence
    direct = phase.direct_role_binding_authority
    inference = fit.frame_width_inference
    # Generated proof IDs are not mathematical inputs. Original registered
    # observation IDs, full intervals and the complete consumed state are.
    key = (fit.template.template_id, fit.template.count, fit.template.direction,
        fit.template.frame_width_px, fit.phase_lattice_fit, fit.pitch_fit,
        fit.model_role_positions_px, fit.model_role_intervals_px, fit.adjacency_relations,
        fit.calibrated_nominal_grid_fit_state,
        tuple(None if b is None else (b.observation_id, b.use, b.canonical_position_px,
                                      b.full_position_interval_px) for b in fit.role_bindings),
        _qualified_global(phase),
        None if grid is None else (grid.state, grid.prior_id, grid.phase_anchor_role_indices,
            grid.phase_anchor_observation_ids, grid.inferred_adjacency_ordinals, grid.unobserved_frame_ordinals),
        None if direct is None else tuple((f.role_index, f.observation_id, f.state, f.bases) for f in direct.facts),
        None if inference is None else (inference.state, inference.inferred_role_indices,
            inference.width_px, inference.canonical_width_px, inference.observation_ids),
        None if width is None else (width.state, width.width_px, width.canonical_width_px,
            width.observation_ids, width.matches_placement(fit),
            inference is not None and inference.authority_id == width.authority_id))
    return sha256(repr(key).encode("utf-8")).hexdigest()


def native_grid_relation_ordinals(fit: SequenceFit) -> tuple[int, ...]:
    relations = {r.relation_ordinal: r for r in fit.adjacency_relations}
    unobserved = tuple(fit.role_bindings[i] is None and fit.role_bindings[i + 1] is None
                       for i in range(0, len(fit.role_bindings), 2))
    return tuple(i for i in range(1, fit.template.count)
        if unobserved[i - 1] != unobserved[i]
        and (i not in relations or isinstance(relations[i], SeparatorRelation) and not relations[i].is_measured))


def native_grid_work_bound(role_count: int) -> int:
    if type(role_count) is not int or role_count < 2 or role_count % 2:
        raise ValueError("native/Grid work requires a positive even role count")
    return 128 + 32 * role_count * (role_count + 10)


def native_grid_bytes_bound(role_count: int) -> int:
    native_grid_work_bound(role_count)
    return 8192 + 512 * role_count * (role_count + 10)


def _grid_qualification(phase):
    fit = phase.best
    global_authority = _qualified_global(phase)
    state = fit.calibrated_nominal_grid_fit_state
    evidence = phase.calibrated_nominal_grid_evidence
    nominal_supported = bool(state is not None and evidence is not None and state.phase_anchor_role_indices
        and evidence.state == EvidenceState.SUPPORTED and evidence.prior_id == state.prior_id
        and evidence.phase_anchor_role_indices == state.phase_anchor_role_indices
        and evidence.phase_anchor_observation_ids == state.phase_anchor_observation_ids
        and all(fit.role_bindings[i] is not None
                and fit.role_bindings[i].use == SequenceBindingUse.PHASE_ANCHOR
                and fit.role_bindings[i].observation_id == identity
                for i, identity in zip(state.phase_anchor_role_indices, state.phase_anchor_observation_ids, strict=True)))
    # The shared system consumes every retained coordinate constraint, not
    # only the native endpoint at this particular adjacency. Cross-dependent
    # partial-height anchors cannot supply a pre-Cross physical conclusion.
    required = set(() if state is None else state.phase_anchor_role_indices)
    if global_authority is not None:
        required.update(c.role_index for c in global_authority.constraints
                        if c.kind == GlobalLatticeConstraintKind.DIRECT_ROLE_COORDINATE)
    # No compiled state does not mean no original anchor obligations. Keep
    # their coordinate failures visible without treating these bindings as
    # constraints of an authorized Grid or running a downstream LP.
    uncompiled = (() if state is not None or global_authority is not None else
                  tuple(i for i, b in enumerate(fit.role_bindings)
                        if b is not None and b.use == SequenceBindingUse.PHASE_ANCHOR))
    required.update(uncompiled)
    direct = phase.direct_role_binding_authority
    facts = {} if direct is None else {f.role_index: f for f in direct.facts}
    missing = tuple(sorted(i for i in required if not (i in facts and fit.role_bindings[i] is not None
               and facts[i].observation_id == fit.role_bindings[i].observation_id
               and facts[i].has_unconditional_coordinate_authority)))
    if global_authority is None and not nominal_supported:
        failure = (evidence.failure_kind.value if evidence is not None and evidence.failure_kind is not None
                   else "nominal_grid_state_missing" if state is None else "nominal_grid_identity_unqualified")
        return False, failure, missing, uncompiled
    return ((False, "grid_anchor_coordinate_authority_unavailable", missing, ())
            if missing else (True, None, (), ()))


def _grid_authorized(phase):
    return _grid_qualification(phase)[0]


def _independent_native_system(phase, anchors, facts_by_role):
    """Keep native coordinates and their existing physical relations together.

    Native/local variables never constrain their model roles. A complete
    native Frame consumes the original physical template width, allowing
    different observed Frames to have different widths. Only an explicit
    measured relation contributes a native adjacency strip.
    """
    from .template_feasible_geometry import sequence_feasible_system, _FeasibleSystem

    fit = phase.best
    system, roles = sequence_feasible_system(fit, _qualified_global(phase))
    authorized = {i for i, b in enumerate(fit.role_bindings) if b is not None
        and i in facts_by_role and facts_by_role[i].observation_id == b.observation_id
        and facts_by_role[i].has_unconditional_coordinate_authority}
    shared = {fit.role_bindings[i].observation_id: i for i in anchors}
    by_id = {b.observation_id: b for b in fit.role_bindings if b is not None}
    native_ids = tuple(dict.fromkeys(b.observation_id for i, b in enumerate(fit.role_bindings)
        if b is not None and i in authorized and b.observation_id not in shared))
    native_indices = {identity: len(system.bounds) + i for i, identity in enumerate(native_ids)}
    dimension = len(system.bounds) + len(native_ids)
    native_expressions = {}
    for i in sorted(authorized):
        identity = fit.role_bindings[i].observation_id
        coefficients = np.zeros(dimension, dtype=np.float64)
        if identity in shared:
            expression = roles[shared[identity]]
            coefficients[:len(system.bounds)] = expression.coefficients
            constant = expression.constant
        else:
            coefficients[native_indices[identity]] = 1.0
            constant = 0.0
        native_expressions[i] = (coefficients, constant)
    rows = [np.pad(row, (0, len(native_ids))) for row in system.inequalities[0]]
    limits = list(system.inequalities[1])
    constraints = []

    def retain(kind, ordinal, first, second, interval):
        if first not in native_expressions or second not in native_expressions:
            return
        left, right = native_expressions[first], native_expressions[second]
        coefficients = fit.template.direction * (right[0] - left[0])
        constant = fit.template.direction * (right[1] - left[1])
        rows.extend((coefficients, -coefficients))
        limits.extend((interval.maximum - constant, constant - interval.minimum))
        constraints.append(NativeGridIndependentConstraint(kind, ordinal, first, second,
            (fit.role_bindings[first].observation_id, fit.role_bindings[second].observation_id),
            FiniteInterval(interval.minimum, interval.maximum)))

    for first in range(0, len(fit.role_bindings), 2):
        retain(NativeGridConstraintKind.NATIVE_FRAME_WIDTH, first // 2 + 1,
               first, first + 1, fit.template.frame_width_px)
    for relation in fit.adjacency_relations:
        if isinstance(relation, SeparatorRelation) and not relation.is_measured:
            continue
        span = FiniteInterval.exact(0.0) if isinstance(relation, ContactRelation) else relation.signed_gap_interval_px
        retain(NativeGridConstraintKind.MEASURED_RELATION, relation.relation_ordinal,
               2 * relation.relation_ordinal - 1, 2 * relation.relation_ordinal, span)
    bounds = system.bounds + tuple((by_id[i].full_position_interval_px.minimum,
                                    by_id[i].full_position_interval_px.maximum) for i in native_ids)
    return (_FeasibleSystem(bounds, (np.asarray(rows), np.asarray(limits))), roles,
            native_expressions, native_ids, tuple(constraints))


def assess_native_grid_association(phase: PhaseFitResult, source_frame_width_authority=None):
    """Project a conservative actual gap without assuming its desired sign."""
    fit = phase.best
    if fit is None:
        return None
    ordinals = native_grid_relation_ordinals(fit)
    if not ordinals:
        return None
    system = roles = None
    native_expressions = None
    native_ids = independent_constraints = ()
    grid_authorized, grid_failure, unqualified_anchors, uncompiled_anchors = _grid_qualification(phase)
    direct = phase.direct_role_binding_authority
    facts_by_role = {} if direct is None else {f.role_index: f for f in direct.facts}
    unqualified_native = tuple(i for i, b in enumerate(fit.role_bindings) if b is not None
        and (i not in facts_by_role or facts_by_role[i].observation_id != b.observation_id
             or not facts_by_role[i].has_unconditional_coordinate_authority))
    anchors = set()
    nominal = fit.calibrated_nominal_grid_fit_state
    if nominal is not None:
        anchors.update(nominal.phase_anchor_role_indices)
    global_authority = _qualified_global(phase)
    if global_authority is not None:
        anchors.update(c.role_index for c in global_authority.constraints
                       if c.kind == GlobalLatticeConstraintKind.DIRECT_ROLE_COORDINATE)
    inference = fit.frame_width_inference
    width = source_frame_width_authority
    width_authorized = bool(inference is not None and inference.state == EvidenceState.SUPPORTED
        and width is not None and width.state == EvidenceState.SUPPORTED and width.matches_placement(fit)
        and inference.authority_id == width.authority_id)

    def endpoint(index):
        binding = fit.role_bindings[index]
        if binding is None and fit.role_bindings[index ^ 1] is None:
            return (NativeGridBoundarySource(index, NativeGridBoundaryBasis.GRID, None, None, None,
                                            grid_authorized, False),
                    fit.model_role_positions_px[index])
        native_index = index if binding is not None else index ^ 1
        native = fit.role_bindings[native_index]
        fact = facts_by_role.get(native_index)
        native_authorized = bool(fact is not None and fact.has_unconditional_coordinate_authority
                                 and fact.observation_id == native.observation_id)
        inferred = binding is None
        anchor_width = inferred and native_index in anchors and grid_authorized
        authorized_width = bool(anchor_width or inferred and width_authorized and index in inference.inferred_role_indices)
        basis = (NativeGridBoundaryBasis.ANCHOR_GRID_WIDTH if anchor_width else
                 NativeGridBoundaryBasis.NATIVE_WIDTH if inferred else
                 NativeGridBoundaryBasis.NATIVE_ANCHOR if native_index in anchors else NativeGridBoundaryBasis.NATIVE)
        source = NativeGridBoundarySource(index, basis, native_index, native.observation_id,
            native.full_position_interval_px, native_authorized and (not inferred or authorized_width), authorized_width)
        canonical = native.canonical_position_px
        if inferred:
            signed_width = fit.template.direction * (1 if index % 2 else -1)
            canonical += signed_width * fit.pitch_fit.canonical_frame_width_px
        return source, canonical

    def expression(source):
        if source.basis == NativeGridBoundaryBasis.GRID:
            role = roles[source.role_index]
            return np.pad(role.coefficients, (0, len(native_ids))), FiniteInterval.exact(role.constant)
        coordinates = native_expressions[source.native_role_index]
        coefficients = coordinates[0].copy()
        offset = FiniteInterval.exact(coordinates[1])
        if source.basis in (NativeGridBoundaryBasis.NATIVE_WIDTH, NativeGridBoundaryBasis.ANCHOR_GRID_WIDTH):
            coefficients[1] += fit.template.direction * (1 if source.role_index % 2 else -1)
        return coefficients, offset

    solve_count = 0
    infeasible = False
    facts = []
    extrema_by_objective = {}
    for ordinal in ordinals:
        end, end_canonical = endpoint(2 * ordinal - 1)
        start, start_canonical = endpoint(2 * ordinal)
        direction = fit.template.direction
        canonical = direction * (start_canonical - end_canonical)
        if not end.coordinate_authorized or not start.coordinate_authorized:
            facts.append(NativeGridGapFact(ordinal, end, start, None, canonical, None))
            continue
        if system is None:
            system, roles, native_expressions, native_ids, independent_constraints = _independent_native_system(
                phase, anchors, facts_by_role)
        end_coefficients, end_offset = expression(end)
        start_coefficients, start_offset = expression(start)
        objective = direction * (start_coefficients - end_coefficients)
        offset = (FiniteInterval(start_offset.minimum - end_offset.maximum, start_offset.maximum - end_offset.minimum)
                  if direction > 0 else
                  FiniteInterval(end_offset.minimum - start_offset.maximum, end_offset.maximum - start_offset.minimum))
        bounds = None
        if not infeasible:
            key = objective.tobytes()
            extrema = extrema_by_objective.get(key)
            if extrema is None:
                extrema = []
                for sign in (1, -1):
                    result = linprog(sign * objective, A_ub=system.inequalities[0], b_ub=system.inequalities[1],
                                     bounds=system.bounds, method="highs")
                    solve_count += 1
                    if result.status == 2:
                        if extrema or any(f.joint_system_feasible for f in facts):
                            raise RuntimeError("native/Grid joint state changed feasibility between extrema")
                        infeasible = True
                        break
                    if not result.success or result.x is None:
                        raise RuntimeError("native/Grid joint projection solver failed: " + str(result.message))
                    extrema.append(float(objective @ result.x))
                if not infeasible:
                    extrema_by_objective[key] = extrema
            if not infeasible:
                minimum, maximum = extrema[0] + offset.minimum, extrema[1] + offset.maximum
                if minimum > maximum + _EPSILON:
                    raise RuntimeError("native/Grid extrema disagree beyond joint geometry tolerance")
                # Keep an outward hull when two LP endpoints differ only by
                # the existing joint-projection arithmetic tolerance.
                bounds = FiniteInterval(min(minimum, maximum), max(minimum, maximum))
        facts.append(NativeGridGapFact(ordinal, end, start, bounds, canonical, not infeasible))
    return NativeGridAssociationProof(_input_fingerprint(phase, width), tuple(facts),
        0 if system is None else len(system.bounds),
        0 if system is None else len(system.inequalities[1]), solve_count,
        native_ids, independent_constraints, grid_failure, unqualified_anchors, unqualified_native,
        uncompiled_grid_anchor_role_indices=uncompiled_anchors)
