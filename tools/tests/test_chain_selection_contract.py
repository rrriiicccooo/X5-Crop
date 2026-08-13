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


def _chain(
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


def _placement(
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


def _cluster(
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


def _source_combination(
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


def _placement_map(
    *clusters: PlacementCluster,
) -> dict[str, object]:
    return {
        cluster.representative_placement_id: _placement(
            cluster.representative_placement_id.split(":", 1)[1]
        )
        for cluster in clusters
    }


def _observation(box: Box) -> ContentOccupancyObservationSet:
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


def _frame(
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


def _content_placement(
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


class ChainSelectionContractTest(unittest.TestCase):
    def test_producer_overflow_is_a_real_coverage_state(self) -> None:
        complete = CorridorEdgeFamilyCount("corridor:complete", 3, 3)
        incomplete = CorridorEdgeFamilyCount("corridor:incomplete", 4, 3)
        ProducerBoundsReceipt(
            lane_id="lane:0",
            corridor_edge_families=(complete,),
            proposed_complete_chain_count=0,
            materialized_complete_chain_count=0,
            chain_ledger_entry_count=0,
            prune_summaries=(),
            bound_exceeded=False,
        )
        ProducerBoundsReceipt(
            lane_id="lane:0",
            corridor_edge_families=(incomplete,),
            proposed_complete_chain_count=0,
            materialized_complete_chain_count=0,
            chain_ledger_entry_count=0,
            prune_summaries=(),
            bound_exceeded=True,
        )
        with self.assertRaises(ValueError):
            ProducerBoundsReceipt(
                lane_id="lane:0",
                corridor_edge_families=(incomplete,),
                proposed_complete_chain_count=0,
                materialized_complete_chain_count=0,
                chain_ledger_entry_count=0,
                prune_summaries=(),
                bound_exceeded=False,
            )

    def test_outer_and_recombined_separator_bands_are_not_new_votes(self) -> None:
        start_role = SimpleNamespace(
            role=SimpleNamespace(value="start"),
            lane_ordinal=1,
        )
        end_role = SimpleNamespace(
            role=SimpleNamespace(value="end"),
            lane_ordinal=1,
        )
        placement = SimpleNamespace(
            fixed_frames=SimpleNamespace(
                frames=(_frame(100.0, 200.0), _frame(230.0, 330.0))
            ),
            sequence=SimpleNamespace(
                separator_bands=(),
                observations=(
                    SimpleNamespace(
                        observation_id=ObservationId("edge:start"),
                        role=start_role,
                    ),
                    SimpleNamespace(
                        observation_id=ObservationId("edge:end"),
                        role=end_role,
                    ),
                ),
            ),
            cross=SimpleNamespace(evidence=()),
        )
        edges = (
            SimpleNamespace(
                observation_id=ObservationId("edge:outer"),
                coordinate_interval_px=FiniteInterval(70.0, 80.0),
            ),
            SimpleNamespace(
                observation_id=ObservationId("edge:start"),
                coordinate_interval_px=FiniteInterval(99.0, 101.0),
            ),
            SimpleNamespace(
                observation_id=ObservationId("edge:end"),
                coordinate_interval_px=FiniteInterval(199.0, 201.0),
            ),
            SimpleNamespace(
                observation_id=ObservationId("edge:internal"),
                coordinate_interval_px=FiniteInterval(249.0, 251.0),
            ),
            SimpleNamespace(
                observation_id=ObservationId("edge:after-last"),
                coordinate_interval_px=FiniteInterval(350.0, 360.0),
            ),
        )
        bands = (
            SimpleNamespace(
                observation_id=ObservationId("band:outer"),
                left_edge_observation_id=ObservationId("edge:outer"),
                right_edge_observation_id=ObservationId("edge:start"),
            ),
            SimpleNamespace(
                observation_id=ObservationId("band:recombined"),
                left_edge_observation_id=ObservationId("edge:end"),
                right_edge_observation_id=ObservationId("edge:internal"),
            ),
        )
        accounting = account_chain_observations(
            placement,
            build_chain_observation_spatial_index(edges, bands, ()),
            include_facts=True,
        )
        self.assertTrue(
            {
                ObservationId("band:outer"),
                ObservationId("band:recombined"),
                ObservationId("edge:after-last"),
            }.issubset(accounting.accounted_observation_ids)
        )
        by_id = {item.observation_id: item for item in accounting.facts}
        self.assertEqual(
            by_id[ObservationId("band:outer")].disposition,
            ObservationDisposition.EXPLAINED_NON_BOUNDARY,
        )
        self.assertEqual(
            by_id[ObservationId("band:recombined")].disposition,
            ObservationDisposition.EXPLAINED_NON_BOUNDARY,
        )
        self.assertEqual(
            by_id[ObservationId("edge:after-last")].disposition,
            ObservationDisposition.EXPLAINED_NON_BOUNDARY,
        )

    def test_observation_interval_index_preserves_exact_interval_relations(self) -> None:
        edges = tuple(
            SimpleNamespace(
                observation_id=ObservationId(identity),
                coordinate_interval_px=interval,
            )
            for identity, interval in (
                ("a", FiniteInterval(0.0, 2.0)),
                ("b", FiniteInterval(2.0, 4.0)),
                ("c", FiniteInterval(3.0, 5.0)),
                ("d", FiniteInterval(6.0, 7.0)),
            )
        )
        index = build_chain_observation_spatial_index(edges, (), ()).edge_intervals
        self.assertEqual(
            set(index.intersecting(FiniteInterval(2.0, 3.0))),
            {ObservationId("a"), ObservationId("b"), ObservationId("c")},
        )
        self.assertEqual(
            set(index.strictly_inside(FiniteInterval(1.0, 6.0))),
            {ObservationId("b"), ObservationId("c")},
        )
        self.assertEqual(
            index.entirely_before(3.0),
            (ObservationId("a"),),
        )
        self.assertEqual(
            index.entirely_after(5.0),
            (ObservationId("d"),),
        )

    def test_axis_authority_is_componentwise_and_never_compensates(self) -> None:
        self.assertEqual(
            componentwise_authority_relation((3, 2, 1), (2, 2, 1)),
            1,
        )
        self.assertEqual(
            componentwise_authority_relation((2, 2, 1), (3, 2, 1)),
            -1,
        )
        self.assertIsNone(
            componentwise_authority_relation((3, 1, 1), (2, 2, 1))
        )

    def test_lower_tier_quantity_cannot_cancel_higher_tier_authority(
        self,
    ) -> None:
        self.assertEqual(
            tiered_authority_relation(
                (1, 1, 1, 1, 2, 4),
                (1, 1, 1, 0, 2, 5),
            ),
            1,
        )

    def test_dual_lane_selection_only_joins_prebound_shared_geometry(
        self,
    ) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)

        def geometry(minimum: float, maximum: float) -> SourceScanGeometry:
            return SourceScanGeometry.create(
                frame,
                width_scale_px_per_mm=PositiveInterval(minimum, maximum),
                height_scale_px_per_mm=PositiveInterval(minimum, maximum),
            )

        compatible = _cluster(
            "compatible",
            pair_count=1,
            direct_count=1,
            pair_ids=("a",),
            direct_ids=("a",),
        )
        incompatible = _cluster(
            "incompatible",
            pair_count=1,
            direct_count=1,
            pair_ids=("b",),
            direct_ids=("b",),
        )
        shared = geometry(9.5, 10.0)
        right = {
            compatible.representative_placement_id: SimpleNamespace(
                frame_spec=frame,
                source_scan_geometry=shared,
            ),
            incompatible.representative_placement_id: SimpleNamespace(
                frame_spec=frame,
                source_scan_geometry=geometry(11.0, 12.0),
            ),
        }
        matches = compatible_source_geometry_clusters(
            (compatible, incompatible),
            right,
            SimpleNamespace(
                frame_spec=frame,
                source_scan_geometry=shared,
            ),
        )
        self.assertEqual(
            tuple(item.cluster_id for item, _shared in matches),
            (compatible.cluster_id,),
        )
        self.assertEqual(
            matches[0][1].width_state.feasible_scale_interval(),
            PositiveInterval(9.5, 10.0),
        )

    def test_chain_ledger_preserves_every_unique_entry(self) -> None:
        entries = tuple(
            ChainLedgerEntry(
                entry_id=f"entry:{ordinal}",
                chain_id="chain:overflow",
                ordinal=ordinal,
                evidence_tier=ChainEvidenceTier.WEAK_PRIOR,
                observation_ids=(),
                physical_interval_px=None,
            )
            for ordinal in range(1, 66)
        )
        record = CompleteChainRecord(
            chain_id="chain:overflow",
            placement_id="placement:overflow",
            lane_id="lane:0",
            sampling_boxes=(Box(0, 0, 10, 10),),
            sampling_authority_boxes=(Box(0, 0, 20, 20),),
            authority_profile_ids=("holder:test",),
            boundary_intervals_px=(FiniteInterval.exact(1.0),) * 4,
            direction_id="direction:test",
            source_scan_geometry_id="source-geometry:test",
            direct_observation_count=0,
            separator_band_count=0,
            structural_pair_count=0,
            cross_axis_pair_supported=False,
            cross_axis_support_region_count=0,
            cross_axis_observation_ids=(),
            direct_observation_ids=(),
            structural_observation_ids=(),
            normal_gap_supported=False,
            separator_support_region_count=0,
            lane_direction_disagreement_degrees=0.0,
            direction_observation_ids=(),
            separator_material_quality=0.0,
            local_advance_authorized=True,
            ledger=entries,
        )
        self.assertEqual(len(record.ledger), 65)

    def test_safe_envelope_and_budget_accept_one_selected_placement(self) -> None:
        self.assertIn(
            "placement",
            inspect.signature(safe_crop_envelope_from_placement).parameters,
        )
        self.assertNotIn(
            "placements",
            inspect.signature(safe_crop_envelope_from_placement).parameters,
        )
        self.assertIn(
            "placement",
            inspect.signature(direct_use_budget_assessment).parameters,
        )
        self.assertNotIn(
            "placements",
            inspect.signature(direct_use_budget_assessment).parameters,
        )
        self.assertNotIn(
            "minimum_guard",
            inspect.getsource(safe_crop_envelope_from_placement),
        )

    def test_sampling_cluster_requires_exact_boxes_and_common_intervals(
        self,
    ) -> None:
        first = _chain(
            "first",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(1.0, 2.0),
        )
        equivalent = _chain(
            "equivalent",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(1.5, 2.5),
        )
        displaced = _chain(
            "displaced",
            box=Box(1, 0, 11, 10),
            interval=FiniteInterval(1.5, 2.5),
        )
        disjoint = _chain(
            "disjoint",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(3.0, 4.0),
        )
        placements = {
            item.placement_id: _placement(item.placement_id.split(":", 1)[1])
            for item in (first, equivalent, displaced, disjoint)
        }
        clusters = cluster_sampling_equivalent_chains(
            (first, equivalent, displaced, disjoint),
            placements,
        )
        self.assertEqual(sorted(len(item.chain_ids) for item in clusters), [1, 1, 2])
        self.assertEqual(
            clusters,
            cluster_sampling_equivalent_chains(
                (disjoint, displaced, equivalent, first),
                placements,
            ),
        )

    def test_flat_direct_count_cannot_create_cross_axis_dominance(self) -> None:
        authority = _cluster(
            "authority",
            pair_count=2,
            direct_count=4,
            pair_ids=("a", "b", "c"),
            direct_ids=("a", "b", "c", "d"),
        )
        explained = _cluster(
            "explained",
            pair_count=1,
            direct_count=3,
            pair_ids=("a", "b"),
            direct_ids=("a", "b", "d"),
        )
        unexplained = _cluster(
            "unexplained",
            pair_count=1,
            direct_count=3,
            pair_ids=("a", "x"),
            direct_ids=("a", "x", "d"),
        )
        authority_combination = _source_combination("authority", authority)
        explained_combination = _source_combination("explained", explained)
        unexplained_combination = _source_combination(
            "unexplained", unexplained
        )
        clusters = {
            item.cluster_id: item
            for item in (authority, explained, unexplained)
        }
        self.assertFalse(
            source_strictly_dominates(
                authority_combination,
                explained_combination,
                _placement_map(authority, explained, unexplained),
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                authority_combination,
                unexplained_combination,
                _placement_map(authority, explained, unexplained),
            )
        )

    def test_complete_separator_band_precedes_explained_isolated_edge(self) -> None:
        band_chain = _cluster(
            "separator-band",
            pair_count=2,
            direct_count=3,
            pair_ids=("top", "bottom", "band"),
            direct_ids=("top", "bottom", "band"),
            separator_band_count=1,
        )
        isolated_edge_chain = _cluster(
            "isolated-edge",
            pair_count=2,
            direct_count=4,
            pair_ids=("top", "bottom"),
            direct_ids=("top", "bottom", "edge-a", "edge-b"),
            separator_band_count=0,
        )
        band_combination = _source_combination(
            "separator-band",
            band_chain,
            accounted_ids=("edge-a", "edge-b"),
        )
        isolated_combination = _source_combination(
            "isolated-edge",
            isolated_edge_chain,
        )
        clusters = {
            item.cluster_id: item
            for item in (band_chain, isolated_edge_chain)
        }
        placements = _placement_map(band_chain, isolated_edge_chain)
        self.assertTrue(
            source_strictly_dominates(
                band_combination,
                isolated_combination,
                placements,
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                isolated_combination,
                band_combination,
                placements,
            )
        )

    def test_cross_pair_does_not_preempt_two_separator_bands(self) -> None:
        cross_pair = _cluster(
            "cross-pair",
            pair_count=1,
            direct_count=4,
            pair_ids=("top", "bottom"),
            direct_ids=("top", "bottom", "edge-a", "edge-b"),
            separator_band_count=0,
            cross_axis_pair_supported=True,
        )
        separator_chain = _cluster(
            "separator-chain",
            pair_count=2,
            direct_count=4,
            pair_ids=("band-a", "band-b"),
            direct_ids=("cross", "outer", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=False,
        )
        cross_combination = _source_combination(
            "cross-pair",
            cross_pair,
            accounted_ids=separator_chain.direct_observation_ids,
        )
        separator_combination = _source_combination(
            "separator-chain",
            separator_chain,
            accounted_ids=cross_pair.direct_observation_ids,
        )
        clusters = {
            item.cluster_id: item for item in (cross_pair, separator_chain)
        }
        placements = _placement_map(cross_pair, separator_chain)
        self.assertFalse(
            source_strictly_dominates(
                separator_combination,
                cross_combination,
                placements,
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                cross_combination,
                separator_combination,
                placements,
            )
        )

    def test_cross_pair_breaks_tie_after_separator_chain_is_fixed(self) -> None:
        paired = _cluster(
            "paired-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top", "bottom", "band-a", "band-b"),
            direct_ids=("top", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=True,
        )
        isolated = _cluster(
            "isolated-cross",
            pair_count=2,
            direct_count=5,
            pair_ids=("edge", "band-a", "band-b"),
            direct_ids=("top", "edge", "outer", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=False,
        )
        paired_combination = _source_combination(
            "paired-cross",
            paired,
            accounted_ids=isolated.direct_observation_ids,
        )
        isolated_combination = _source_combination(
            "isolated-cross",
            isolated,
            accounted_ids=paired.direct_observation_ids,
        )
        clusters = {item.cluster_id: item for item in (paired, isolated)}
        placements = _placement_map(paired, isolated)
        self.assertTrue(
            source_strictly_dominates(
                paired_combination,
                isolated_combination,
                placements,
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                isolated_combination,
                paired_combination,
                placements,
            )
        )

    def test_repeated_cross_axis_regions_break_same_evidence_tier_tie(
        self,
    ) -> None:
        stronger = _cluster(
            "stronger-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("a", "b"),
            direct_ids=("a", "b", "c", "d"),
            cross_axis_support_regions=6,
        )
        weaker = _cluster(
            "weaker-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("a", "b"),
            direct_ids=("a", "b", "c", "d"),
            cross_axis_support_regions=4,
        )
        stronger_combination = _source_combination("stronger-cross", stronger)
        weaker_combination = _source_combination("weaker-cross", weaker)
        clusters = {
            item.cluster_id: item for item in (stronger, weaker)
        }
        self.assertTrue(
            source_strictly_dominates(
                stronger_combination,
                weaker_combination,
                _placement_map(stronger, weaker),
            )
        )

    def test_cross_measurement_uses_fit_quality_not_pixel_quantity_or_interval_width(
        self,
    ) -> None:
        precise = _placement(
            "precise-cross-measurement",
            cross_top=FiniteInterval(1.0, 2.0),
        )
        noisy = _placement(
            "noisy-cross-measurement",
            cross_top=FiniteInterval(1.5, 2.5),
        )
        precise_top = precise.cross.evidence[0].observation
        noisy_top = noisy.cross.evidence[0].observation
        precise_top.fit_residual_px = 0.5
        precise_top.angle_interval_degrees = FiniteInterval(-0.3, 0.3)
        precise_top.offset_interval_px = FiniteInterval(0.5, 2.5)
        precise_top.trace_support_count = 3
        precise_top.line.support_projection_px = FiniteInterval(0.0, 10.0)
        noisy_top.fit_residual_px = 1.0
        noisy_top.angle_interval_degrees = FiniteInterval(-0.1, 0.1)
        noisy_top.offset_interval_px = FiniteInterval(1.0, 2.0)
        noisy_top.trace_support_count = 300
        noisy_top.line.support_projection_px = FiniteInterval(0.0, 1000.0)
        placements = {
            precise.placement_id: precise,
            noisy.placement_id: noisy,
        }

        self.assertTrue(
            cross_measurements_strictly_dominate(
                (precise.placement_id,),
                (noisy.placement_id,),
                placements,
            )
        )
        self.assertFalse(
            cross_measurements_strictly_dominate(
                (noisy.placement_id,),
                (precise.placement_id,),
                placements,
            )
        )

    def test_cross_pair_compares_its_weaker_role_consistency(self) -> None:
        consistent = _placement(
            "role-consistent-cross",
            residual=2.0,
            top_role_consistency=0.8,
            bottom_role_consistency=1.0,
        )
        ambiguous = _placement(
            "role-ambiguous-cross",
            residual=0.25,
            top_role_consistency=0.51,
            bottom_role_consistency=0.99,
        )
        placements = {
            consistent.placement_id: consistent,
            ambiguous.placement_id: ambiguous,
        }

        self.assertTrue(
            cross_measurements_strictly_dominate(
                (consistent.placement_id,),
                (ambiguous.placement_id,),
                placements,
            )
        )
        self.assertFalse(
            cross_measurements_strictly_dominate(
                (ambiguous.placement_id,),
                (consistent.placement_id,),
                placements,
            )
        )

    def test_common_top_bottom_direction_precedes_material_preference(self) -> None:
        common_direction = _placement(
            "common-direction-cross",
            residual=2.0,
            top_role_consistency=0.6,
            bottom_role_consistency=0.6,
            top_fit_direction=FiniteInterval(0.10, 0.20),
            bottom_fit_direction=FiniteInterval(0.15, 0.25),
        )
        displaced_direction = _placement(
            "displaced-direction-cross",
            residual=0.25,
            top_role_consistency=1.0,
            bottom_role_consistency=1.0,
            top_fit_direction=FiniteInterval(0.10, 0.20),
            bottom_fit_direction=FiniteInterval(0.30, 0.40),
        )
        placements = {
            common_direction.placement_id: common_direction,
            displaced_direction.placement_id: displaced_direction,
        }

        self.assertTrue(
            cross_measurements_strictly_dominate(
                (common_direction.placement_id,),
                (displaced_direction.placement_id,),
                placements,
            )
        )
        self.assertFalse(
            cross_measurements_strictly_dominate(
                (displaced_direction.placement_id,),
                (common_direction.placement_id,),
                placements,
            )
        )

    def test_top_and_bottom_role_consistency_cannot_compensate(self) -> None:
        stronger_top = _placement(
            "stronger-top-cross",
            residual=0.25,
            top_role_consistency=0.9,
            bottom_role_consistency=0.7,
        )
        stronger_bottom = _placement(
            "stronger-bottom-cross",
            residual=2.0,
            top_role_consistency=0.7,
            bottom_role_consistency=0.9,
        )
        placements = {
            stronger_top.placement_id: stronger_top,
            stronger_bottom.placement_id: stronger_bottom,
        }

        self.assertFalse(
            cross_measurements_strictly_dominate(
                (stronger_top.placement_id,),
                (stronger_bottom.placement_id,),
                placements,
            )
        )
        self.assertFalse(
            cross_measurements_strictly_dominate(
                (stronger_bottom.placement_id,),
                (stronger_top.placement_id,),
                placements,
            )
        )

    def test_distinct_direct_cross_pairs_are_not_minimum_safe_variants(
        self,
    ) -> None:
        first = _placement(
            "first-direct-pair",
            cross_top=FiniteInterval(1.0, 2.0),
            cross_bottom=FiniteInterval(8.0, 9.0),
        )
        second = _placement(
            "second-direct-pair",
            cross_top=FiniteInterval(1.5, 2.5),
            cross_bottom=FiniteInterval(7.5, 8.5),
        )

        self.assertIsNone(
            minimum_safe_cross_pair_relation(
                (first.placement_id,),
                (second.placement_id,),
                {
                    first.placement_id: first,
                    second.placement_id: second,
                },
            )
        )

    def test_cross_authority_precedes_minimum_safe_pair(
        self,
    ) -> None:
        smaller = _cluster(
            "smaller-safe-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-a", "bottom"),
            direct_ids=("top-a", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        larger = _cluster(
            "larger-safe-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-b", "bottom"),
            direct_ids=("top-b", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        smaller_combination = _source_combination(
            "smaller-safe-cross",
            smaller,
            accounted_ids=("top-b",),
        )
        larger_combination = _source_combination(
            "larger-safe-cross",
            larger,
            accounted_ids=("top-a",),
        )
        placements = _placement_map(smaller, larger)
        placements[smaller.representative_placement_id] = _placement(
            "smaller-safe-cross",
            cross_top=FiniteInterval(1.25, 2.0),
            cross_bottom=FiniteInterval(8.0, 8.75),
            cross_bottom_observation_id="bottom:shared",
        )
        placements[larger.representative_placement_id] = _placement(
            "larger-safe-cross",
            cross_top=FiniteInterval(1.0, 1.5),
            cross_bottom=FiniteInterval(8.5, 9.0),
            cross_bottom_observation_id="bottom:shared",
        )
        clusters = {
            item.cluster_id: item for item in (smaller, larger)
        }
        # The geometric relation alone says that the first pair is smaller,
        # but the competing pair owns an additional independent cross support
        # region.  Selection must compare that direct cross authority first;
        # "smaller" is not permission to discard stronger evidence.
        self.assertTrue(
            minimum_safe_source_variant_strictly_dominates(
                smaller_combination,
                larger_combination,
                placements,
            )
        )
        clusters = {item.cluster_id: item for item in (smaller, larger)}
        self.assertTrue(
            source_strictly_dominates(
                larger_combination,
                smaller_combination,
                placements,
            )
        )

    def test_direct_opposite_edge_cannot_be_discarded_as_minimum_safe(self) -> None:
        inner = _cluster(
            "inner-safe-cross",
            pair_count=1,
            direct_count=3,
            pair_ids=("bottom",),
            direct_ids=("bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=False,
            cross_axis_support_regions=3,
        )
        outer = _cluster(
            "outer-safe-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-outer", "bottom"),
            direct_ids=("top-outer", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        inner_combination = _source_combination("inner-safe-cross", inner)
        outer_combination = _source_combination("outer-safe-cross", outer)
        inner_combination = replace(
            inner_combination,
            sequence_authority=replace(
                inner_combination.sequence_authority,
                observation_ids=(
                    ObservationId("band-a"),
                    ObservationId("band-b"),
                ),
            ),
            cross_authority=replace(
                inner_combination.cross_authority,
                observation_ids=(ObservationId("bottom"),),
            ),
        )
        outer_combination = replace(
            outer_combination,
            sequence_authority=replace(
                outer_combination.sequence_authority,
                observation_ids=(
                    ObservationId("band-a"),
                    ObservationId("band-b"),
                ),
            ),
            cross_authority=replace(
                outer_combination.cross_authority,
                observation_ids=(
                    ObservationId("top-outer"),
                    ObservationId("bottom"),
                ),
            ),
        )
        placements = _placement_map(inner, outer)
        inner_placement = placements[inner.representative_placement_id]
        outer_placement = placements[outer.representative_placement_id]
        inner_placement.cross.evidence = (inner_placement.cross.evidence[1],)
        inner_placement.cross.direct_height_span_validated = False
        inner_placement.cross.top_full_positions_px = (
            FiniteInterval(1.4, 2.0),
        )
        inner_placement.cross.bottom_full_positions_px = (
            FiniteInterval(8.0, 8.5),
        )
        outer_placement.cross.top_full_positions_px = (
            FiniteInterval(1.0, 1.5),
        )
        outer_placement.cross.bottom_full_positions_px = (
            FiniteInterval(8.0, 8.5),
        )
        inner_placement.cross.evidence[0].observation.observation_id = (
            ObservationId("bottom")
        )
        outer_placement.cross.evidence[0].observation.observation_id = (
            ObservationId("top-outer")
        )
        outer_placement.cross.evidence[1].observation.observation_id = (
            ObservationId("bottom")
        )

        cluster_map = {item.cluster_id: item for item in (inner, outer)}
        self.assertFalse(
            minimum_safe_source_variant_strictly_dominates(
                inner_combination,
                outer_combination,
                placements,
            )
        )
        self.assertTrue(
            source_strictly_dominates(
                outer_combination,
                inner_combination,
                placements,
            )
        )

    def test_shared_cross_observations_do_not_gain_centering_vote(self) -> None:
        left = _placement(
            "shared-cross-left",
            cross_top=FiniteInterval.exact(1.0),
            cross_bottom=FiniteInterval.exact(9.0),
            cross_top_observation_id="shared-top",
            cross_bottom_observation_id="shared-bottom",
        )
        right = _placement(
            "shared-cross-right",
            cross_top=FiniteInterval.exact(2.0),
            cross_bottom=FiniteInterval.exact(10.0),
            cross_top_observation_id="shared-top",
            cross_bottom_observation_id="shared-bottom",
        )
        relation = minimum_safe_cross_pair_relation(
            (left.placement_id,),
            (right.placement_id,),
            {
                left.placement_id: left,
                right.placement_id: right,
            },
        )
        self.assertEqual(relation, 0)

    def test_inferred_inner_side_cannot_replace_direct_opposite_edge(
        self,
    ) -> None:
        inner = _placement(
            "inner-inferred-top",
            cross_top=FiniteInterval(1.4, 2.0),
            cross_bottom=FiniteInterval(8.0, 8.5),
            cross_bottom_observation_id="bottom:shared",
        )
        outer = _placement(
            "outer-direct-top",
            cross_top=FiniteInterval(1.0, 1.5),
            cross_bottom=FiniteInterval(8.0, 8.5),
            cross_bottom_observation_id="bottom:shared",
        )
        inner.cross.evidence = (inner.cross.evidence[1],)
        inner.cross.direct_height_span_validated = False

        relation = minimum_safe_cross_pair_relation(
            (inner.placement_id,),
            (outer.placement_id,),
            {
                inner.placement_id: inner,
                outer.placement_id: outer,
            },
        )

        self.assertIsNone(relation)

    def test_shared_separator_edge_prefers_smaller_safe_band(self) -> None:
        smaller = _placement("smaller-separator")
        larger = _placement("larger-separator")

        def bound_band(name: str, gap: FiniteInterval):
            return SimpleNamespace(
                relation_ordinal=1,
                observation=SimpleNamespace(
                    observation_id=ObservationId(name),
                    left_edge_observation_id=ObservationId("shared-left"),
                    right_edge_observation_id=ObservationId(
                        f"right:{name}"
                    ),
                    gap_interval_px=gap,
                ),
            )

        smaller.sequence.separator_bands = (
            bound_band("smaller", FiniteInterval(4.0, 5.0)),
        )
        larger.sequence.separator_bands = (
            bound_band("larger", FiniteInterval(4.5, 5.5)),
        )

        relation = minimum_safe_separator_relation(
            (smaller.placement_id,),
            (larger.placement_id,),
            {
                smaller.placement_id: smaller,
                larger.placement_id: larger,
            },
        )

        self.assertEqual(relation, 1)

    def test_same_sequence_core_prefers_smaller_safe_outer_end(self) -> None:
        inner = _placement("inner-last-end")
        outer = _placement("outer-last-end")
        inner.fixed_frames.frames[-1].end.full_position_interval_px = (
            FiniteInterval(18.0, 20.0)
        )
        outer.fixed_frames.frames[-1].end.full_position_interval_px = (
            FiniteInterval(19.0, 22.0)
        )
        inner.sequence.observations = (
            *inner.sequence.observations,
            SimpleNamespace(
                role=SimpleNamespace(role_index=1),
                observation_id=ObservationId("end:inner"),
            ),
        )
        outer.sequence.observations = (
            *outer.sequence.observations,
            SimpleNamespace(
                role=SimpleNamespace(role_index=1),
                observation_id=ObservationId("end:outer"),
            ),
        )

        self.assertEqual(
            minimum_safe_outer_boundary_relation(
                (inner.placement_id,),
                (outer.placement_id,),
                {
                    inner.placement_id: inner,
                    outer.placement_id: outer,
                },
            ),
            1,
        )

    def test_minimum_safe_cross_pair_does_not_compare_disjoint_scale_hypotheses(
        self,
    ) -> None:
        smaller = _cluster(
            "smaller-disjoint-scale",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-a", "bottom-a"),
            direct_ids=("top-a", "bottom-a", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        larger = _cluster(
            "larger-supported-scale",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-b", "bottom-b"),
            direct_ids=("top-b", "bottom-b", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        smaller_combination = _source_combination(
            "smaller-disjoint-scale",
            smaller,
            accounted_ids=("top-b", "bottom-b"),
        )
        larger_combination = _source_combination(
            "larger-supported-scale",
            larger,
        )
        placements = _placement_map(smaller, larger)
        placements[smaller.representative_placement_id] = _placement(
            "smaller-disjoint-scale",
            cross_top=FiniteInterval(2.0, 2.5),
            cross_bottom=FiniteInterval(8.0, 8.5),
        )
        placements[larger.representative_placement_id] = _placement(
            "larger-supported-scale",
            cross_top=FiniteInterval(1.0, 1.5),
            cross_bottom=FiniteInterval(9.0, 9.5),
        )
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        placements[smaller.representative_placement_id].source_scan_geometry = (
            SourceScanGeometry.create(
                frame,
                width_scale_px_per_mm=PositiveInterval(9.0, 9.5),
                height_scale_px_per_mm=PositiveInterval(9.0, 9.5),
            )
        )
        placements[larger.representative_placement_id].source_scan_geometry = (
            SourceScanGeometry.create(
                frame,
                width_scale_px_per_mm=PositiveInterval(10.0, 10.5),
                height_scale_px_per_mm=PositiveInterval(10.0, 10.5),
            )
        )
        clusters = {
            item.cluster_id: item for item in (smaller, larger)
        }
        self.assertFalse(
            source_strictly_dominates(
                smaller_combination,
                larger_combination,
                placements,
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                larger_combination,
                smaller_combination,
                placements,
            )
        )

    def test_displaced_cross_pair_is_not_treated_as_minimum_safe_variant(self) -> None:
        smaller = _cluster(
            "smaller-off-center",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-a", "bottom-a"),
            direct_ids=("top-a", "bottom-a", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        larger = _cluster(
            "larger-centered",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-b", "bottom-b"),
            direct_ids=("top-b", "bottom-b", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        smaller_combination = _source_combination(
            "smaller-off-center",
            smaller,
        )
        larger_combination = _source_combination(
            "larger-centered",
            larger,
        )
        placements = _placement_map(smaller, larger)
        placements[smaller.representative_placement_id] = _placement(
            "smaller-off-center",
            cross_top=FiniteInterval.exact(0.0),
            cross_bottom=FiniteInterval.exact(8.0),
        )
        placements[larger.representative_placement_id] = _placement(
            "larger-centered",
            cross_top=FiniteInterval.exact(2.0),
            cross_bottom=FiniteInterval.exact(10.0),
        )
        clusters = {item.cluster_id: item for item in (smaller, larger)}
        self.assertFalse(
            source_strictly_dominates(
                smaller_combination,
                larger_combination,
                placements,
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                larger_combination,
                smaller_combination,
                placements,
            )
        )

    def test_shared_raw_cross_boundary_is_not_counted_twice(self) -> None:
        inner_top = _cluster(
            "inner-top-shared-bottom",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-inner", "bottom"),
            direct_ids=("top-inner", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        outer_top = _cluster(
            "outer-top-shared-bottom",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-outer", "bottom"),
            direct_ids=("top-outer", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        inner_combination = _source_combination(
            "inner-top-shared-bottom",
            inner_top,
            accounted_ids=("top-outer",),
        )
        outer_combination = _source_combination(
            "outer-top-shared-bottom",
            outer_top,
        )
        placements = _placement_map(inner_top, outer_top)
        placements[inner_top.representative_placement_id] = _placement(
            "inner-top-shared-bottom",
            cross_top=FiniteInterval(1.4, 2.0),
            cross_bottom=FiniteInterval(8.0, 8.5),
            cross_bottom_observation_id="bottom:shared",
        )
        placements[outer_top.representative_placement_id] = _placement(
            "outer-top-shared-bottom",
            cross_top=FiniteInterval(1.0, 1.5),
            cross_bottom=FiniteInterval(7.5, 8.0),
            cross_bottom_observation_id="bottom:shared",
        )
        clusters = {
            item.cluster_id: item for item in (inner_top, outer_top)
        }
        self.assertTrue(
            minimum_safe_source_variant_strictly_dominates(
                inner_combination,
                outer_combination,
                placements,
            )
        )

    def test_same_cross_pair_does_not_revote_sequence_projection(self) -> None:
        stronger_sequence = _cluster(
            "same-cross-stronger-sequence",
            pair_count=2,
            direct_count=5,
            pair_ids=("top", "bottom", "band-a", "band-b"),
            direct_ids=("top", "bottom", "outer", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        weaker_sequence = _cluster(
            "same-cross-weaker-sequence",
            pair_count=2,
            direct_count=4,
            pair_ids=("top", "bottom", "band-a", "band-b"),
            direct_ids=("top", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        stronger_combination = _source_combination(
            "same-cross-stronger-sequence",
            stronger_sequence,
        )
        weaker_combination = _source_combination(
            "same-cross-weaker-sequence",
            weaker_sequence,
        )
        stronger_combination = replace(
            stronger_combination,
            sequence_authority=replace(
                stronger_combination.sequence_authority,
                direct_outer_boundary_count=1,
            ),
        )
        weaker_combination = replace(
            weaker_combination,
            sequence_authority=replace(
                weaker_combination.sequence_authority,
                direct_outer_boundary_count=0,
            ),
        )
        placements = _placement_map(stronger_sequence, weaker_sequence)
        placements[
            stronger_sequence.representative_placement_id
        ] = _placement(
            "same-cross-stronger-sequence",
            cross_top=FiniteInterval(1.0, 2.0),
            cross_bottom=FiniteInterval(8.0, 9.0),
            cross_top_observation_id="top:shared",
            cross_bottom_observation_id="bottom:shared",
        )
        placements[
            weaker_sequence.representative_placement_id
        ] = _placement(
            "same-cross-weaker-sequence",
            cross_top=FiniteInterval(2.0, 3.0),
            cross_bottom=FiniteInterval(7.0, 8.0),
            cross_top_observation_id="top:shared",
            cross_bottom_observation_id="bottom:shared",
        )
        clusters = {
            item.cluster_id: item
            for item in (stronger_sequence, weaker_sequence)
        }
        self.assertTrue(
            source_strictly_dominates(
                stronger_combination,
                weaker_combination,
                placements,
            )
        )

    def test_direction_consistency_joins_cross_and_sequence_evidence(self) -> None:
        direct = SimpleNamespace(
            observation_id=ObservationId("cross:direct"),
            fit_angle_interval_degrees=FiniteInterval(0.18, 0.20),
        )
        second = SimpleNamespace(
            observation_id=ObservationId("cross:second"),
            fit_angle_interval_degrees=FiniteInterval(0.16, 0.17),
        )
        placement = SimpleNamespace(
            cross=SimpleNamespace(
                evidence=(
                    SimpleNamespace(observation=direct),
                    SimpleNamespace(observation=second),
                ),
                direct_height_span_validated=False,
            ),
            sequence=SimpleNamespace(
                observations=(
                    SimpleNamespace(
                        observation_id=ObservationId("sequence:direct"),
                        fit_direction_interval_degrees=FiniteInterval(
                            0.30,
                            0.31,
                        ),
                        full_direction_interval_degrees=FiniteInterval(
                            0.29,
                            0.32,
                        ),
                    ),
                    SimpleNamespace(
                        observation_id=ObservationId("sequence:second"),
                        fit_direction_interval_degrees=FiniteInterval(
                            0.30,
                            0.31,
                        ),
                        full_direction_interval_degrees=FiniteInterval(
                            0.29,
                            0.32,
                        ),
                    ),
                ),
            ),
            lane_geometry=SimpleNamespace(
                direction=SimpleNamespace(
                    selected_observation_ids=(second.observation_id,)
                )
            ),
        )
        self.assertAlmostEqual(
            lane_direction_evidence(placement)[0],
            0.12,
        )

    def test_direction_fit_difference_cannot_create_dominance(self) -> None:
        common = {
            "pair_count": 2,
            "direct_count": 4,
            "pair_ids": ("a", "b"),
            "direct_ids": ("a", "b", "c", "d"),
        }
        consistent = _cluster(
            "consistent-direction",
            **common,
            sampling_box=Box(0, 0, 12, 12),
            direction_disagreement=0.01,
        )
        inconsistent = _cluster(
            "inconsistent-direction",
            **common,
            sampling_box=Box(0, 0, 12, 12),
            direction_disagreement=0.03,
        )
        consistent_combination = _source_combination(
            "consistent-direction", consistent
        )
        inconsistent_combination = _source_combination(
            "inconsistent-direction", inconsistent
        )
        clusters = {
            item.cluster_id: item for item in (consistent, inconsistent)
        }
        self.assertFalse(
            source_strictly_dominates(
                consistent_combination,
                inconsistent_combination,
                _placement_map(consistent, inconsistent),
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                inconsistent_combination,
                consistent_combination,
                _placement_map(consistent, inconsistent),
            )
        )

    def test_start_end_and_contact_content_are_neutral(self) -> None:
        outside_observation = _observation(Box(0, 12, 5, 16))
        outside = content_veto_assessment(
            _content_placement((_frame(10.0, 20.0),), ()),
            build_content_topology_index(outside_observation, layout="horizontal"),
        )
        contact_observation = _observation(Box(18, 12, 22, 16))
        contact = content_veto_assessment(
            _content_placement(
                (_frame(10.0, 20.0), _frame(20.0, 30.0)),
                (LocalAdvanceKind.CONTACT,),
            ),
            build_content_topology_index(contact_observation, layout="horizontal"),
        )
        overlap = content_veto_assessment(
            _content_placement(
                (_frame(10.0, 21.0), _frame(19.0, 30.0)),
                (LocalAdvanceKind.OVERLAP,),
            ),
            build_content_topology_index(contact_observation, layout="horizontal"),
        )
        self.assertFalse(outside.vetoed)
        self.assertFalse(contact.vetoed)
        self.assertFalse(overlap.vetoed)

    def test_only_slot_crop_or_normal_separator_crossing_vetoes(self) -> None:
        slot_observation = _observation(Box(12, 8, 16, 13))
        slot = content_veto_assessment(
            _content_placement((_frame(10.0, 20.0),), ()),
            build_content_topology_index(slot_observation, layout="horizontal"),
        )
        separator_observation = _observation(Box(16, 12, 24, 16))
        separator = content_veto_assessment(
            _content_placement(
                (_frame(10.0, 18.0), _frame(22.0, 30.0)),
                (LocalAdvanceKind.NOMINAL,),
            ),
            build_content_topology_index(separator_observation, layout="horizontal"),
        )
        self.assertEqual(
            {item.reason for item in slot.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )
        self.assertEqual(
            {item.reason for item in separator.facts},
            {ContentVetoReason.SEPARATOR_CORE_CONTENT_CROSSING},
        )
        self.assertTrue(
            separator_core_content_contradictions(
                build_content_topology_index(
                    separator_observation,
                    layout="horizontal",
                ),
                sequence_core=FiniteInterval(18.0, 22.0),
                cross_core=FiniteInterval(10.0, 20.0),
            )
        )

    def test_edge_intersection_at_slot_corner_is_not_content_veto(self) -> None:
        corner = content_veto_assessment(
            _content_placement((_frame(10.0, 20.0),), ()),
            build_content_topology_index(
                _observation(Box(9, 8, 11, 13)),
                layout="horizontal",
            ),
        )
        self.assertFalse(corner.vetoed)

    def test_content_one_cell_inside_corner_is_still_edge_interior(self) -> None:
        assessment = content_veto_assessment(
            _content_placement((_frame(10.0, 20.0),), ()),
            build_content_topology_index(
                _observation(Box(10, 8, 14, 13)),
                layout="horizontal",
            ),
        )
        self.assertIn(
            ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
            {item.reason for item in assessment.facts},
        )

    def test_large_component_vetoes_where_one_local_span_crosses_edge_interior(
        self,
    ) -> None:
        observation = _observation(Box(0, 8, 16, 13))
        assessment = content_veto_assessment(
            _content_placement((_frame(10.0, 20.0),), ()),
            build_content_topology_index(observation, layout="horizontal"),
        )
        self.assertIn(
            ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
            {item.reason for item in assessment.facts},
        )

    def test_content_veto_uses_the_safe_envelope_discard_edge(self) -> None:
        frame = _frame(10.0, 20.0)
        frame.top = replace(
            frame.top,
            full_position_interval_px=FiniteInterval(10.0, 12.0),
        )
        assessment = content_veto_assessment(
            _content_placement((frame,), ()),
            build_content_topology_index(
                _observation(Box(12, 8, 16, 13)),
                layout="horizontal",
            ),
        )
        self.assertEqual(
            {item.reason for item in assessment.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )

    def test_angled_boundary_projects_at_each_real_content_cell(self) -> None:
        frame = _frame(
            10.0,
            20.0,
            direction_degrees=FiniteInterval.exact(45.0),
        )
        top = outward_boundary_projection(frame.top).coordinate_interval(
            FiniteInterval(20.0, 22.0)
        )
        start = outward_boundary_projection(frame.start).coordinate_interval(
            FiniteInterval(20.0, 22.0)
        )
        self.assertEqual(top, FiniteInterval(15.0, 17.0))
        self.assertAlmostEqual(start.minimum, 3.0)
        self.assertAlmostEqual(start.maximum, 5.0)


if __name__ == "__main__":
    unittest.main()
