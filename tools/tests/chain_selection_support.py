from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import inspect
import unittest

from x5crop.detection.evidence.content_occupancy_model import (
    ContentOccupancyObservation,
    ContentOccupancyObservationSet,
)
from x5crop.detection.photo_geometry.line_observations import SourceCoordinateLine
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    DirectionAuthority,
    PositionSource,
)
from x5crop.detection.photo_geometry.output_model import FrameBoundaryGeometry
from x5crop.detection.photo_geometry.output import (
    direct_use_budget_assessment,
    safe_crop_envelope_from_placement,
)
from x5crop.detection.photo_geometry.chain_direction_evidence import (
    lane_direction_evidence,
)
from x5crop.detection.photo_geometry.chain_record_model import (
    ChainEvidenceTier,
    ChainLedgerEntry,
    CompleteChainRecord,
)
from x5crop.detection.photo_geometry.chain_observation_accounting import (
    ObservationDisposition,
    account_chain_observations,
)
from x5crop.detection.photo_geometry.observation_spatial_index import (
    build_chain_observation_spatial_index,
)
from x5crop.detection.photo_geometry.content_veto import content_veto_assessment
from x5crop.detection.photo_geometry.content_veto_model import ContentVetoReason
from x5crop.detection.photo_geometry.content_topology import (
    build_content_topology_index,
)
from x5crop.detection.photo_geometry.content_boundary_queries import (
    separator_core_content_contradictions,
)
from x5crop.detection.photo_geometry.boundary_geometry import (
    outward_boundary_projection,
)
from x5crop.detection.photo_geometry.cross_dominance import (
    cross_measurements_strictly_dominate,
    minimum_safe_cross_pair_relation,
)
from x5crop.detection.photo_geometry.placement_clusters import (
    PlacementCluster,
    cluster_sampling_equivalent_chains,
)
from x5crop.detection.photo_geometry.producer_receipts import (
    CorridorEdgeFamilyCount,
    ProducerBoundsReceipt,
)
from x5crop.detection.photo_geometry.placement_dominance import (
    minimum_safe_outer_boundary_relation,
)
from x5crop.detection.photo_geometry.source_selection_model import (
    SourcePlacementCombination,
)
from x5crop.detection.photo_geometry.source_combinations import (
    compatible_source_geometry_clusters,
)
from x5crop.detection.photo_geometry.source_dominance import (
    minimum_safe_source_variant_strictly_dominates,
    source_strictly_dominates,
)
from x5crop.detection.photo_geometry.sequence_dominance import (
    minimum_safe_separator_relation,
)
from x5crop.detection.photo_geometry.axis_authority import (
    CrossAuthorityVector,
    SequenceAuthorityVector,
    SharedAuthorityVector,
    componentwise_authority_relation,
    tiered_authority_relation,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.sequence_models import LocalAdvanceKind
from x5crop.domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)


def make_chain(
    name: str,
    *,
    box: Box,
    interval: FiniteInterval,
    pair_count: int = 1,
    direct_count: int = 2,
    identities: tuple[str, ...] = ("a", "b"),
) -> CompleteChainRecord:
    observation_ids = tuple(ObservationId(value) for value in identities)
    return CompleteChainRecord(
        chain_id=f"chain:{name}",
        placement_id=f"placement:{name}",
        lane_id="lane:0",
        sampling_boxes=(box,),
        sampling_authority_boxes=(Box(0, 0, 20, 20),),
        authority_profile_ids=("holder:test",),
        boundary_intervals_px=(interval,) * 4,
        direction_id="direction:test",
        source_scan_geometry_id="source-geometry:test",
        direct_observation_count=direct_count,
        separator_band_count=0,
        structural_pair_count=pair_count,
        cross_axis_pair_supported=True,
        cross_axis_support_region_count=4,
        cross_axis_observation_ids=observation_ids,
        direct_observation_ids=observation_ids,
        structural_observation_ids=observation_ids,
        normal_gap_supported=True,
        separator_support_region_count=0,
        lane_direction_disagreement_degrees=0.0,
        direction_observation_ids=observation_ids,
        separator_material_quality=1.0,
        local_advance_authorized=True,
        ledger=(),
    )


