"""Bounded, whole-atom interpretations of unresolved Cross families."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields
from enum import Enum
import math

from ...domain import FiniteInterval, ObservationId
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .robust_line_fit import physical_line_region


MAXIMUM_MEMBERSHIP_VISITS = 4096


class MembershipState(str, Enum):
    COMPLETE = "complete"
    NO_INDEPENDENT_ANCHOR = "no_independent_anchor"
    SEARCH_BOUND_EXCEEDED = "search_bound_exceeded"
    FIT_BOUND_EXCEEDED = "fit_bound_exceeded"


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
    visited_count: int = 0
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

    def __post_init__(self) -> None:
        if any(type(getattr(self, field.name)) is not int or getattr(self, field.name) < 0
               for field in fields(self)):
            raise ValueError("membership work must contain nonnegative actual counts")
        if (
            self.visited_count != self.trace_conflict_count + self.physical_region_count
            or self.physical_region_count != self.empty_region_count + self.feasible_set_count
            or self.maximality_extension_check_count > self.maximality_variable_visit_count
            or self.polygon_clip_count > 2 * self.raw_interval_count
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
    maximal_member_groups: tuple[tuple[ObservationId, ...], ...]
    work: MembershipWork

    def __post_init__(self) -> None:
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
            or self.work.visited_count > MAXIMUM_MEMBERSHIP_VISITS
            or self.work.raw_union_input_count > 2 * self.raw_transition_count * self.work.visited_count
            or self.work.raw_identity_check_count > self.raw_transition_count * self.work.visited_count
            or self.work.raw_interval_count > self.query_trace_count * self.work.physical_region_count
            or self.work.polygon_vertex_evaluation_count > self.work.physical_region_count * (
                4 * self.query_trace_count ** 2 + 10 * self.query_trace_count)
            or self.work.maximality_variable_visit_count > self.atom_count * self.work.feasible_set_count
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
    scale_px_per_mm: float, remaining_visits: int,
) -> MembershipScope:
    """Enumerate every maximal feasible superset of all independent anchors.

    Trace conflicts and empty full physical domains are monotone. No fit,
    loss, role permission, support ranking, or placement result prunes a set.
    A completed search retains every maximal interpretation; exhaustion
    exposes work only, never a purportedly complete prefix.
    """
    if not 0 <= remaining_visits <= MAXIMUM_MEMBERSHIP_VISITS:
        raise ValueError("membership visit budget is invalid")
    raw = {item.transition_id: item for item in transitions}
    members = {item.observation_id: frozenset(item.transition_ids) for item in atoms}
    if len(raw) != len(transitions) or len(members) != len(atoms) or any(
        not ids or not ids.issubset(raw) for ids in members.values()
    ):
        raise ValueError("membership atom lost original transition identity")
    anchors = tuple(sorted((item.observation_id for item in atoms
                            if item.independent_support_region_count >= 2), key=str))
    variables = tuple(sorted(set(members) - set(anchors), key=str))
    raw_count = len(set().union(*members.values())) if members else 0
    work: Counter[str] = Counter()

    def receipt(state: MembershipState, groups: tuple[tuple[ObservationId, ...], ...] = ()) -> MembershipScope:
        return MembershipScope(parent_family_id, role, state, anchors, len(atoms), raw_count,
                               len(query_trace_positions_px), groups, MembershipWork(**work))

    if not anchors:
        return receipt(MembershipState.NO_INDEPENDENT_ANCHOR)
    if not query_trace_positions_px or not math.isfinite(scale_px_per_mm) or scale_px_per_mm <= 0:
        raise ValueError("membership physical query is invalid")
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    allowance = spec.inlier_minimum_threshold_mm * scale_px_per_mm
    cap = math.tan(math.radians(spec.maximum_measurable_line_angle_degrees))
    reference = (query_trace_positions_px[0] + query_trace_positions_px[-1]) / 2
    feasible: set[int] = set()

    class Exhausted(Exception):
        pass

    def visit(mask: int, start: int, previous: frozenset[ObservationId], addition: frozenset[ObservationId]) -> None:
        if work['visited_count'] >= remaining_visits:
            raise Exhausted
        work['visited_count'] += 1
        work['raw_union_input_count'] += len(previous) + len(addition)
        identities = previous | addition
        work['raw_identity_check_count'] += len(identities)
        if len({raw[key].trace_coordinate_px for key in identities}) != len(identities):
            work['trace_conflict_count'] += 1
            return
        intervals = tuple((raw[key].trace_coordinate_px, FiniteInterval(
            raw[key].physical_position_interval_px.minimum - allowance,
            raw[key].physical_position_interval_px.maximum + allowance,
        )) for key in sorted(identities, key=str))
        work['physical_region_count'] += 1
        work['raw_interval_count'] += len(intervals)
        if physical_line_region(intervals, cap, reference, work=work) is None:
            work['empty_region_count'] += 1
            return
        feasible.add(mask)
        work['feasible_set_count'] += 1
        for index in range(start, len(variables)):
            visit(mask | (1 << index), index + 1, identities, members[variables[index]])

    try:
        visit(0, 0, frozenset(), frozenset().union(*(members[key] for key in anchors)))
    except Exhausted:
        return receipt(MembershipState.SEARCH_BOUND_EXCEEDED)
    maximal = []
    for mask in sorted(feasible):
        for index in range(len(variables)):
            work['maximality_variable_visit_count'] += 1
            if mask & (1 << index):
                continue
            work['maximality_extension_check_count'] += 1
            if (mask | (1 << index)) in feasible:
                break
        else:
            maximal.append(tuple(sorted((*anchors, *(name for index, name in enumerate(variables)
                                                     if mask & (1 << index))), key=str)))
    return receipt(MembershipState.COMPLETE, tuple(sorted(maximal)))
