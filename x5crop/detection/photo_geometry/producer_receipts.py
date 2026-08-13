"""Bounded-producer work and pruning receipts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class ProducerPruneReason(str, Enum):
    SEPARATOR_CONTENT_CONTRADICTION = "separator_content_contradiction"
    STRICTLY_DOMINATED_PHYSICAL_PLACEMENT = (
        "strictly_dominated_physical_placement"
    )
    SAMPLING_CONTAINMENT_INVALID = "sampling_containment_invalid"


@dataclass(frozen=True)
class ChainProducerWorkReceipt:
    measurement_query_count: int
    pixel_query_count: int
    basic_profile_coordinate_count: int
    basic_profile_run_count: int
    role_proposal_count: int
    phase_hypothesis_count: int
    sequence_group_count: int
    ordinal_role_lookup_count: int
    ordinal_role_match_count: int
    local_relation_evaluation_count: int
    materialized_frame_geometry_count: int
    shared_measurement_reuse_count: int
    domain_pixels: int
    peak_temporary_bytes: int

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.__dict__.values()):
            raise ValueError("chain-producer work receipt cannot be negative")

    def validate_bounds(
        self,
        *,
        ordered_role_count: int,
        slot_count: int,
    ) -> None:
        if ordered_role_count <= 0 or slot_count <= 0:
            raise ValueError(
                "chain-producer work bound requires positive shape"
            )
        if (
            self.ordinal_role_lookup_count
            > self.phase_hypothesis_count * self.role_proposal_count
            or self.ordinal_role_match_count
            > self.phase_hypothesis_count * self.role_proposal_count
            or self.local_relation_evaluation_count
            > self.sequence_group_count * max(0, slot_count - 1)
        ):
            raise ValueError(
                "chain-producer work exceeded its structural bound"
            )



@dataclass(frozen=True)
class CorridorEdgeFamilyCount:
    corridor_id: str
    proposed_count: int
    materialized_count: int

    def __post_init__(self) -> None:
        if (
            not self.corridor_id
            or self.proposed_count < self.materialized_count
            or self.materialized_count < 0
        ):
            raise ValueError("corridor edge-family count is invalid")


@dataclass(frozen=True)
class ProducerPruneSummary:
    reason: ProducerPruneReason
    count: int

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("producer prune summary requires a positive count")



@dataclass(frozen=True)
class ProducerBoundsReceipt:
    lane_id: str
    corridor_edge_families: tuple[CorridorEdgeFamilyCount, ...]
    proposed_complete_chain_count: int
    materialized_complete_chain_count: int
    chain_ledger_entry_count: int
    prune_summaries: tuple[ProducerPruneSummary, ...]
    bound_exceeded: bool

    def __post_init__(self) -> None:
        incomplete_corridor = any(
            item.proposed_count > item.materialized_count
            for item in self.corridor_edge_families
        )
        if (
            not self.lane_id
            or self.proposed_complete_chain_count
            < self.materialized_complete_chain_count
            or self.materialized_complete_chain_count < 0
            or self.chain_ledger_entry_count < 0
            or len({item.reason for item in self.prune_summaries})
            != len(self.prune_summaries)
            or self.bound_exceeded != incomplete_corridor
        ):
            raise ValueError("producer bounds receipt is invalid")
