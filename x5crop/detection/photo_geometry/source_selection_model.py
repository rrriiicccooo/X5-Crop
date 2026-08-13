"""Typed source-level placement combination and selection facts."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import EvidenceState, ObservationId
from .axis_authority import (
    CrossAuthorityVector,
    SequenceAuthorityVector,
    SharedAuthorityVector,
)
from .source_geometry import SourceScanGeometry


@dataclass(frozen=True)
class SourcePlacementCombination:
    combination_id: str
    lane_cluster_ids: tuple[str, ...]
    lane_placement_ids: tuple[str, ...]
    shared_scan_geometry: SourceScanGeometry
    direct_observation_ids: tuple[ObservationId, ...]
    direct_observation_count: int
    separator_band_count: int
    structural_observation_ids: tuple[ObservationId, ...]
    structural_strength: int
    cross_axis_pair_count: int
    cross_axis_support_region_count: int
    cross_axis_observation_ids: tuple[ObservationId, ...]
    separator_support_region_count: int
    lane_direction_disagreement_degrees: float
    direction_observation_ids: tuple[ObservationId, ...]
    separator_material_quality: float
    sequence_authority: SequenceAuthorityVector
    cross_authority: CrossAuthorityVector
    shared_authority: SharedAuthorityVector
    accounted_observation_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.combination_id
            or not self.lane_cluster_ids
            or len(self.lane_cluster_ids) != len(self.lane_placement_ids)
            or len(set(self.direct_observation_ids))
            != len(self.direct_observation_ids)
            or min(
                self.direct_observation_count,
                self.separator_band_count,
                self.structural_strength,
                self.cross_axis_support_region_count,
                self.separator_support_region_count,
            ) < 0
            or len(set(self.structural_observation_ids))
            != len(self.structural_observation_ids)
            or not 0 <= self.cross_axis_pair_count <= len(self.lane_cluster_ids)
            or len(set(self.cross_axis_observation_ids))
            != len(self.cross_axis_observation_ids)
            or not math.isfinite(self.lane_direction_disagreement_degrees)
            or self.lane_direction_disagreement_degrees < 0.0
            or len(set(self.direction_observation_ids))
            != len(self.direction_observation_ids)
            or not math.isfinite(self.separator_material_quality)
            or self.separator_material_quality < 0.0
            or len(set(self.accounted_observation_ids))
            != len(self.accounted_observation_ids)
        ):
            raise ValueError("source placement combination is invalid")


@dataclass(frozen=True)
class SourcePlacementSelection:
    combinations: tuple[SourcePlacementCombination, ...]
    selected_combination_id: str | None
    shared_scan_geometry: SourceScanGeometry | None
    state: EvidenceState

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        if (
            supported != (self.selected_combination_id is not None)
            or supported != (self.shared_scan_geometry is not None)
            or self.selected_combination_id
            not in ({None} | {item.combination_id for item in self.combinations})
        ):
            raise ValueError("source placement selection is invalid")