def make_placement(
    name: str,
    residual: float = 0.0,
    *,
    cross_top: FiniteInterval = FiniteInterval.exact(1.0),
    cross_bottom: FiniteInterval = FiniteInterval.exact(9.0),
    cross_top_observation_id: str | None = None,
    cross_bottom_observation_id: str | None = None,
    top_role_consistency: float = 1.0,
    bottom_role_consistency: float = 1.0,
    top_fit_direction: FiniteInterval = FiniteInterval.exact(0.0),
    bottom_fit_direction: FiniteInterval = FiniteInterval.exact(0.0),
):
    boundary = SimpleNamespace(
        full_position_interval_px=FiniteInterval.exact(1.0)
    )
    frame = FramePhysicalSpec(36.0, 24.0, 2.0)
    geometry = SourceScanGeometry.create(
        frame,
        width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
    )
    return SimpleNamespace(
        placement_id=f"placement:{name}",
        output_slot_count=1,
        fixed_frames=SimpleNamespace(
            frames=(
                SimpleNamespace(
                    start=boundary,
                    end=boundary,
                    top=boundary,
                    bottom=boundary,
                ),
            )
        ),
        sequence=SimpleNamespace(
            observations=(
                SimpleNamespace(
                    fit_residual_px=residual,
                    observation_id=None,
                    role=SimpleNamespace(role_index=0),
                ),
            ),
            separator_bands=(),
            local_advance_relations=(),
        ),
        cross=SimpleNamespace(
            evidence=(
                SimpleNamespace(
                    role=BoundaryRole.TOP,
                    observation=SimpleNamespace(
                        observation_id=ObservationId(
                            cross_top_observation_id or f"top:{name}"
                        ),
                        fit_residual_px=residual,
                        transition_ids=(
                            ObservationId(f"top-transition:{name}"),
                        ),
                        angle_interval_degrees=FiniteInterval.exact(0.0),
                        fit_angle_interval_degrees=top_fit_direction,
                        offset_interval_px=cross_top,
                        independent_support_region_count=2,
                        trace_support_count=2,
                        left_background_preference_fraction=(
                            top_role_consistency
                        ),
                        right_background_preference_fraction=(
                            1.0 - top_role_consistency
                        ),
                        line=SimpleNamespace(
                            support_projection_px=FiniteInterval(0.0, 10.0)
                        ),
                    ),
                    canonical_position_at_lane_reference_px=(
                        cross_top.center
                    ),
                ),
                SimpleNamespace(
                    role=BoundaryRole.BOTTOM,
                    observation=SimpleNamespace(
                        observation_id=ObservationId(
                            cross_bottom_observation_id or f"bottom:{name}"
                        ),
                        fit_residual_px=residual,
                        transition_ids=(
                            ObservationId(f"bottom-transition:{name}"),
                        ),
                        angle_interval_degrees=FiniteInterval.exact(0.0),
                        fit_angle_interval_degrees=bottom_fit_direction,
                        offset_interval_px=cross_bottom,
                        independent_support_region_count=2,
                        trace_support_count=2,
                        left_background_preference_fraction=(
                            1.0 - bottom_role_consistency
                        ),
                        right_background_preference_fraction=(
                            bottom_role_consistency
                        ),
                        line=SimpleNamespace(
                            support_projection_px=FiniteInterval(0.0, 10.0)
                        ),
                    ),
                    canonical_position_at_lane_reference_px=(
                        cross_bottom.center
                    ),
                ),
            ),
            direct_height_span_validated=True,
            top_full_positions_px=(cross_top,),
            bottom_full_positions_px=(cross_bottom,),
            top_canonical_positions_px=(cross_top.center,),
            bottom_canonical_positions_px=(cross_bottom.center,),
        ),
        lane_geometry=SimpleNamespace(
            nominal_centerline_px=5.0,
            direction=SimpleNamespace(
                full_angle_interval_degrees=FiniteInterval.exact(0.0)
            )
        ),
        source_scan_geometry=geometry,
    )


