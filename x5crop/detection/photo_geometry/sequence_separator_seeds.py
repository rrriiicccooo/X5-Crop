"""Build complete direct-separator sequence groups."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import replace

from ...domain import FiniteInterval
from .interval_math import add, common, intersect, multiply, subtract
from .observation_types import (
    SeparatorBandRoleProposal,
    SequenceHypothesisGroup,
)
from .physical_identity import physical_fact_id


def direct_separator_groups(
    bands: tuple[SeparatorBandRoleProposal, ...],
    *,
    relation_count: int,
    width_interval_px: FiniteInterval,
    canonical_width_px: float,
    fit_position_by_run: dict[str, FiniteInterval],
) -> tuple[SequenceHypothesisGroup, ...]:
    """Find complete fixed-format paths through physical separator bands.

    Bands are nodes ordered in source coordinates.  A directed edge exists
    only when the next band's left edge is one shared frame width after the
    current band's right edge.  Ordinal roles are attached after a complete
    physical path exists; they do not participate in discovering the path.
    """

    if not bands or relation_count <= 0:
        return ()
    proposals_by_observation: dict[
        str,
        dict[int, SeparatorBandRoleProposal],
    ] = {}
    for band in bands:
        proposals_by_observation.setdefault(
            str(band.band_observation_id),
            {},
        )[band.relation_ordinal] = band
    physical_nodes = tuple(
        sorted(
            proposals_by_observation,
            key=lambda observation_id: (
                fit_position_by_run[
                    next(iter(proposals_by_observation[observation_id].values()))
                    .left_role_proposal.run_id
                ].minimum,
                fit_position_by_run[
                    next(iter(proposals_by_observation[observation_id].values()))
                    .left_role_proposal.run_id
                ].maximum,
                observation_id,
            ),
        )
    )
    representative = {
        observation_id: next(
            iter(proposals_by_observation[observation_id].values())
        )
        for observation_id in physical_nodes
    }
    left_positions = {
        observation_id: fit_position_by_run[
            representative[observation_id].left_role_proposal.run_id
        ]
        for observation_id in physical_nodes
    }
    ordered_left_minima = tuple(
        left_positions[observation_id].minimum
        for observation_id in physical_nodes
    )
    successors: dict[str, tuple[str, ...]] = {}
    for node_index, observation_id in enumerate(physical_nodes):
        current = representative[observation_id]
        current_right = fit_position_by_run[
            current.right_role_proposal.run_id
        ]
        stop = bisect_right(
            ordered_left_minima,
            current_right.maximum + width_interval_px.maximum,
        )
        successors[observation_id] = tuple(
            candidate_id
            for candidate_id in physical_nodes[node_index + 1 : stop]
            for candidate in (representative[candidate_id],)
            if intersect(
                subtract(
                    fit_position_by_run[
                        candidate.left_role_proposal.run_id
                    ],
                    current_right,
                ),
                width_interval_px,
            )
            is not None
        )

    physical_paths: list[tuple[str, ...]] = []

    def extend(path: tuple[str, ...]) -> None:
        if len(path) == relation_count:
            physical_paths.append(path)
            return
        for successor in successors[path[-1]]:
            extend((*path, successor))

    for node in physical_nodes:
        extend((node,))
    paths = tuple(
        tuple(
            proposals_by_observation[observation_id][ordinal]
            for ordinal, observation_id in enumerate(path, start=1)
        )
        for path in physical_paths
        if all(
            ordinal in proposals_by_observation[observation_id]
            for ordinal, observation_id in enumerate(path, start=1)
        )
    )

    groups: list[SequenceHypothesisGroup] = []
    for path in paths:
        adjusted_bands: list[SeparatorBandRoleProposal] = []
        phase_constraints: list[FiniteInterval] = []
        preceding_gaps = FiniteInterval.exact(0.0)
        canonical_preceding_gaps = 0.0
        for band in path:
            left_relative = add(
                multiply(width_interval_px, band.relation_ordinal),
                preceding_gaps,
            )
            right_relative = add(left_relative, band.gap_interval_px)
            left_phase = subtract(
                fit_position_by_run[band.left_role_proposal.run_id],
                left_relative,
            )
            right_phase = subtract(
                fit_position_by_run[band.right_role_proposal.run_id],
                right_relative,
            )
            band_phase = intersect(left_phase, right_phase)
            if band_phase is None:
                break
            phase_constraints.append(band_phase)
            canonical_left = (
                band.relation_ordinal * canonical_width_px
                + canonical_preceding_gaps
            )
            left_role = replace(
                band.left_role_proposal,
                phase_interval_px=left_phase,
                role_coordinate_px=canonical_left,
            )
            right_role = replace(
                band.right_role_proposal,
                phase_interval_px=right_phase,
                role_coordinate_px=(
                    canonical_left + band.gap_interval_px.center
                ),
            )
            adjusted_bands.append(
                replace(
                    band,
                    phase_interval_px=band_phase,
                    left_role_proposal=left_role,
                    right_role_proposal=right_role,
                )
            )
            preceding_gaps = add(preceding_gaps, band.gap_interval_px)
            canonical_preceding_gaps += band.gap_interval_px.center
        if len(adjusted_bands) != relation_count:
            continue
        phase = common(tuple(phase_constraints))
        if phase is None:
            continue
        role_proposals = tuple(
            role
            for band in adjusted_bands
            for role in (
                band.left_role_proposal,
                band.right_role_proposal,
            )
        )
        groups.append(
            SequenceHypothesisGroup(
                group_id=physical_fact_id(
                    "direct-separator-chain-group",
                    *(band.proposal_id for band in adjusted_bands),
                    phase.minimum,
                    phase.maximum,
                ),
                phase_interval_px=phase,
                role_proposals=role_proposals,
                separator_band_proposals=tuple(adjusted_bands),
                ambiguous_proposal_ids=(),
                exclusion_authorized=True,
            )
        )
    unique = {group.group_id: group for group in groups}
    return tuple(unique[key] for key in sorted(unique))
