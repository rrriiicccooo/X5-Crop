"""Enumerate every bounded complete-chain placement for one source."""

from __future__ import annotations

from .boundary_projection import BoundRunProjection
from .chain_materialization import materialize_frame_spec_seed
from .chains import (
    BoundRoleEvidence,
    CompleteFormatChain,
    SourcePlacementMaterialization,
)
from .chain_proposals import LanePhysicalProposals
from .direction_proposals import physical_bound_direction_classes
from .model import BoundaryRole
from .sequence_materialization_cache import SequenceMaterializationCache
from .sequence_seed import frame_spec_materialization_seeds
from .sequence_models import SequenceDiscoveryKind


def materialize_lane_placements(
    proposal: LanePhysicalProposals,
    *,
    discovery_kind: SequenceDiscoveryKind,
) -> tuple[tuple[CompleteFormatChain, ...], int]:
    projection_cache: dict[tuple[object, ...], BoundRunProjection] = {}
    evidence_cache: dict[tuple[str, str, int], BoundRoleEvidence] = {}
    sequence_cache: SequenceMaterializationCache = {}
    proposed_unsorted = tuple(
        (frame_spec, seed, direction, cross_proposal)
        for frame_spec in sorted(
            (
                item
                for item in proposal.frame_proposals
                if item.discovery_kind == discovery_kind
            ),
            key=lambda item: item.frame_spec.frame_spec_id,
        )
        for cross_proposal in proposal.cross_proposals
        for direction in physical_bound_direction_classes((cross_proposal,))
        for seed in frame_spec_materialization_seeds(
            proposal,
            frame_spec,
            direction,
            projection_cache,
        )
    )
    proposed = tuple(
        sorted(
            proposed_unsorted,
            key=lambda item: (
                -sum(
                    {
                        proposal.role.role
                        for proposal in item[1].role_proposals
                        if proposal.role.lane_ordinal == ordinal
                    }
                    == {BoundaryRole.START, BoundaryRole.END}
                    for ordinal in {
                        proposal.role.lane_ordinal
                        for proposal in item[1].role_proposals
                    }
                ),
                -len(
                    {
                        proposal.role.role_index
                        for proposal in item[1].role_proposals
                    }
                ),
                min(
                    proposal.role.lane_ordinal
                    for proposal in item[1].role_proposals
                ),
                tuple(
                    value
                    for proposal in item[1].role_proposals
                    for value in (
                        proposal.phase_interval_px.minimum.hex(),
                        proposal.phase_interval_px.maximum.hex(),
                    )
                ),
                tuple(
                    sorted(
                        str(identity)
                        for proposal in item[1].role_proposals
                        for identity in proposal.transition_ids
                    )
                ),
                item[0].frame_spec.frame_spec_id,
                item[1].chain_proposal_id,
                item[2].direction_id,
                item[3].cross_proposal_id,
            ),
        )
    )
    seed_materializations = tuple(
        placements
        for frame_spec, seed, direction, cross_proposal in proposed
        if (
            placements := materialize_frame_spec_seed(
                proposal,
                frame_spec,
                seed,
                direction,
                projection_cache=projection_cache,
                evidence_cache=evidence_cache,
                sequence_cache=sequence_cache,
                cross_candidates=(cross_proposal,),
            )
        )
    )
    values = tuple(
        placement
        for placements in seed_materializations
        for placement in placements
    )
    unique = {item.placement_id: item for item in values}
    ordered = tuple(unique[key] for key in sorted(unique))
    return ordered, max(len(proposed), len(ordered))


def materialize_source_placements(
    lane_proposals: tuple[LanePhysicalProposals, ...],
) -> SourcePlacementMaterialization:
    """Materialize every finite lane direction and sequence proposal."""

    if not lane_proposals:
        return SourcePlacementMaterialization((), (), ())
    if len(lane_proposals) > 2:
        raise ValueError("physical-chain source supports at most two lanes")
    placements_by_lane: list[tuple[CompleteFormatChain, ...]] = []
    proposed_counts: list[int] = []
    materialized_lane_proposals: list[LanePhysicalProposals] = []
    for lane in lane_proposals:
        placements: dict[str, CompleteFormatChain] = {}
        proposed_count = 0
        kinds = tuple(
            dict.fromkeys(item.discovery_kind for item in lane.frame_proposals)
        )
        for discovery_kind in kinds:
            materialized, layer_count = materialize_lane_placements(
                lane,
                discovery_kind=discovery_kind,
            )
            proposed_count += layer_count
            placements.update(
                {item.placement_id: item for item in materialized}
            )
        ordered = tuple(placements[key] for key in sorted(placements))
        materialized_lane_proposals.append(lane)
        placements_by_lane.append(ordered)
        proposed_counts.append(max(proposed_count, len(ordered)))
    return SourcePlacementMaterialization(
        placements_by_lane=tuple(placements_by_lane),
        proposed_complete_chain_counts_by_lane=tuple(proposed_counts),
        lane_proposals=tuple(materialized_lane_proposals),
    )