def make_cluster(
    name: str,
    *,
    pair_count: int,
    direct_count: int,
    pair_ids: tuple[str, ...],
    direct_ids: tuple[str, ...],
    separator_band_count: int = 0,
    cross_axis_pair_supported: bool = True,
    cross_axis_support_regions: int = 4,
    sampling_box: Box = Box(0, 0, 10, 10),
    direction_disagreement: float = 0.0,
) -> PlacementCluster:
    return PlacementCluster(
        cluster_id=f"cluster:{name}",
        chain_ids=(f"chain:{name}",),
        representative_placement_id=f"placement:{name}",
        sampling_boxes=(sampling_box,),
        boundary_intersections_px=(FiniteInterval.exact(1.0),) * 4,
        direct_observation_count=direct_count,
        separator_band_count=separator_band_count,
        structural_pair_count=pair_count,
        cross_axis_pair_supported=cross_axis_pair_supported,
        cross_axis_support_region_count=cross_axis_support_regions,
        cross_axis_observation_ids=tuple(
            ObservationId(value) for value in direct_ids
        ),
        direct_observation_ids=tuple(
            ObservationId(value) for value in direct_ids
        ),
        structural_observation_ids=tuple(
            ObservationId(value) for value in pair_ids
        ),
        normal_gap_supported=True,
        separator_support_region_count=0,
        lane_direction_disagreement_degrees=direction_disagreement,
        direction_observation_ids=tuple(
            ObservationId(value) for value in direct_ids
        ),
        separator_material_quality=1.0,
    )


def make_source_combination(
    name: str,
    cluster: PlacementCluster,
    *,
    accounted_ids: tuple[str, ...] | None = None,
) -> SourcePlacementCombination:
    frame = FramePhysicalSpec(36.0, 24.0, 2.0)
    geometry = SourceScanGeometry.create(
        frame,
        width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
    )
    return SourcePlacementCombination(
        combination_id=f"combination:{name}",
        lane_cluster_ids=(cluster.cluster_id,),
        lane_placement_ids=(cluster.representative_placement_id,),
        shared_scan_geometry=geometry,
        direct_observation_ids=cluster.direct_observation_ids,
        direct_observation_count=cluster.direct_observation_count,
        separator_band_count=cluster.separator_band_count,
        structural_observation_ids=cluster.structural_observation_ids,
        structural_strength=cluster.structural_pair_count + 1,
        cross_axis_pair_count=int(cluster.cross_axis_pair_supported),
        cross_axis_support_region_count=(
            cluster.cross_axis_support_region_count
        ),
        cross_axis_observation_ids=cluster.cross_axis_observation_ids,
        separator_support_region_count=0,
        lane_direction_disagreement_degrees=(
            cluster.lane_direction_disagreement_degrees
        ),
        direction_observation_ids=cluster.direction_observation_ids,
        separator_material_quality=1.0,
        sequence_authority=SequenceAuthorityVector(
            complete_direct_chain_count=int(
                cluster.separator_band_count > 0
            ),
            direct_separator_band_count=cluster.separator_band_count,
            independent_separator_support_region_count=(
                cluster.separator_support_region_count
            ),
            direct_outer_boundary_count=0,
            normal_completion_authorized_count=int(
                cluster.normal_gap_supported
            ),
            local_advance_authorized_count=1,
            filled_holder_centering_authorized_count=0,
            observation_ids=cluster.direct_observation_ids,
        ),
        cross_authority=CrossAuthorityVector(
            fixed_height_placement_authorized_count=1,
            complete_top_bottom_pair_count=int(
                cluster.cross_axis_pair_supported
            ),
            direct_height_span_validated_count=int(
                cluster.cross_axis_pair_supported
            ),
            common_top_bottom_direction_count=int(
                cluster.cross_axis_pair_supported
            ),
            source_spanning_boundary_family_count=0,
            direct_boundary_family_count=(
                2 if cluster.cross_axis_pair_supported else 1
            ),
            independent_support_region_count=(
                cluster.cross_axis_support_region_count
            ),
            observation_ids=cluster.cross_axis_observation_ids,
        ),
        shared_authority=SharedAuthorityVector(
            source_scale_compatible=True,
            direction_bound_lane_count=1,
            source_lane_authority_bound_count=1,
            content_veto_passed_lane_count=1,
        ),
        accounted_observation_ids=tuple(
            ObservationId(value)
            for value in dict.fromkeys(
                (
                    *map(str, cluster.direct_observation_ids),
                    *(accounted_ids or ()),
                )
            )
        ),
    )


