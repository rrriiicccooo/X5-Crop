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
from .template_model import SeparatorRelation, SequenceBindingUse, SequenceFit
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


@dataclass(frozen=True)
class NativeGridAssociationProof:
    input_fingerprint: str
    facts: tuple[NativeGridGapFact, ...]
    variable_count: int
    inequality_count: int
    lp_solve_count: int
    state: EvidenceState = field(init=False)

    def __post_init__(self) -> None:
        ordinals = tuple(f.relation_ordinal for f in self.facts)
        if (len(self.input_fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in self.input_fingerprint)
                or not self.facts or ordinals != tuple(sorted(set(ordinals)))
                or any(type(value) is not int or value < 0 for value in (
                    self.variable_count, self.inequality_count, self.lp_solve_count))
                or self.variable_count not in (0,) and self.variable_count < 3
                or bool(self.variable_count) != bool(self.inequality_count)
                or bool(self.variable_count) != bool(self.lp_solve_count)
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
    return 128 + 8 * role_count * (role_count + 10)


def native_grid_bytes_bound(role_count: int) -> int:
    native_grid_work_bound(role_count)
    return 8192 + 512 * role_count * (role_count + 10)


def _grid_authorized(phase):
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
    if global_authority is None and not nominal_supported:
        return False
    # The shared system consumes every retained coordinate constraint, not
    # only the native endpoint at this particular adjacency. Cross-dependent
    # partial-height anchors cannot supply a pre-Cross physical conclusion.
    required = set(() if state is None else state.phase_anchor_role_indices)
    if global_authority is not None:
        required.update(c.role_index for c in global_authority.constraints
                        if c.kind == GlobalLatticeConstraintKind.DIRECT_ROLE_COORDINATE)
    direct = phase.direct_role_binding_authority
    facts = {} if direct is None else {f.role_index: f for f in direct.facts}
    return all(i in facts and fit.role_bindings[i] is not None
               and facts[i].observation_id == fit.role_bindings[i].observation_id
               and facts[i].has_unconditional_coordinate_authority for i in required)


def assess_native_grid_association(phase: PhaseFitResult, source_frame_width_authority=None):
    """Project a conservative actual gap without assuming its desired sign."""
    fit = phase.best
    if fit is None:
        return None
    ordinals = native_grid_relation_ordinals(fit)
    if not ordinals:
        return None
    # Imported at execution time: placement composes from this same owner,
    # while this sequence-only proof must be available before Cross exists.
    from .template_feasible_geometry import sequence_feasible_system
    system = roles = None
    grid_authorized = _grid_authorized(phase)
    direct = phase.direct_role_binding_authority
    facts_by_role = {} if direct is None else {f.role_index: f for f in direct.facts}
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
            return role.coefficients, FiniteInterval.exact(role.constant)
        if source.native_role_index in anchors:
            coefficients = roles[source.native_role_index].coefficients.copy()
            offset = FiniteInterval.exact(roles[source.native_role_index].constant)
        else:
            coefficients = np.zeros(len(system.bounds), dtype=np.float64)
            offset = source.native_full_interval_px
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
            system, roles = sequence_feasible_system(fit, _qualified_global(phase))
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
        0 if system is None else len(system.inequalities[1]), solve_count)
