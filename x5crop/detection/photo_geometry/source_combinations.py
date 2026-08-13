"""Build finite source-level combinations from eligible lane clusters."""

from __future__ import annotations

from .axis_authority import (
    CrossAuthorityVector,
    SequenceAuthorityVector,
    SharedAuthorityVector,
)
from .chain_authority import placement_axis_authority
from .chains import CompleteFormatChain
from .placement_clusters import LanePlacementSelection, PlacementCluster
from .selection_identity import selection_fact_id
from .source_geometry import SourceScanGeometry
from .source_selection_model import SourcePlacementCombination


def eligible_clusters(
    selection: LanePlacementSelection,
) -> tuple[PlacementCluster, ...]:
    assessment_by_placement = {
        item.placement_id: item
        for item in selection.content_veto_assessments
    }
    return tuple(
        cluster
        for cluster in selection.clusters
        if not assessment_by_placement[cluster.representative_placement_id].vetoed
    )


def source_combination(
    clusters: tuple[PlacementCluster, ...],
    placements_by_lane: tuple[dict[str, CompleteFormatChain], ...],
    *,
    shared_scan_geometry: SourceScanGeometry | None = None,
) -> SourcePlacementCombination | None:
    placements = tuple(
        placements_by_lane[index][cluster.representative_placement_id]
        for index, cluster in enumerate(clusters)
    )
    axis_authorities = tuple(
        placement_axis_authority(
            placement,
            content_veto_passed=True,
        )
        for placement in placements
    )
    shared = shared_scan_geometry or placements[0].source_scan_geometry
    if shared_scan_geometry is None:
        try:
            for placement in placements[1:]:
                shared = shared.intersect_source_state(
                    placement.source_scan_geometry
                )
        except ValueError:
            return None
    direct_ids = tuple(
        sorted(
            {
                identity
                for cluster in clusters
                for identity in cluster.direct_observation_ids
            },
            key=str,
        )
    )
    structural_ids = tuple(
        sorted(
            {
                identity
                for cluster in clusters
                for identity in cluster.structural_observation_ids
            },
            key=str,
        )
    )
    cluster_ids = tuple(cluster.cluster_id for cluster in clusters)
    placement_ids = tuple(
        cluster.representative_placement_id for cluster in clusters
    )
    return SourcePlacementCombination(
        combination_id=selection_fact_id(
            "source-placement-combination",
            (*cluster_ids, shared.geometry_id),
        ),
        lane_cluster_ids=cluster_ids,
        lane_placement_ids=placement_ids,
        shared_scan_geometry=shared,
        direct_observation_ids=direct_ids,
        direct_observation_count=sum(
            cluster.direct_observation_count for cluster in clusters
        ),
        separator_band_count=sum(
            cluster.separator_band_count for cluster in clusters
        ),
        structural_observation_ids=structural_ids,
        structural_strength=sum(
            cluster.structural_pair_count + int(cluster.normal_gap_supported)
            for cluster in clusters
        ),
        cross_axis_pair_count=sum(
            cluster.cross_axis_pair_supported for cluster in clusters
        ),
        cross_axis_support_region_count=sum(
            cluster.cross_axis_support_region_count for cluster in clusters
        ),
        cross_axis_observation_ids=tuple(
            sorted(
                {
                    identity
                    for cluster in clusters
                    for identity in cluster.cross_axis_observation_ids
                },
                key=str,
            )
        ),
        separator_support_region_count=sum(
            cluster.separator_support_region_count for cluster in clusters
        ),
        lane_direction_disagreement_degrees=sum(
            cluster.lane_direction_disagreement_degrees for cluster in clusters
        ),
        direction_observation_ids=tuple(
            sorted(
                {
                    identity
                    for cluster in clusters
                    for identity in cluster.direction_observation_ids
                },
                key=str,
            )
        ),
        separator_material_quality=sum(
            cluster.separator_material_quality for cluster in clusters
        ),
        sequence_authority=SequenceAuthorityVector(
            complete_direct_chain_count=sum(
                item.sequence.complete_direct_chain_count
                for item in axis_authorities
            ),
            direct_separator_band_count=sum(
                item.sequence.direct_separator_band_count
                for item in axis_authorities
            ),
            independent_separator_support_region_count=sum(
                item.sequence.independent_separator_support_region_count
                for item in axis_authorities
            ),
            direct_outer_boundary_count=sum(
                item.sequence.direct_outer_boundary_count
                for item in axis_authorities
            ),
            normal_completion_authorized_count=sum(
                item.sequence.normal_completion_authorized_count
                for item in axis_authorities
            ),
            local_advance_authorized_count=sum(
                item.sequence.local_advance_authorized_count
                for item in axis_authorities
            ),
            filled_holder_centering_authorized_count=sum(
                item.sequence.filled_holder_centering_authorized_count
                for item in axis_authorities
            ),
            observation_ids=tuple(
                sorted(
                    {
                        identity
                        for item in axis_authorities
                        for identity in item.sequence.observation_ids
                    },
                    key=str,
                )
            ),
        ),
        cross_authority=CrossAuthorityVector(
            fixed_height_placement_authorized_count=sum(
                item.cross.fixed_height_placement_authorized_count
                for item in axis_authorities
            ),
            complete_top_bottom_pair_count=sum(
                item.cross.complete_top_bottom_pair_count
                for item in axis_authorities
            ),
            direct_height_span_validated_count=sum(
                item.cross.direct_height_span_validated_count
                for item in axis_authorities
            ),
            common_top_bottom_direction_count=sum(
                item.cross.common_top_bottom_direction_count
                for item in axis_authorities
            ),
            source_spanning_boundary_family_count=sum(
                item.cross.source_spanning_boundary_family_count
                for item in axis_authorities
            ),
            direct_boundary_family_count=sum(
                item.cross.direct_boundary_family_count
                for item in axis_authorities
            ),
            independent_support_region_count=sum(
                item.cross.independent_support_region_count
                for item in axis_authorities
            ),
            observation_ids=tuple(
                sorted(
                    {
                        identity
                        for item in axis_authorities
                        for identity in item.cross.observation_ids
                    },
                    key=str,
                )
            ),
        ),
        shared_authority=SharedAuthorityVector(
            source_scale_compatible=True,
            direction_bound_lane_count=sum(
                item.shared.direction_bound_lane_count
                for item in axis_authorities
            ),
            source_lane_authority_bound_count=sum(
                item.shared.source_lane_authority_bound_count
                for item in axis_authorities
            ),
            content_veto_passed_lane_count=sum(
                item.shared.content_veto_passed_lane_count
                for item in axis_authorities
            ),
        ),
        accounted_observation_ids=tuple(
            sorted(
                {
                    identity
                    for cluster in clusters
                    for identity in cluster.accounted_observation_ids
                },
                key=str,
            )
        ),
    )


def compatible_source_geometry_clusters(
    clusters: tuple[PlacementCluster, ...],
    placements: dict[str, CompleteFormatChain],
    placement: CompleteFormatChain,
) -> tuple[tuple[PlacementCluster, SourceScanGeometry], ...]:
    """Return only candidates already bound to identical source W/H."""

    geometry = placement.source_scan_geometry
    return tuple(
        (cluster, geometry)
        for cluster in sorted(clusters, key=lambda item: item.cluster_id)
        if placements[
            cluster.representative_placement_id
        ].source_scan_geometry == geometry
    )
