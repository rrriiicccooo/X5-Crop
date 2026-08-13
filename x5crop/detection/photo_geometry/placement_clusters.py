"""Sampling-equivalent chain clustering within one lane."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import Box, EvidenceState, FiniteInterval, ObservationId
from ..evidence.content_occupancy_model import ContentOccupancyObservationSet
from .chain_record_model import CompleteChainRecord
from .chain_records import (
    direct_chain_evidence,
    interval_identity_fields,
    placement_boundary_intervals,
)
from .chains import CompleteFormatChain
from .content_topology import build_content_topology_index
from .content_veto import content_veto_assessment
from .content_veto_model import ContentVetoAssessment
from .interval_math import intersect
from .selection_identity import selection_fact_id
from .source_geometry import SourceScanGeometry

@dataclass(frozen=True)
class PlacementCluster:
    cluster_id: str
    chain_ids: tuple[str, ...]
    representative_placement_id: str
    sampling_boxes: tuple[Box, ...]
    boundary_intersections_px: tuple[FiniteInterval, ...]
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
    accounted_observation_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.cluster_id
            or not self.chain_ids
            or len(set(self.chain_ids)) != len(self.chain_ids)
            or not self.representative_placement_id
            or not self.sampling_boxes
            or not self.boundary_intersections_px
            or self.separator_band_count < 0
            or self.cross_axis_support_region_count < 0
            or self.separator_support_region_count < 0
            or not math.isfinite(
                self.lane_direction_disagreement_degrees
            )
            or self.lane_direction_disagreement_degrees < 0.0
            or len(set(self.direction_observation_ids))
            != len(self.direction_observation_ids)
            or len(set(self.accounted_observation_ids))
            != len(self.accounted_observation_ids)
        ):
            raise ValueError("placement cluster is invalid")



@dataclass(frozen=True)
class LanePlacementSelection:
    chains: tuple[CompleteChainRecord, ...]
    clusters: tuple[PlacementCluster, ...]
    content_veto_assessments: tuple[ContentVetoAssessment, ...]
    selected_cluster_id: str | None
    selected_placement_id: str | None
    state: EvidenceState

    def __post_init__(self) -> None:
        selected = self.selected_cluster_id is not None
        if (
            selected != (self.selected_placement_id is not None)
            or selected != (self.state == EvidenceState.SUPPORTED)
            or len({item.chain_id for item in self.chains}) != len(self.chains)
            or len({item.cluster_id for item in self.clusters}) != len(self.clusters)
            or self.selected_cluster_id
            not in ({None} | {item.cluster_id for item in self.clusters})
        ):
            raise ValueError("lane placement selection is invalid")

def _weak_representative_key(
    placement: CompleteFormatChain,
) -> tuple[object, ...]:
    (
        direct_count,
        structural_count,
        _direct_ids,
        _structural_ids,
        _material_quality,
        support_region_count,
        cross_pair,
    ) = direct_chain_evidence(placement)
    residual = sum(
        item.fit_residual_px for item in placement.sequence.observations
    ) + sum(
        item.observation.fit_residual_px
        for item in placement.cross.evidence
    )
    uncertainty = sum(
        interval.width for interval in placement_boundary_intervals(placement)
    )
    return (
        -direct_count,
        -int(cross_pair),
        -structural_count,
        -support_region_count,
        residual,
        uncertainty,
        placement.placement_id,
    )


def cluster_sampling_equivalent_chains(
    chains: tuple[CompleteChainRecord, ...],
    placements_by_id: dict[str, CompleteFormatChain],
) -> tuple[PlacementCluster, ...]:
    groups: list[list[CompleteChainRecord]] = []
    intersections: list[tuple[FiniteInterval, ...]] = []
    direction_intersections: list[FiniteInterval] = []
    shared_geometries: list[SourceScanGeometry] = []
    ordered_chains = tuple(
        sorted(
            chains,
            key=lambda item: (
                -item.direct_observation_count,
                -item.structural_pair_count,
                item.lane_id,
                interval_identity_fields(item.boundary_intervals_px),
                tuple(map(str, item.direct_observation_ids)),
                item.chain_id,
            ),
        )
    )
    for chain in ordered_chains:
        for index, group in enumerate(groups):
            placement = placements_by_id[chain.placement_id]
            if (
                group[0].sampling_boxes != chain.sampling_boxes
                or group[0].sampling_authority_boxes
                != chain.sampling_authority_boxes
                or group[0].authority_profile_ids != chain.authority_profile_ids
            ):
                continue
            direction_common = intersect(
                direction_intersections[index],
                placement.lane_geometry.direction.full_angle_interval_degrees,
            )
            if direction_common is None:
                continue
            try:
                geometry_common = shared_geometries[index].intersect_source_state(
                    placement.source_scan_geometry
                )
            except ValueError:
                continue
            merged = tuple(
                intersect(left, right)
                for left, right in zip(
                    intersections[index],
                    chain.boundary_intervals_px,
                    strict=True,
                )
            )
            if any(value is None for value in merged):
                continue
            group.append(chain)
            intersections[index] = tuple(
                value for value in merged if value is not None
            )
            direction_intersections[index] = direction_common
            shared_geometries[index] = geometry_common
            break
        else:
            groups.append([chain])
            intersections.append(chain.boundary_intervals_px)
            placement = placements_by_id[chain.placement_id]
            direction_intersections.append(
                placement.lane_geometry.direction.full_angle_interval_degrees
            )
            shared_geometries.append(placement.source_scan_geometry)
    clusters: list[PlacementCluster] = []
    for group, common in zip(groups, intersections, strict=True):
        ordered = tuple(sorted(group, key=lambda item: item.chain_id))
        representative = min(
            ordered,
            key=lambda item: _weak_representative_key(
                placements_by_id[item.placement_id]
            ),
        )
        structural_ids = tuple(
            sorted(
                {
                    identity
                    for item in ordered
                    for identity in item.structural_observation_ids
                },
                key=str,
            )
        )
        direct_ids = tuple(
            sorted(
                {
                    identity
                    for item in ordered
                    for identity in item.direct_observation_ids
                },
                key=str,
            )
        )
        chain_ids = tuple(item.chain_id for item in ordered)
        cluster_id = selection_fact_id(
            "placement-cluster",
            (
                *chain_ids,
                *interval_identity_fields(common),
                *(
                    str(value)
                    for box in representative.sampling_boxes
                    for value in (box.left, box.top, box.right, box.bottom)
                ),
            ),
        )
        clusters.append(
            PlacementCluster(
                cluster_id=cluster_id,
                chain_ids=chain_ids,
                representative_placement_id=representative.placement_id,
                sampling_boxes=representative.sampling_boxes,
                boundary_intersections_px=common,
                direct_observation_count=max(
                    item.direct_observation_count for item in ordered
                ),
                separator_band_count=max(
                    item.separator_band_count for item in ordered
                ),
                structural_pair_count=max(
                    item.structural_pair_count for item in ordered
                ),
                cross_axis_pair_supported=any(
                    item.cross_axis_pair_supported for item in ordered
                ),
                cross_axis_support_region_count=max(
                    item.cross_axis_support_region_count for item in ordered
                ),
                cross_axis_observation_ids=tuple(
                    sorted(
                        {
                            identity
                            for item in ordered
                            for identity in item.cross_axis_observation_ids
                        },
                        key=str,
                    )
                ),
                direct_observation_ids=direct_ids,
                structural_observation_ids=structural_ids,
                normal_gap_supported=any(
                    item.normal_gap_supported for item in ordered
                ),
                separator_support_region_count=max(
                    item.separator_support_region_count for item in ordered
                ),
                lane_direction_disagreement_degrees=min(
                    item.lane_direction_disagreement_degrees
                    for item in ordered
                ),
                direction_observation_ids=tuple(
                    sorted(
                        {
                            identity
                            for item in ordered
                            for identity in item.direction_observation_ids
                        },
                        key=str,
                    )
                ),
                separator_material_quality=max(
                    item.separator_material_quality for item in ordered
                ),
                accounted_observation_ids=tuple(
                    sorted(
                        {
                            identity
                            for item in ordered
                            for identity in item.accounted_observation_ids
                        },
                        key=str,
                    )
                ),
            )
        )
    return tuple(sorted(clusters, key=lambda item: item.cluster_id))



def prepare_placement_clusters(
    chains: tuple[CompleteChainRecord, ...],
    placements_by_id: dict[str, CompleteFormatChain],
    observations: ContentOccupancyObservationSet,
    *,
    layout: str,
    content_assessments_by_placement: dict[
        str,
        ContentVetoAssessment,
    ] | None = None,
) -> LanePlacementSelection:
    clusters = cluster_sampling_equivalent_chains(chains, placements_by_id)
    content_index = (
        None
        if content_assessments_by_placement is not None
        else build_content_topology_index(observations, layout=layout)
    )

    def assessment_for(cluster: PlacementCluster) -> ContentVetoAssessment:
        if content_assessments_by_placement is not None:
            return content_assessments_by_placement[
                cluster.representative_placement_id
            ]
        if content_index is None:
            raise AssertionError("content topology index was not constructed")
        return content_veto_assessment(
            placements_by_id[cluster.representative_placement_id],
            content_index,
        )

    assessments = tuple(
        assessment_for(cluster)
        for cluster in clusters
    )
    return LanePlacementSelection(
        chains=chains,
        clusters=clusters,
        content_veto_assessments=assessments,
        selected_cluster_id=None,
        selected_placement_id=None,
        state=EvidenceState.UNAVAILABLE,
    )
