"""Build sequence-chain seeds from already grouped direct roles."""

from __future__ import annotations

from ...domain import FiniteInterval
from .chain_proposals import FrameChainProposals, SequenceChainProposal
from .physical_identity import physical_fact_id
from .sequence_models import LocalAdvanceKind, LocalAdvanceRelation


def build_sequence_chain_proposals(
    proposal: FrameChainProposals,
) -> tuple[SequenceChainProposal, ...]:
    slot_count = len(proposal.roles) // 2
    seeds: list[SequenceChainProposal] = []
    for group in proposal.sequence_groups:
        local_proposals = tuple(
            sorted(
                group.role_proposals,
                key=lambda item: (item.role.role_index, item.proposal_id),
            )
        )
        if not local_proposals:
            continue
        relations = tuple(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=LocalAdvanceKind.NOMINAL,
                delta_interval_px=FiniteInterval.exact(0.0),
                canonical_delta_px=0.0,
                observation_ids=(),
            )
            for ordinal in range(1, slot_count)
        )
        seeds.append(
            SequenceChainProposal(
                chain_proposal_id=physical_fact_id(
                    "sequence-chain-proposal",
                    proposal.discovery_kind.value,
                    group.group_id,
                ),
                discovery_kind=proposal.discovery_kind,
                sequence_group_ids=(group.group_id,),
                base_phase_interval_px=group.phase_interval_px,
                # Every role in the established group constrains one common
                # phase.  Keeping all is interval intersection, not voting.
                role_proposals=local_proposals,
                local_advance_proposals=local_proposals,
                local_advance_relations=relations,
                exclusion_authorized=group.exclusion_authorized,
            )
        )
    unique = {item.chain_proposal_id: item for item in seeds}
    return tuple(unique[key] for key in sorted(unique))
