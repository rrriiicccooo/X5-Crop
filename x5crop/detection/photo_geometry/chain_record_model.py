"""Typed audit records emitted for one complete physical chain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import Box, FiniteInterval, ObservationId
from .chain_observation_accounting import ChainObservationFact


class ChainEvidenceTier(str, Enum):
    DIRECT_PHYSICAL_OBSERVATION = "direct_physical_observation"
    COMPLETE_PHYSICAL_STRUCTURE = "complete_physical_structure"
    MATERIAL_QUALITY = "material_quality"
    WEAK_PRIOR = "weak_prior"


@dataclass(frozen=True)
class ChainLedgerEntry:
    entry_id: str
    chain_id: str
    ordinal: int
    evidence_tier: ChainEvidenceTier
    observation_ids: tuple[ObservationId, ...]
    physical_interval_px: FiniteInterval | None

    def __post_init__(self) -> None:
        if (
            not self.entry_id
            or not self.chain_id
            or self.ordinal <= 0
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise ValueError("chain ledger entry is invalid")


@dataclass(frozen=True)
class CompleteChainRecord:
    chain_id: str
    placement_id: str
    lane_id: str
    sampling_boxes: tuple[Box, ...]
    sampling_authority_boxes: tuple[Box, ...]
    authority_profile_ids: tuple[str, ...]
    boundary_intervals_px: tuple[FiniteInterval, ...]
    direction_id: str
    source_scan_geometry_id: str
    direct_observation_count: int
    separator_band_count: int
    structural_pair_count: int
    cross_axis_pair_supported: bool
    cross_axis_support_region_count: int
    cross_axis_observation_ids: tuple[ObservationId, ...]
    direct_observation_ids: tuple[ObservationId, ...]
    structural_observation_ids: tuple[ObservationId, ...]
    normal_gap_supported: bool
    separator_support_region_count: int
    lane_direction_disagreement_degrees: float
    direction_observation_ids: tuple[ObservationId, ...]
    separator_material_quality: float
    local_advance_authorized: bool
    accounted_observation_ids: tuple[ObservationId, ...] = ()
    ledger: tuple[ChainLedgerEntry, ...] = ()
    observation_facts: tuple[ChainObservationFact, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or not self.placement_id
            or not self.lane_id
            or not self.sampling_boxes
            or any(not box.valid() for box in self.sampling_boxes)
            or len(self.sampling_authority_boxes) != len(self.sampling_boxes)
            or any(not box.valid() for box in self.sampling_authority_boxes)
            or len(self.authority_profile_ids) != len(self.sampling_boxes)
            or not all(self.authority_profile_ids)
            or not self.boundary_intervals_px
            or not self.direction_id
            or not self.source_scan_geometry_id
            or self.direct_observation_count < 0
            or self.separator_band_count < 0
            or self.structural_pair_count < 0
            or self.cross_axis_support_region_count < 0
            or len(set(self.direct_observation_ids))
            != len(self.direct_observation_ids)
            or len(set(self.structural_observation_ids))
            != len(self.structural_observation_ids)
            or self.separator_support_region_count < 0
            or not math.isfinite(self.lane_direction_disagreement_degrees)
            or self.lane_direction_disagreement_degrees < 0.0
            or len(set(self.direction_observation_ids))
            != len(self.direction_observation_ids)
            or not math.isfinite(self.separator_material_quality)
            or self.separator_material_quality < 0.0
            or not self.local_advance_authorized
            or len(set(self.accounted_observation_ids))
            != len(self.accounted_observation_ids)
            or any(
                item.chain_id != self.chain_id or item.ordinal != ordinal
                for ordinal, item in enumerate(self.ledger, 1)
            )
            or len({item.observation_id for item in self.observation_facts})
            != len(self.observation_facts)
        ):
            raise ValueError("complete chain record is invalid")
