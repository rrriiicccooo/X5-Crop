"""Bounded, whole-atom interpretations of unresolved Cross families."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields
from enum import Enum
import math

from ...domain import FiniteInterval, ObservationId
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .robust_line_fit import physical_line_region
from .template_measurement_plan_model import MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES


MAXIMUM_MEMBERSHIP_VISITS = 4096
_IDENTITY_WORD_BITS = 30


def _cache_temporary_bytes(atom_count: int, entry_count: int) -> int:
    return 256 + entry_count * (192 + 8 * ((atom_count + 29) // 30))


def _maximal_working_bytes(atom_count: int, group_count_bound: int) -> int:
    # Original list, sorting list, immutable output tuple and validation set
    # may coexist. Identity strings are borrowed; group tuples are new.
    return 256 + group_count_bound * (256 + 8 * atom_count) if group_count_bound else 0


def _identity_memory_plan(
    atom_count: int, anchor_count: int, transition_count: int, atom_input_count: int,
    raw_count: int, trace_count: int, visit_budget: int, retained_scope_prefix_bytes: int,
) -> tuple[int, int, int, int, int, int]:
    """Conservative working bytes for inputs, DFS, oracle and optional index.

    Input identities/measurements are borrowed. The new dict/set/list slots,
    frozensets and one-limb Python integers are included here. Each 30-bit
    word reserves 40 bytes (a list slot and a Python integer); the original
    A-bit memo keeps its separate, unchanged bound.
    """
    inputs = (8192 + 128 * transition_count + 256 * atom_count
              + 64 * atom_input_count + 64 * (raw_count + trace_count))
    if not anchor_count:
        return inputs, 0, 0, 0, 0, retained_scope_prefix_bytes + inputs
    # At depth <= A, each suspended search frame retains at most six A-long
    # tuple/list sequences (48 A bytes of references), plus masks, generator
    # state, local scalars and frame overhead. Reserve 64 A^2 + 4096 A.
    search = 64 * atom_count ** 2 + 4096 * atom_count
    # A full raw union retains <= T identities. A non-conflicting physical
    # call has <= S intervals and <= 2S+4 vertices per polygon. Include the
    # selected/inputs containers, new FiniteInterval objects and floats, and
    # old vertices + new list + return tuple coexisting during each clip.
    oracle = 8192 + 128 * raw_count + 1024 * trace_count + 64 * atom_count
    base_working = inputs + search + oracle
    # A complete binary search has <= B+1 <= V+1 leaves. No output prefix
    # can require more temporary group storage before success/exhaustion.
    maximal = _maximal_working_bytes(atom_count, visit_budget + 1)
    words = ((raw_count + _IDENTITY_WORD_BITS - 1) // _IDENTITY_WORD_BITS
             + (trace_count + _IDENTITY_WORD_BITS - 1) // _IDENTITY_WORD_BITS)
    retained = 256 + (atom_count - anchor_count + 1) * (256 + 40 * words)
    # Raw -> four one-limb positions/bits, plus exact trace -> position/bit.
    # These construction dicts are cleared before any oracle or memo entry.
    build = 512 + 384 * raw_count + 256 * trace_count
    # Include old/new one-limb values during |= and coexisting A-bit mask,
    # negation, selected-bit and XOR scalars, beyond the two scratch lists.
    check = 512 + 40 * words + 32 * ((atom_count + 29) // 30)
    peak = (retained_scope_prefix_bytes + base_working + maximal + retained
            + max(build, check + _cache_temporary_bytes(atom_count, visit_budget)))
    return base_working, maximal, retained, build, check, peak


class MembershipState(str, Enum):
    COMPLETE = "complete"
    NO_INDEPENDENT_ANCHOR = "no_independent_anchor"
    SEARCH_BOUND_EXCEEDED = "search_bound_exceeded"
    FIT_BOUND_EXCEEDED = "fit_bound_exceeded"


class MembershipIdentityPrecheckState(str, Enum):
    ENABLED = "enabled"
    NO_INDEPENDENT_ANCHOR = "no_independent_anchor"
    MEMORY_ALLOWANCE_EXCEEDED = "memory_allowance_exceeded"


@dataclass(frozen=True)
class MembershipIdentityPlan:
    state: MembershipIdentityPrecheckState
    input_transition_count: int
    atom_transition_input_count: int
    atom_transition_unique_count: int
    trace_identity_count: int
    visit_budget: int
    retained_scope_prefix_bytes: int
    base_working_temporary_bytes: int
    maximal_planned_working_bytes: int
    index_planned_retained_bytes: int
    index_planned_build_temporary_bytes: int
    precheck_planned_temporary_bytes: int
    planned_peak_temporary_bytes: int

    def __post_init__(self) -> None:
        if (not isinstance(self.state, MembershipIdentityPrecheckState)
                or any(type(getattr(self, field.name)) is not int or getattr(self, field.name) < 0
                       for field in fields(self) if field.name != 'state')
                or self.visit_budget > MAXIMUM_MEMBERSHIP_VISITS):
            raise ValueError("membership identity plan is invalid")


@dataclass(frozen=True)
class MembershipAtom:
    observation_id: ObservationId
    transition_ids: tuple[ObservationId, ...]
    independent_support_region_count: int


@dataclass(frozen=True)
class MembershipTransition:
    transition_id: ObservationId
    trace_coordinate_px: float
    physical_position_interval_px: FiniteInterval


@dataclass(frozen=True)
class MembershipWork:
    input_transition_visit_count: int = 0
    input_atom_visit_count: int = 0
    input_raw_visit_count: int = 0
    identity_index_raw_visit_count: int = 0
    identity_index_atom_visit_count: int = 0
    identity_index_raw_input_count: int = 0
    identity_index_bit_build_count: int = 0
    identity_index_zero_word_count: int = 0
    identity_index_word_update_count: int = 0
    identity_precheck_count: int = 0
    identity_precheck_atom_visit_count: int = 0
    identity_precheck_copy_word_count: int = 0
    identity_precheck_or_word_count: int = 0
    identity_precheck_popcount_word_count: int = 0
    identity_word_access_count: int = 0
    identity_precheck_mask_limb_span_count: int = 0
    identity_precheck_mask_control_logical_limb_bound: int = 0
    identity_logical_limb_access_bound: int = 0
    identity_precheck_pass_without_actual_count: int = 0
    initial_identity_reject_count: int = 0
    branch_identity_reject_count: int = 0
    maximality_identity_reject_count: int = 0
    visited_count: int = 0
    anchor_check_count: int = 0
    initial_filter_count: int = 0
    branch_filter_count: int = 0
    search_node_count: int = 0
    search_branch_count: int = 0
    search_maximum_depth: int = 0
    union_lookahead_count: int = 0
    union_lookahead_reuse_count: int = 0
    raw_union_atom_visit_count: int = 0
    raw_union_input_count: int = 0
    raw_identity_check_count: int = 0
    trace_conflict_count: int = 0
    physical_region_count: int = 0
    raw_interval_count: int = 0
    polygon_clip_count: int = 0
    polygon_vertex_evaluation_count: int = 0
    empty_region_count: int = 0
    feasible_set_count: int = 0
    maximality_variable_visit_count: int = 0
    maximality_extension_check_count: int = 0
    feasibility_lookup_count: int = 0
    cached_feasible_reuse_count: int = 0
    cached_infeasible_reuse_count: int = 0
    initial_filter_reuse_count: int = 0
    branch_filter_reuse_count: int = 0
    maximality_extension_reuse_count: int = 0
    cache_peak_entry_count: int = 0

    @property
    def identity_reject_count(self) -> int:
        return (self.initial_identity_reject_count + self.branch_identity_reject_count
                + self.maximality_identity_reject_count)

    def __post_init__(self) -> None:
        if any(type(getattr(self, field.name)) is not int or getattr(self, field.name) < 0
               for field in fields(self)):
            raise ValueError("membership work must contain nonnegative actual counts")
        if (
            self.visited_count != self.trace_conflict_count + self.physical_region_count
            or self.visited_count != (
                self.anchor_check_count + self.initial_filter_count + self.branch_filter_count
                + self.union_lookahead_count + self.maximality_extension_check_count
            )
            or self.physical_region_count != self.empty_region_count + self.feasible_set_count
            or self.anchor_check_count > 1
            or not (self.union_lookahead_count + self.union_lookahead_reuse_count
                    <= self.search_node_count
                    <= self.union_lookahead_count + self.union_lookahead_reuse_count + 1)
            or self.search_branch_count > self.union_lookahead_count
            or (self.search_node_count and self.search_node_count > 2 * self.search_branch_count + 1)
            or (self.search_node_count == 0) != (self.search_maximum_depth == 0)
            or self.search_maximum_depth > self.search_node_count
            or self.maximality_extension_check_count + self.maximality_extension_reuse_count
            + self.maximality_identity_reject_count
            > self.maximality_variable_visit_count
            or self.maximality_variable_visit_count > (
                self.maximality_extension_check_count
                + self.maximality_extension_reuse_count + self.maximality_identity_reject_count + 1
            )
            or self.feasibility_lookup_count < (
                self.visited_count + self.cached_feasible_reuse_count
                + self.cached_infeasible_reuse_count + self.identity_reject_count
            )
            or self.feasibility_lookup_count > (
                self.visited_count + self.cached_feasible_reuse_count
                + self.cached_infeasible_reuse_count + self.identity_reject_count + 1
            )
            or self.cached_feasible_reuse_count + self.cached_infeasible_reuse_count
            != (
                self.initial_filter_reuse_count + self.branch_filter_reuse_count
                + self.maximality_extension_reuse_count
            )
            or self.cache_peak_entry_count > self.visited_count
            or self.cache_peak_entry_count > MAXIMUM_MEMBERSHIP_VISITS
            or (self.cache_peak_entry_count == 0) != (self.visited_count == 0)
            or self.polygon_clip_count > 2 * self.raw_interval_count
            or self.identity_precheck_pass_without_actual_count > 1
            or self.identity_reject_count > self.identity_precheck_count
            or self.identity_word_access_count != (
                2 * self.identity_index_bit_build_count + self.identity_index_zero_word_count
                + 3 * self.identity_index_word_update_count
                + 2 * self.identity_precheck_copy_word_count
                + 3 * self.identity_precheck_or_word_count
                + self.identity_precheck_popcount_word_count)
            or self.identity_precheck_mask_control_logical_limb_bound != 32 * (
                self.identity_precheck_mask_limb_span_count + self.identity_precheck_atom_visit_count)
            or self.identity_logical_limb_access_bound != (
                self.identity_word_access_count + self.identity_precheck_mask_control_logical_limb_bound)
        ):
            raise ValueError("membership search lost its work ledger")


@dataclass(frozen=True)
class MembershipScope:
    parent_family_id: str
    role: BoundaryRole
    state: MembershipState
    anchor_observation_ids: tuple[ObservationId, ...]
    atom_count: int
    raw_transition_count: int
    query_trace_count: int
    identity_plan: MembershipIdentityPlan
    maximal_member_groups: tuple[tuple[ObservationId, ...], ...]
    work: MembershipWork

    @property
    def cache_temporary_bytes(self) -> int:
        """Membership working scratch and memo bound for the source memory owner.

        Includes the base input mappings, suspended DFS and physical oracle;
        prior returned receipts and current maximal-list/sort/validation
        storage are included. Later registration plans/fits are outside it.
        """
        plan = self.identity_plan
        memo = (_cache_temporary_bytes(self.atom_count, self.work.cache_peak_entry_count)
                if self.work.feasibility_lookup_count else 0)
        base = (plan.retained_scope_prefix_bytes + plan.base_working_temporary_bytes
                + _maximal_working_bytes(self.atom_count, self.work.search_branch_count + 1
                                         if self.work.search_node_count else 0))
        if plan.state != MembershipIdentityPrecheckState.ENABLED:
            return base + memo
        return (base + plan.index_planned_retained_bytes
                + max(plan.index_planned_build_temporary_bytes,
                      plan.precheck_planned_temporary_bytes + memo))

    @property
    def retained_bytes(self) -> int:
        """Returned scope/plan/work/group storage, with input identities borrowed."""
        return (8192 + 16 * self.atom_count
                + sum(96 + 8 * len(group) for group in self.maximal_member_groups))

    def __post_init__(self) -> None:
        plan = self.identity_plan
        expected_memory = _identity_memory_plan(
            self.atom_count, len(self.anchor_observation_ids), plan.input_transition_count,
            plan.atom_transition_input_count, self.raw_transition_count,
            plan.trace_identity_count, plan.visit_budget, plan.retained_scope_prefix_bytes)
        has_anchor = bool(self.anchor_observation_ids)
        enabled = plan.state == MembershipIdentityPrecheckState.ENABLED
        words = ((self.raw_transition_count + _IDENTITY_WORD_BITS - 1) // _IDENTITY_WORD_BITS
                 + (plan.trace_identity_count + _IDENTITY_WORD_BITS - 1) // _IDENTITY_WORD_BITS)
        index_fields = (
            'identity_index_raw_visit_count', 'identity_index_atom_visit_count',
            'identity_index_raw_input_count', 'identity_index_bit_build_count',
            'identity_index_zero_word_count', 'identity_index_word_update_count',
            'identity_precheck_count', 'identity_precheck_atom_visit_count',
            'identity_precheck_copy_word_count', 'identity_precheck_or_word_count',
            'identity_precheck_popcount_word_count', 'identity_precheck_pass_without_actual_count',
            'identity_word_access_count',
            'identity_precheck_mask_limb_span_count',
            'identity_precheck_mask_control_logical_limb_bound', 'identity_logical_limb_access_bound',
            'initial_identity_reject_count', 'branch_identity_reject_count',
            'maximality_identity_reject_count',
        )
        if (
            not self.parent_family_id or self.role not in (BoundaryRole.TOP, BoundaryRole.BOTTOM)
            or self.state not in (MembershipState.COMPLETE, MembershipState.NO_INDEPENDENT_ANCHOR,
                                  MembershipState.SEARCH_BOUND_EXCEEDED)
            or min(self.atom_count, self.raw_transition_count, self.query_trace_count) < 0
            or tuple(sorted(set(self.anchor_observation_ids), key=str)) != self.anchor_observation_ids
            or len(self.anchor_observation_ids) > self.atom_count
            or (self.state == MembershipState.NO_INDEPENDENT_ANCHOR) != (not self.anchor_observation_ids)
            or (self.state != MembershipState.COMPLETE and self.maximal_member_groups)
            or len(set(self.maximal_member_groups)) != len(self.maximal_member_groups)
            or any(tuple(sorted(set(group), key=str)) != group
                   or not set(self.anchor_observation_ids).issubset(group)
                   or len(group) > self.atom_count for group in self.maximal_member_groups)
            or len(self.maximal_member_groups) > self.work.search_node_count
            or len(self.maximal_member_groups) > (self.work.search_branch_count + 1
                                                  if self.work.search_node_count else 0)
            or self.work.visited_count > MAXIMUM_MEMBERSHIP_VISITS
            or self.work.visited_count > plan.visit_budget
            or plan.input_transition_count < self.raw_transition_count
            or not self.raw_transition_count <= plan.atom_transition_unique_count <= plan.atom_transition_input_count
            or plan.atom_transition_unique_count > self.atom_count * self.raw_transition_count
            or not 0 <= plan.trace_identity_count <= self.raw_transition_count
            or (plan.trace_identity_count == 0) != (self.raw_transition_count == 0)
            or (self.atom_count == 0) != (plan.atom_transition_input_count == 0)
            or tuple(getattr(plan, name) for name in (
                'base_working_temporary_bytes', 'maximal_planned_working_bytes', 'index_planned_retained_bytes',
                'index_planned_build_temporary_bytes', 'precheck_planned_temporary_bytes',
                'planned_peak_temporary_bytes')) != expected_memory
            or (plan.state == MembershipIdentityPrecheckState.NO_INDEPENDENT_ANCHOR) != (not has_anchor)
            or (has_anchor and enabled != (
                plan.planned_peak_temporary_bytes <= MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES))
            or self.work.input_transition_visit_count != plan.input_transition_count
            or self.work.input_atom_visit_count != self.atom_count
            or self.work.input_raw_visit_count != (
                plan.atom_transition_input_count + plan.atom_transition_unique_count)
            or (not enabled and any(getattr(self.work, name) for name in index_fields))
            or (enabled and (
                self.work.identity_index_raw_visit_count != self.raw_transition_count
                or self.work.identity_index_atom_visit_count != self.atom_count
                or self.work.identity_index_raw_input_count != plan.atom_transition_unique_count
                or self.work.identity_index_bit_build_count != self.raw_transition_count + plan.trace_identity_count
                or self.work.identity_index_zero_word_count != (
                    self.atom_count - len(self.anchor_observation_ids) + 1) * words
                or self.work.identity_index_word_update_count != 2 * plan.atom_transition_unique_count
                or self.work.identity_precheck_copy_word_count != self.work.identity_precheck_count * words
                or self.work.identity_precheck_popcount_word_count != self.work.identity_precheck_count * words
                or self.work.identity_precheck_or_word_count != self.work.identity_precheck_atom_visit_count * words
                or self.work.identity_precheck_atom_visit_count > (
                    self.atom_count - len(self.anchor_observation_ids)) * self.work.identity_precheck_count
                or self.work.identity_precheck_mask_limb_span_count < self.work.identity_precheck_atom_visit_count
                or self.work.identity_precheck_mask_limb_span_count > (
                    (self.atom_count - len(self.anchor_observation_ids) + 29) // 30
                    * self.work.identity_precheck_atom_visit_count)
                or self.work.identity_precheck_count != (
                    self.work.identity_reject_count + self.work.initial_filter_count
                    + self.work.branch_filter_count + self.work.maximality_extension_check_count
                    + self.work.identity_precheck_pass_without_actual_count)
            ))
            or self.work.initial_filter_count + self.work.initial_filter_reuse_count
            + self.work.initial_identity_reject_count
            > self.atom_count - len(self.anchor_observation_ids)
            or self.work.branch_filter_count + self.work.branch_filter_reuse_count
            + self.work.branch_identity_reject_count
            > self.atom_count * self.work.search_branch_count
            or self.work.feasibility_lookup_count > (
                1 + self.atom_count + self.atom_count * self.work.search_branch_count
                + self.work.search_node_count
                + self.atom_count * self.work.search_node_count
            )
            or self.work.feasibility_lookup_count != (
                self.work.visited_count
                + self.work.cached_feasible_reuse_count
                + self.work.cached_infeasible_reuse_count
                + self.work.identity_reject_count
                + int(self.state == MembershipState.SEARCH_BOUND_EXCEEDED)
            )
            or self.work.branch_filter_count > self.atom_count * self.work.search_branch_count
            or self.work.search_maximum_depth > self.atom_count
            or self.work.raw_union_atom_visit_count > self.atom_count * self.work.visited_count
            or self.work.raw_union_input_count > self.raw_transition_count * self.work.raw_union_atom_visit_count
            or self.work.raw_identity_check_count > self.raw_transition_count * self.work.visited_count
            or self.work.raw_interval_count > self.query_trace_count * self.work.physical_region_count
            or self.work.polygon_vertex_evaluation_count > self.work.physical_region_count * (
                4 * self.query_trace_count ** 2 + 10 * self.query_trace_count)
            or self.work.maximality_variable_visit_count > self.atom_count * self.work.search_node_count
            or (self.state == MembershipState.COMPLETE and (
                self.work.search_node_count != (self.work.union_lookahead_count
                                               + self.work.union_lookahead_reuse_count)
                or self.work.maximality_variable_visit_count != (
                    self.work.maximality_extension_check_count
                    + self.work.maximality_extension_reuse_count
                    + self.work.maximality_identity_reject_count
                )
                or self.work.identity_precheck_pass_without_actual_count
            ))
            or (self.state == MembershipState.NO_INDEPENDENT_ANCHOR and any(
                getattr(self.work, field.name) for field in fields(self.work)
                if field.name not in ('input_transition_visit_count', 'input_atom_visit_count', 'input_raw_visit_count')
            ))
        ):
            raise ValueError("membership scope is invalid or exceeds finite work bounds")


@dataclass(frozen=True)
class MembershipFitBudget:
    role: BoundaryRole
    registered_run_count: int
    original_family_fit_count: int
    original_constrained_fit_count: int
    additional_union_count: int

    @property
    def admits_all(self) -> bool:
        return (
            self.registered_run_count + self.original_family_fit_count + self.additional_union_count
            <= 3 * self.registered_run_count
            and self.original_constrained_fit_count + self.additional_union_count
            <= 2 * self.registered_run_count
        )

    def __post_init__(self) -> None:
        if self.role not in (BoundaryRole.TOP, BoundaryRole.BOTTOM) or any(
            type(value) is not int or value < 0 for value in (
                self.registered_run_count, self.original_family_fit_count,
                self.original_constrained_fit_count, self.additional_union_count)):
            raise ValueError("membership fit preflight is invalid")


@dataclass(frozen=True)
class MembershipReceipt:
    state: MembershipState
    scopes: tuple[MembershipScope, ...]
    fit_budgets: tuple[MembershipFitBudget, ...]
    original_observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        exhausted = any(scope.state == MembershipState.SEARCH_BOUND_EXCEEDED for scope in self.scopes)
        retained_prefix = 0
        for scope in self.scopes:
            if scope.identity_plan.retained_scope_prefix_bytes != retained_prefix:
                raise ValueError("membership scopes lost retained receipt prefix memory")
            retained_prefix += scope.retained_bytes
        if (
            self.state not in (MembershipState.COMPLETE, MembershipState.SEARCH_BOUND_EXCEEDED,
                               MembershipState.FIT_BOUND_EXCEEDED)
            or tuple(sorted(set(self.original_observation_ids), key=str)) != self.original_observation_ids
            or sum(scope.work.visited_count for scope in self.scopes) > MAXIMUM_MEMBERSHIP_VISITS
            or len({scope.parent_family_id for scope in self.scopes}) != len(self.scopes)
            or exhausted != (self.state == MembershipState.SEARCH_BOUND_EXCEEDED)
            or (exhausted and self.fit_budgets)
            or (not exhausted and tuple(item.role for item in self.fit_budgets)
                != (BoundaryRole.TOP, BoundaryRole.BOTTOM))
            or (not exhausted and (self.state == MembershipState.COMPLETE)
                != all(item.admits_all for item in self.fit_budgets))
        ):
            raise ValueError("membership augmentation lost whole-lane atomicity")


@dataclass(frozen=True)
class MembershipProjectionCoverage:
    """One enumerated interpretation represented in the actual solver input."""

    parent_family_id: str
    role: BoundaryRole
    member_observation_ids: tuple[ObservationId, ...]
    member_transition_ids: tuple[ObservationId, ...]
    solver_observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if not self.parent_family_id or self.role not in (BoundaryRole.TOP, BoundaryRole.BOTTOM):
            raise ValueError("membership projection requires its parent and role")
        for identities in (self.member_observation_ids, self.member_transition_ids, self.solver_observation_ids):
            if not identities or tuple(sorted(set(identities), key=str)) != identities:
                raise ValueError("membership projection identities are incomplete")


def new_membership_groups(
    scopes: tuple[MembershipScope, ...], atoms: dict[ObservationId, MembershipAtom],
    existing_unions: set[tuple[BoundaryRole, tuple[ObservationId, ...]]],
) -> dict[tuple[BoundaryRole, tuple[ObservationId, ...], tuple[ObservationId, ...]], tuple[str, ...]]:
    """Deduplicate geometry without discarding distinct member provenance."""
    groups: dict[tuple[BoundaryRole, tuple[ObservationId, ...], tuple[ObservationId, ...]], set[str]] = {}
    for scope in scopes:
        for members in scope.maximal_member_groups:
            union = tuple(sorted({identity for member in members for identity in atoms[member].transition_ids}, key=str))
            if len(members) < 2 or (scope.role, union) in existing_unions:
                continue
            groups.setdefault((scope.role, members, union), set()).add(scope.parent_family_id)
    return {key: tuple(sorted(parents)) for key, parents in groups.items()}


def enumerate_membership_scope(
    *, parent_family_id: str, role: BoundaryRole, atoms: tuple[MembershipAtom, ...],
    transitions: tuple[MembershipTransition, ...], query_trace_positions_px: tuple[int, ...],
    scale_px_per_mm: float, remaining_visits: int, retained_scope_prefix_bytes: int = 0,
) -> MembershipScope:
    """Enumerate every maximal feasible superset of all independent anchors.

    Trace conflicts and empty full physical domains are monotone. Include /
    exclude branches preserve all feasible maximal interpretations. A whole
    remaining-union lookahead closes a compatible branch only after checking
    every previously excluded atom for a feasible extension. Every oracle
    checks the complete raw union; pairwise substitution is never used.
    A search node reuses its own exact prior feasibility check when at most
    one pending atom remains; all pending atoms passed the full required-union
    filter. Completed raw feasibility checks are also reused by exact integer
    masks within this scope for the bounded filter and maximality purposes.
    On an eligible memo miss, an optional exact raw/trace bitset precheck
    can reject an identity conflict without an actual visit or memo entry.
    Passing it always continues to the original full oracle. Anchors and
    true whole unions always take that original actual path.
    It never substitutes pairwise compatibility for a larger union. No fit,
    loss, role permission, support ranking, or placement result prunes a set.
    Exhaustion exposes work only, never a purportedly complete prefix.
    """
    if (not 0 <= remaining_visits <= MAXIMUM_MEMBERSHIP_VISITS
            or type(retained_scope_prefix_bytes) is not int or retained_scope_prefix_bytes < 0):
        raise ValueError("membership visit budget is invalid")
    work: Counter[str] = Counter()
    raw = {}
    for item in transitions:
        work['input_transition_visit_count'] += 1
        raw[item.transition_id] = item
    members = {}
    scope_raw: set[ObservationId] = set()
    scope_traces: set[float] = set()
    atom_input_count = atom_unique_count = 0
    for item in atoms:
        work['input_atom_visit_count'] += 1
        atom_input_count += len(item.transition_ids)
        work['input_raw_visit_count'] += len(item.transition_ids)
        ids = frozenset(item.transition_ids)
        atom_unique_count += len(ids)
        if not ids:
            raise ValueError("membership atom lost original transition identity")
        for identity in ids:
            work['input_raw_visit_count'] += 1
            if identity not in raw:
                raise ValueError("membership atom lost original transition identity")
            scope_raw.add(identity)
            scope_traces.add(raw[identity].trace_coordinate_px)
        members[item.observation_id] = ids
    if len(raw) != len(transitions) or len(members) != len(atoms):
        raise ValueError("membership atom lost original transition identity")
    anchors = tuple(sorted((item.observation_id for item in atoms
                            if item.independent_support_region_count >= 2), key=str))
    variables = tuple(sorted(set(members) - set(anchors), key=str))
    raw_count = len(scope_raw)
    memory = _identity_memory_plan(len(atoms), len(anchors), len(transitions), atom_input_count,
                                   raw_count, len(scope_traces), remaining_visits, retained_scope_prefix_bytes)
    identity_state = (MembershipIdentityPrecheckState.NO_INDEPENDENT_ANCHOR if not anchors else
                      MembershipIdentityPrecheckState.ENABLED
                      if memory[-1] <= MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES else
                      MembershipIdentityPrecheckState.MEMORY_ALLOWANCE_EXCEEDED)
    identity_plan = MembershipIdentityPlan(identity_state, len(transitions), atom_input_count,
        atom_unique_count, len(scope_traces), remaining_visits, retained_scope_prefix_bytes, *memory)

    def receipt(state: MembershipState, groups: tuple[tuple[ObservationId, ...], ...] = ()) -> MembershipScope:
        work['identity_logical_limb_access_bound'] = (
            work['identity_word_access_count'] + work['identity_precheck_mask_control_logical_limb_bound'])
        return MembershipScope(parent_family_id, role, state, anchors, len(atoms), raw_count,
                               len(query_trace_positions_px), identity_plan, groups, MembershipWork(**work))

    if not anchors:
        return receipt(MembershipState.NO_INDEPENDENT_ANCHOR)
    # Reserve the complete bounded memo before any entries are allocated.
    # It uses the existing fixed source allowance, not an extra resource pool.
    if _cache_temporary_bytes(len(atoms), remaining_visits) > MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES:
        raise ValueError("membership cache exceeds the fixed source memory allowance")
    if not query_trace_positions_px or not math.isfinite(scale_px_per_mm) or scale_px_per_mm <= 0:
        raise ValueError("membership physical query is invalid")
    feasibility_cache: dict[int, bool] = {}
    cache_read_purposes = {
        'initial_filter_count': 'initial_filter_reuse_count',
        'branch_filter_count': 'branch_filter_reuse_count',
        'maximality_extension_check_count': 'maximality_extension_reuse_count',
    }
    identity_reject_fields = {
        'initial_filter_count': 'initial_identity_reject_count',
        'branch_filter_count': 'branch_identity_reject_count',
        'maximality_extension_check_count': 'maximality_identity_reject_count',
    }
    raw_words = (raw_count + _IDENTITY_WORD_BITS - 1) // _IDENTITY_WORD_BITS
    trace_words = (len(scope_traces) + _IDENTITY_WORD_BITS - 1) // _IDENTITY_WORD_BITS
    anchor_raw_bits: list[int] = []
    anchor_trace_bits: list[int] = []
    variable_bits: list[tuple[list[int], list[int]]] = []
    if identity_state == MembershipIdentityPrecheckState.ENABLED:
        raw_positions = {}
        trace_positions = {}
        try:
            for raw_index, identity in enumerate(scope_raw):
                work['identity_index_raw_visit_count'] += 1
                trace = raw[identity].trace_coordinate_px
                if trace not in trace_positions:
                    trace_index = len(trace_positions)
                    trace_positions[trace] = (trace_index // _IDENTITY_WORD_BITS,
                                              1 << (trace_index % _IDENTITY_WORD_BITS))
                    work['identity_index_bit_build_count'] += 1
                    work['identity_word_access_count'] += 2
                trace_word, trace_bit = trace_positions[trace]
                raw_positions[identity] = (raw_index // _IDENTITY_WORD_BITS,
                    1 << (raw_index % _IDENTITY_WORD_BITS), trace_word, trace_bit)
                work['identity_index_bit_build_count'] += 1
                work['identity_word_access_count'] += 2
            anchor_raw_bits = [0] * raw_words
            anchor_trace_bits = [0] * trace_words
            work['identity_index_zero_word_count'] += raw_words + trace_words
            work['identity_word_access_count'] += raw_words + trace_words
            for atom_index, key in enumerate((*anchors, *variables)):
                work['identity_index_atom_visit_count'] += 1
                if atom_index < len(anchors):
                    raw_bits, trace_bits = anchor_raw_bits, anchor_trace_bits
                else:
                    raw_bits, trace_bits = [0] * raw_words, [0] * trace_words
                    work['identity_index_zero_word_count'] += raw_words + trace_words
                    work['identity_word_access_count'] += raw_words + trace_words
                    variable_bits.append((raw_bits, trace_bits))
                for identity in members[key]:
                    work['identity_index_raw_input_count'] += 1
                    raw_word, raw_bit, trace_word, trace_bit = raw_positions[identity]
                    raw_bits[raw_word] |= raw_bit
                    trace_bits[trace_word] |= trace_bit
                    work['identity_index_word_update_count'] += 2
                    work['identity_word_access_count'] += 6
        finally:
            raw_positions.clear()
            trace_positions.clear()

    def identity_possible(mask: int) -> bool:
        # Equal raw and exact-trace cardinalities hold iff no two different
        # raw identities share a trace. Sharing the same raw remains legal.
        # Each list element is one 30-bit limb: the counters below count the
        # actual fixed-width copy/OR/popcount loops, including zero words.
        work['identity_precheck_count'] += 1
        raw_bits, trace_bits = anchor_raw_bits.copy(), anchor_trace_bits.copy()
        work['identity_precheck_copy_word_count'] += raw_words + trace_words
        work['identity_word_access_count'] += 2 * (raw_words + trace_words)
        while mask:
            # Source-level conservative bound, not a CPython instruction or
            # machine-read counter: for L positive mask limbs, 32(L+1)
            # covers unary negation, signed AND conversion/temporaries,
            # bit_length/index arithmetic, XOR and loop bookkeeping. Record
            # the actual width at every selection; a high sparse bit still
            # costs its full width, not one selected-atom visit.
            mask_limbs = (mask.bit_length() + _IDENTITY_WORD_BITS - 1) // _IDENTITY_WORD_BITS
            work['identity_precheck_mask_limb_span_count'] += mask_limbs
            work['identity_precheck_mask_control_logical_limb_bound'] += 32 * (mask_limbs + 1)
            bit = mask & -mask
            index = bit.bit_length() - 1
            work['identity_precheck_atom_visit_count'] += 1
            atom_raw, atom_trace = variable_bits[index]
            for word_index in range(raw_words):
                raw_bits[word_index] |= atom_raw[word_index]
                work['identity_precheck_or_word_count'] += 1
                work['identity_word_access_count'] += 3
            for word_index in range(trace_words):
                trace_bits[word_index] |= atom_trace[word_index]
                work['identity_precheck_or_word_count'] += 1
                work['identity_word_access_count'] += 3
            mask ^= bit
        raw_cardinality = sum(word.bit_count() for word in raw_bits)
        trace_cardinality = sum(word.bit_count() for word in trace_bits)
        work['identity_precheck_popcount_word_count'] += raw_words + trace_words
        work['identity_word_access_count'] += raw_words + trace_words
        return raw_cardinality == trace_cardinality

    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    allowance = spec.inlier_minimum_threshold_mm * scale_px_per_mm
    cap = math.tan(math.radians(spec.maximum_measurable_line_angle_degrees))
    reference = (query_trace_positions_px[0] + query_trace_positions_px[-1]) / 2
    maximal: list[tuple[ObservationId, ...]] = []

    class Exhausted(Exception):
        pass

    def feasible(mask: int, purpose: str) -> bool:
        work['feasibility_lookup_count'] += 1
        reuse_field = cache_read_purposes.get(purpose)
        if reuse_field is not None and mask in feasibility_cache:
            result = feasibility_cache[mask]
            work[reuse_field] += 1
            work['cached_feasible_reuse_count' if result else 'cached_infeasible_reuse_count'] += 1
            return result
        if (reuse_field is not None and identity_state == MembershipIdentityPrecheckState.ENABLED
                and not identity_possible(mask)):
            work[identity_reject_fields[purpose]] += 1
            return False
        if work['visited_count'] >= remaining_visits:
            if reuse_field is not None and identity_state == MembershipIdentityPrecheckState.ENABLED:
                work['identity_precheck_pass_without_actual_count'] += 1
            raise Exhausted
        work['visited_count'] += 1
        work[purpose] += 1
        cache_key = mask
        selected = list(anchors)
        while mask:
            bit = mask & -mask
            selected.append(variables[bit.bit_length() - 1])
            mask ^= bit
        inputs = tuple(members[key] for key in selected)
        work['raw_union_atom_visit_count'] += len(inputs)
        # Atoms may share raw identities. Count every actual union input, not
        # only the unique result, with the finite A * T * V scope bound.
        work['raw_union_input_count'] += sum(map(len, inputs))
        identities = frozenset().union(*inputs)
        work['raw_identity_check_count'] += len(identities)
        if len({raw[key].trace_coordinate_px for key in identities}) != len(identities):
            work['trace_conflict_count'] += 1
            feasibility_cache[cache_key] = False
            work['cache_peak_entry_count'] = len(feasibility_cache)
            return False
        intervals = tuple((raw[key].trace_coordinate_px, FiniteInterval(
            raw[key].physical_position_interval_px.minimum - allowance,
            raw[key].physical_position_interval_px.maximum + allowance,
        )) for key in sorted(identities, key=str))
        work['physical_region_count'] += 1
        work['raw_interval_count'] += len(intervals)
        if physical_line_region(intervals, cap, reference, work=work) is None:
            work['empty_region_count'] += 1
            feasibility_cache[cache_key] = False
            work['cache_peak_entry_count'] = len(feasibility_cache)
            return False
        work['feasible_set_count'] += 1
        feasibility_cache[cache_key] = True
        work['cache_peak_entry_count'] = len(feasibility_cache)
        return True

    def search(required: int, pending: tuple[int, ...], excluded: tuple[int, ...], depth: int) -> None:
        work['search_node_count'] += 1
        work['search_maximum_depth'] = max(work['search_maximum_depth'], depth)
        union = required | sum(1 << index for index in pending)
        # Required is feasible by the anchor check or the parent's filter.
        # With one pending atom its full union was checked by that same
        # filter. Repeating either check spends the shared oracle allowance
        # without adding evidence. Two or more pending atoms still require
        # a joint check, even if every pair was individually feasible.
        known_union = len(pending) <= 1
        if known_union:
            work['union_lookahead_reuse_count'] += 1
        if known_union or feasible(union, 'union_lookahead_count'):
            for index in excluded:
                work['maximality_variable_visit_count'] += 1
                if feasible(union | (1 << index), 'maximality_extension_check_count'):
                    return
            maximal.append(tuple(sorted((*anchors, *(variables[index] for index in range(len(variables))
                                                       if union & (1 << index))), key=str)))
            return
        # Every pending atom is individually feasible with required. Thus a
        # failed whole union has a pending atom and both branches are complete.
        work['search_branch_count'] += 1
        selected, *rest = pending
        tail = tuple(rest)
        included = required | (1 << selected)
        next_pending = tuple(index for index in tail
                             if feasible(included | (1 << index), 'branch_filter_count'))
        next_excluded = tuple(index for index in excluded
                              if feasible(included | (1 << index), 'branch_filter_count'))
        search(included, next_pending, next_excluded, depth + 1)
        search(required, tail, (*excluded, selected), depth + 1)

    result: MembershipScope | None = None
    try:
        if feasible(0, 'anchor_check_count'):
            pending = tuple(index for index in range(len(variables))
                            if feasible(1 << index, 'initial_filter_count'))
            search(0, pending, (), 1)
        result = receipt(MembershipState.COMPLETE, tuple(sorted(maximal)))
    except Exhausted:
        result = receipt(MembershipState.SEARCH_BOUND_EXCEEDED)
    finally:
        feasibility_cache.clear()
        anchor_raw_bits.clear()
        anchor_trace_bits.clear()
        for raw_bits, trace_bits in variable_bits:
            raw_bits.clear()
            trace_bits.clear()
        variable_bits.clear()
        raw.clear()
        members.clear()
        scope_raw.clear()
        scope_traces.clear()
        maximal.clear()
        # search captures itself recursively; break that cell explicitly so
        # discarded output prefixes and working containers do not await GC.
        search = None
    assert result is not None
    return result
