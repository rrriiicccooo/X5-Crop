from __future__ import annotations

from tools.tests.physical_chain_support import *


class FilledLayoutContractTest(unittest.TestCase):
    def test_equal_count_partial_does_not_gain_filled_holder_authority(
        self,
    ) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(20.0), ObservationId("gap-a")),
                (FiniteInterval.exact(20.0), ObservationId("gap-b")),
            ),
        )
        relations = tuple(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=LocalAdvanceKind.NOMINAL,
                delta_interval_px=FiniteInterval.exact(0.0),
                canonical_delta_px=0.0,
                observation_ids=(),
            )
            for ordinal in (1, 2)
        )
        common = dict(
            output_slot_count=3,
            measurement_slot_count=3,
            width_authority_px=FiniteInterval(0.0, 1120.0),
            holder_extent_tolerance_ratio=0.035,
        )
        full = long_axis_fill_authority(
            SimpleNamespace(
                **common,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
            ),
            geometry,
            gap_model,
            relations,
        )
        partial = long_axis_fill_authority(
            SimpleNamespace(
                **common,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_NONFILLING_LAYOUT
                ),
            ),
            geometry,
            gap_model,
            relations,
        )
        self.assertEqual(full.state, EvidenceState.SUPPORTED)
        self.assertEqual(partial.state, EvidenceState.UNAVAILABLE)

    def test_filled_layout_does_not_require_frames_to_equal_canvas_extent(
        self,
    ) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(56.0, 56.0, None),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(40.0), ObservationId("gap-a")),
                (FiniteInterval.exact(40.0), ObservationId("gap-b")),
            ),
        )
        relations = tuple(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=LocalAdvanceKind.NOMINAL,
                delta_interval_px=FiniteInterval.exact(0.0),
                canonical_delta_px=0.0,
                observation_ids=(),
            )
            for ordinal in (1, 2)
        )
        authority = long_axis_fill_authority(
            SimpleNamespace(
                output_slot_count=3,
                measurement_slot_count=3,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
                width_authority_px=FiniteInterval(0.0, 2260.0),
                holder_extent_tolerance_ratio=0.035,
            ),
            geometry,
            gap_model,
            relations,
        )
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        assert authority.chain_span_interval_px is not None
        self.assertLess(authority.chain_span_interval_px.maximum, 2260.0)

    def test_filled_layout_cannot_infer_an_unresolved_gap(self) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(56.0, 56.0, None),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(40.0), ObservationId("gap-a")),
            ),
        )
        authority = long_axis_fill_authority(
            SimpleNamespace(
                output_slot_count=3,
                measurement_slot_count=3,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
                width_authority_px=FiniteInterval(0.0, 2260.0),
                holder_extent_tolerance_ratio=0.035,
            ),
            geometry,
            gap_model,
            (
                LocalAdvanceRelation(
                    relation_ordinal=1,
                    kind=LocalAdvanceKind.OBSERVED_NORMAL,
                    delta_interval_px=FiniteInterval.exact(40.0),
                    canonical_delta_px=40.0,
                    observation_ids=(ObservationId("gap-a"),),
                ),
                LocalAdvanceRelation(
                    relation_ordinal=2,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                ),
            ),
        )
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)

    def test_filled_count_two_can_center_one_direct_normal_gap(self) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(70.0, 56.0, None),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval.exact(45.0), ObservationId("gap-a")),
            ),
        )
        authority = long_axis_fill_authority(
            SimpleNamespace(
                output_slot_count=2,
                measurement_slot_count=2,
                holder_layout_authority=(
                    HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                ),
                width_authority_px=FiniteInterval(0.0, 1885.0),
                holder_extent_tolerance_ratio=0.035,
            ),
            geometry,
            gap_model,
            (
                LocalAdvanceRelation(
                    relation_ordinal=1,
                    kind=LocalAdvanceKind.OBSERVED_NORMAL,
                    delta_interval_px=FiniteInterval.exact(45.0),
                    canonical_delta_px=45.0,
                    observation_ids=(ObservationId("gap-a"),),
                ),
            ),
        )
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(gap_model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(gap_model.placement_pitch_interval_px)

    def test_repeated_contact_or_overlap_cannot_become_normal_gap(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=((
                make_edge(1, 0.0, "a"),
                make_edge(2, 350.0, "b"),
                make_edge(3, 700.0, "c"),
            ),),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)
        self.assertEqual(
            model.unresolved_gap_proposals_px,
            (FiniteInterval.exact(-10.0), FiniteInterval.exact(-10.0)),
        )


if __name__ == "__main__":
    unittest.main()
