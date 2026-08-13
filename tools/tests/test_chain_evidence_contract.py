from __future__ import annotations

from tools.tests.chain_selection_support import *


class ChainEvidenceContractTest(unittest.TestCase):
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
                frames=(make_frame(100.0, 200.0), make_frame(230.0, 330.0))
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

        compatible = make_cluster(
            "compatible",
            pair_count=1,
            direct_count=1,
            pair_ids=("a",),
            direct_ids=("a",),
        )
        incompatible = make_cluster(
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

    def test_safe_envelope_and_budget_accept_one_selectedplacement(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
