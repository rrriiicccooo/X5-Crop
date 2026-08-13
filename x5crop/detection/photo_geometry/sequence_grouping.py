"""Bounded grouping of role-bound sequence observations."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import replace
import math

from ...domain import FiniteInterval, ObservationId
from .interval_math import common, intersect, multiply, subtract
from .model import BoundaryRole
from .observation_types import (
    OrdinalBoundaryRole,
    SeparatorBandRoleProposal,
    SequenceGroupingWork,
    SequenceHypothesisGroup,
    SequenceRoleProposal,
)
from ...run_local_identity import run_local_id


def _stable_id(prefix: str, *parts: object) -> str:
    return run_local_id(prefix, *parts)


def ordered_ordinal_roles(output_slot_count: int) -> tuple[OrdinalBoundaryRole, ...]:
    if output_slot_count <= 0:
        raise ValueError("sequence proposal requires a positive output-slot count")
    return tuple(
        OrdinalBoundaryRole(
            role_index=(ordinal - 1) * 2 + role_offset,
            lane_ordinal=ordinal,
            role=role,
        )
        for ordinal in range(1, output_slot_count + 1)
        for role_offset, role in enumerate((BoundaryRole.START, BoundaryRole.END))
    )


def group_support_exclusion_authorized(
    *,
    role_coordinates_px: tuple[float, ...],
    role_identities: tuple[tuple[int, BoundaryRole], ...],
    transition_id_sets: tuple[tuple[ObservationId, ...], ...],
    frame_width_lower_px: float,
) -> bool:
    if (
        len(role_coordinates_px) != len(role_identities)
        or len(role_coordinates_px) != len(transition_id_sets)
        or not math.isfinite(frame_width_lower_px)
        or frame_width_lower_px <= 0.0
    ):
        raise ValueError("group support evidence is invalid")
    identities = [set(map(str, values)) for values in transition_id_sets]
    for left_index, left_ids in enumerate(identities):
        for right_index in range(left_index + 1, len(identities)):
            if not left_ids.isdisjoint(identities[right_index]):
                continue
            left_role = role_identities[left_index]
            right_role = role_identities[right_index]
            opposite_pair = (
                left_role[0] == right_role[0]
                and {left_role[1], right_role[1]}
                == {BoundaryRole.START, BoundaryRole.END}
            )
            separated = (
                abs(role_coordinates_px[left_index] - role_coordinates_px[right_index])
                + 1.0e-9
                >= frame_width_lower_px
            )
            if opposite_pair or separated:
                return True
    return False


def _endpoint_peak_intervals(
    proposals: tuple[SequenceRoleProposal, ...],
) -> tuple[FiniteInterval, ...]:
    if not proposals:
        return ()
    proposal_by_id = {proposal.proposal_id: proposal for proposal in proposals}
    starts: dict[float, list[str]] = {}
    ends: dict[float, list[str]] = {}
    for proposal in proposals:
        starts.setdefault(proposal.phase_interval_px.minimum, []).append(
            proposal.proposal_id
        )
        ends.setdefault(proposal.phase_interval_px.maximum, []).append(
            proposal.proposal_id
        )
    active: set[str] = set()
    candidate_sets: list[frozenset[str]] = []
    for coordinate in sorted(set(starts) | set(ends)):
        active.update(starts.get(coordinate, ()))
        if active and ends.get(coordinate):
            candidate_sets.append(frozenset(active))
        active.difference_update(ends.get(coordinate, ()))
    unique_sets = tuple(dict.fromkeys(candidate_sets))
    maximal_sets = tuple(
        active_set
        for active_set in unique_sets
        if not any(active_set < other for other in unique_sets)
    )
    maximal = tuple(
        FiniteInterval(
            max(
                proposal_by_id[proposal_id].phase_interval_px.minimum
                for proposal_id in active_set
            ),
            min(
                proposal_by_id[proposal_id].phase_interval_px.maximum
                for proposal_id in active_set
            ),
        )
        for active_set in maximal_sets
    )
    return tuple(
        FiniteInterval(minimum, maximum)
        for minimum, maximum in sorted(
            {(item.minimum, item.maximum) for item in maximal}
        )
    )


def build_sequence_groups(
    proposals: tuple[SequenceRoleProposal, ...],
    roles: tuple[OrdinalBoundaryRole, ...],
    *,
    frame_width_lower_px: float = 1.0,
) -> tuple[tuple[SequenceHypothesisGroup, ...], SequenceGroupingWork]:
    """Assign sequence-role proposals through an indexed endpoint sweep."""

    if not proposals or not roles:
        return (), SequenceGroupingWork(0, 0, 0)
    if len({proposal.proposal_id for proposal in proposals}) != len(proposals):
        raise ValueError("sequence-role proposal identities must be unique")
    seeds = _endpoint_peak_intervals(proposals)
    by_role: dict[int, tuple[tuple[float, SequenceRoleProposal], ...]] = {}
    centers_by_role: dict[int, tuple[float, ...]] = {}
    maximum_half_width: dict[int, float] = {}
    for role in roles:
        indexed = tuple(
            sorted(
                (
                    (proposal.phase_interval_px.center, proposal)
                    for proposal in proposals
                    if proposal.role == role
                ),
                key=lambda item: (item[0], item[1].proposal_id),
            )
        )
        by_role[role.role_index] = indexed
        centers_by_role[role.role_index] = tuple(center for center, _ in indexed)
        maximum_half_width[role.role_index] = max(
            (proposal.phase_interval_px.width / 2.0 for _, proposal in indexed),
            default=0.0,
        )
    candidates_by_seed: list[list[SequenceRoleProposal]] = [[] for _ in seeds]
    lookup_count = 0
    for seed_index, seed in enumerate(seeds):
        for role in roles:
            lookup_count += 1
            indexed = by_role[role.role_index]
            centers = centers_by_role[role.role_index]
            allowance = maximum_half_width[role.role_index]
            start = bisect_left(centers, seed.minimum - allowance)
            stop = bisect_right(centers, seed.maximum + allowance)
            for _, proposal in indexed[start:stop]:
                if intersect(seed, proposal.phase_interval_px) is not None:
                    candidates_by_seed[seed_index].append(proposal)
    groups: list[SequenceHypothesisGroup] = []
    matched = 0
    for seed, assigned in zip(seeds, candidates_by_seed, strict=True):
        selected = [
            proposal
            for proposal in assigned
            if proposal.phase_interval_px.contains(seed.center)
        ]
        if not selected:
            continue
        phase = common(tuple(proposal.phase_interval_px for proposal in selected))
        if phase is None:
            continue
        selected.sort(key=lambda proposal: (proposal.role.role_index, proposal.proposal_id))
        matched += len(selected)
        exclusion = group_support_exclusion_authorized(
            role_coordinates_px=tuple(
                proposal.role_coordinate_px for proposal in selected
            ),
            role_identities=tuple(
                (proposal.role.lane_ordinal, proposal.role)
                for proposal in selected
            ),
            transition_id_sets=tuple(
                proposal.transition_ids for proposal in selected
            ),
            frame_width_lower_px=frame_width_lower_px,
        )
        groups.append(
            SequenceHypothesisGroup(
                group_id=_stable_id(
                    "sequence-phase-group",
                    *(proposal.proposal_id for proposal in selected),
                    phase.minimum,
                    phase.maximum,
                ),
                phase_interval_px=phase,
                role_proposals=tuple(selected),
                separator_band_proposals=(),
                ambiguous_proposal_ids=(),
                exclusion_authorized=exclusion,
            )
        )
    unique = {group.group_id: group for group in groups}
    ordered = tuple(unique[key] for key in sorted(unique))
    return ordered, SequenceGroupingWork(len(seeds), lookup_count, matched)


def build_separator_band_groups(
    proposals: tuple[SeparatorBandRoleProposal, ...],
    *,
    relation_count: int,
) -> tuple[tuple[SequenceHypothesisGroup, ...], SequenceGroupingWork]:
    """Build normal chains from repeated compatible separator bands."""

    if not proposals or relation_count <= 0:
        return (), SequenceGroupingWork(0, 0, 0)
    ordered = tuple(
        sorted(
            proposals,
            key=lambda item: (item.phase_interval_px.center, item.proposal_id),
        )
    )
    groups: list[SequenceHypothesisGroup] = []
    lookup_count = 0
    matched = 0

    def append_group(
        selected: tuple[SeparatorBandRoleProposal, ...],
        phase: FiniteInterval,
    ) -> None:
        nonlocal matched
        role_proposals = tuple(
            proposal
            for band in sorted(
                selected,
                key=lambda item: (item.relation_ordinal, item.proposal_id),
            )
            for proposal in (band.left_role_proposal, band.right_role_proposal)
        )
        matched += len(role_proposals)
        groups.append(
            SequenceHypothesisGroup(
                group_id=_stable_id(
                    "separator-band-phase-group",
                    *(item.proposal_id for item in selected),
                    phase.minimum.hex(),
                    phase.maximum.hex(),
                ),
                phase_interval_px=phase,
                role_proposals=role_proposals,
                separator_band_proposals=tuple(selected),
                ambiguous_proposal_ids=(),
                exclusion_authorized=True,
            )
        )

    if relation_count == 1:
        for proposal in ordered:
            append_group((proposal,), proposal.phase_interval_px)
        unique = {group.group_id: group for group in groups}
        return (
            tuple(unique[key] for key in sorted(unique)),
            SequenceGroupingWork(len(ordered), len(ordered), matched),
        )

    by_relation = {
        ordinal: tuple(
            item for item in ordered if item.relation_ordinal == ordinal
        )
        for ordinal in range(1, relation_count + 1)
    }

    def normalized_pair(
        first: SeparatorBandRoleProposal,
        second: SeparatorBandRoleProposal,
    ) -> tuple[tuple[SeparatorBandRoleProposal, ...], FiniteInterval] | None:
        if (
            first.relation_ordinal >= second.relation_ordinal
            or first.band_observation_id == second.band_observation_id
        ):
            return None
        normal_gap = intersect(first.gap_interval_px, second.gap_interval_px)
        if normal_gap is None:
            return None
        phase_constraints: list[FiniteInterval] = []
        adjusted: list[SeparatorBandRoleProposal] = []
        for band in (first, second):
            cumulative_gap = multiply(normal_gap, band.relation_ordinal - 1)
            phase = subtract(band.phase_interval_px, cumulative_gap)
            phase_constraints.append(phase)
            left = replace(
                band.left_role_proposal,
                phase_interval_px=subtract(
                    band.left_role_proposal.phase_interval_px,
                    cumulative_gap,
                ),
                role_coordinate_px=(
                    band.left_role_proposal.role_coordinate_px
                    + cumulative_gap.center
                ),
            )
            right = replace(
                band.right_role_proposal,
                phase_interval_px=subtract(
                    band.right_role_proposal.phase_interval_px,
                    cumulative_gap,
                ),
                role_coordinate_px=(
                    band.right_role_proposal.role_coordinate_px
                    + cumulative_gap.center
                ),
            )
            adjusted.append(
                replace(
                    band,
                    phase_interval_px=phase,
                    left_role_proposal=left,
                    right_role_proposal=right,
                )
            )
        common_phase = common(tuple(phase_constraints))
        return None if common_phase is None else (tuple(adjusted), common_phase)

    for left_ordinal in range(1, relation_count):
        for right_ordinal in range(left_ordinal + 1, relation_count + 1):
            left_values = by_relation[left_ordinal]
            right_values = by_relation[right_ordinal]
            lookup_count += len(left_values) * len(right_values)
            for left in left_values:
                for right in right_values:
                    normalized = normalized_pair(left, right)
                    if normalized is not None:
                        append_group(*normalized)
    unique = {group.group_id: group for group in groups}
    ordered_groups = tuple(unique[key] for key in sorted(unique))
    return (
        ordered_groups,
        SequenceGroupingWork(len(proposals), lookup_count, matched),
    )