def make_placement_map(
    *clusters: PlacementCluster,
) -> dict[str, object]:
    return {
        cluster.representative_placement_id: make_placement(
            cluster.representative_placement_id.split(":", 1)[1]
        )
        for cluster in clusters
    }


def make_observation(box: Box) -> ContentOccupancyObservationSet:
    identity = ObservationId(
        f"content:{box.left}:{box.top}:{box.right}:{box.bottom}"
    )
    observation = ContentOccupancyObservation(
        observation_id=identity,
        lane_id="lane:0",
        source_box=box,
        source_cells=tuple(
            Box(left, top, left + 1, top + 1)
            for left in range(box.left, box.right)
            for top in range(box.top, box.bottom)
        ),
        reliability=0.95,
    )
    return ContentOccupancyObservationSet(
        lane_id="lane:0",
        observations=(observation,),
        long_step_px=1,
        cross_step_px=1,
        long_sample_count=16,
        cross_sample_count=16,
        occupied_cell_count=box.width * box.height,
        long_support_depth_px=1,
        cross_support_depth_px=1,
    )


def make_frame(
    start: float,
    end: float,
    *,
    direction_degrees: FiniteInterval = FiniteInterval.exact(0.0),
):
    def boundary(role: BoundaryRole, position: float) -> FrameBoundaryGeometry:
        cross = role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        return FrameBoundaryGeometry(
            role=role,
            line=SourceCoordinateLine(
                normal_x=0.0 if cross else 1.0,
                normal_y=1.0 if cross else 0.0,
                offset_px=position,
                support_projection_px=FiniteInterval(0.0, 40.0),
                source_axis_long=BoundaryAxis.X,
            ),
            reference_trace_px=15.0,
            canonical_position_px=position,
            full_position_interval_px=FiniteInterval.exact(position),
            full_direction_interval_degrees=direction_degrees,
            position_source=PositionSource.OBSERVED_TRANSITION,
            position_observation_ids=(
                ObservationId(f"boundary:{role.value}:{position}"),
            ),
            named_position_inference=None,
            direction_authority=(
                DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
                if cross
                else DirectionAuthority.BOUNDED_SEQUENCE_EDGE_DIRECTION
            ),
            direction_reference_id="direction:test",
        )

    return SimpleNamespace(
        start=boundary(BoundaryRole.START, start),
        end=boundary(BoundaryRole.END, end),
        top=boundary(BoundaryRole.TOP, 10.0),
        bottom=boundary(BoundaryRole.BOTTOM, 20.0),
    )


def make_content_placement(
    frames: tuple[object, ...],
    relations: tuple[LocalAdvanceKind, ...],
):
    return SimpleNamespace(
        placement_id="placement:content",
        fixed_frames=SimpleNamespace(frames=frames),
        sequence=SimpleNamespace(
            lane_gap_model=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
                gap_interval_px=FiniteInterval.exact(4.0),
            ),
            local_advance_relations=tuple(
                SimpleNamespace(kind=value) for value in relations
            ),
        ),
    )



# The split contract modules share one explicit fixture namespace.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
