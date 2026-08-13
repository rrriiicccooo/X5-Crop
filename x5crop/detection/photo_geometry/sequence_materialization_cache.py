"""Run-local cache for physically identical sequence materializations."""

from __future__ import annotations

from dataclasses import replace
from typing import TypeAlias

from .chain_proposals import (
    FrameChainProposals,
    SequenceChainProposal,
)
from .chains import (
    SequencePlacement,
)
from .output_model import SharedStripDirection
from .source_geometry import SourceScanGeometry
from .physical_identity import physical_fact_id


SequenceMaterializationKey: TypeAlias = tuple[object, ...]
SequenceMaterializationValue: TypeAlias = SequencePlacement | None
SequenceMaterializationCache: TypeAlias = dict[
    SequenceMaterializationKey,
    SequenceMaterializationValue,
]


def sequence_materialization_key(
    proposal: FrameChainProposals,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
    *,
    bind_all_compatible_bands: bool,
) -> SequenceMaterializationKey:
    """Identify one sequence-axis numeric solve, excluding provenance IDs."""

    def role_key(item) -> tuple[object, ...]:
        return (
            item.run_id,
            item.role,
            item.phase_interval_px,
            item.transition_ids,
            item.role_coordinate_px,
            item.separator_band_observation_id,
        )

    return (
        proposal.frame_spec,
        proposal.discovery_kind,
        seed.base_phase_interval_px,
        tuple(role_key(item) for item in seed.role_proposals),
        tuple(role_key(item) for item in seed.local_advance_proposals),
        seed.local_advance_relations,
        seed.exclusion_authorized,
        direction.full_angle_interval_degrees,
        direction.canonical_angle_degrees,
        geometry.geometry_id,
        bind_all_compatible_bands,
    )


def rebind_cached_sequence(
    cached: SequencePlacement,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
) -> SequencePlacement:
    """Attach one cached numeric solution to the current complete-chain path."""

    return replace(
        cached,
        placement_id=physical_fact_id(
            "sequence-placement",
            geometry.frame_spec.frame_spec_id,
            seed.chain_proposal_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        chain_proposal_id=seed.chain_proposal_id,
        sequence_group_ids=seed.sequence_group_ids,
        source_scan_geometry_id=geometry.geometry_id,
    )
