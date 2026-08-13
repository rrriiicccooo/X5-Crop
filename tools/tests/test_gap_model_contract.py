from __future__ import annotations

from tools.tests.physical_chain_support import *


class GapModelContractTest(unittest.TestCase):
    def test_format_gap_prior_never_changes_role_or_phase_coordinates(self) -> None:
        role = OrdinalBoundaryRole(4, 3, BoundaryRole.START)
        width_state = make_width_state()
        with_prior = FramePhysicalSpec(36.0, 24.0, 2.0)
        without_prior = FramePhysicalSpec(36.0, 24.0, None)

        self.assertEqual(
            role_relative_projection(role, with_prior, width_state),
            FiniteInterval.exact(720.0),
        )
        self.assertEqual(
            role_relative_projection(role, with_prior, width_state),
            role_relative_projection(role, without_prior, width_state),
        )
        self.assertEqual(
            role_canonical_relative(role, with_prior, width_state),
            role_canonical_relative(role, without_prior, width_state),
        )

    def test_profile_run_without_edge_observation_cannot_create_phase(self) -> None:
        run = ProfileRun(
            run_id="ambiguous-run",
            coordinate_interval_px=FiniteInterval.exact(100.0),
            transition_ids=(ObservationId("transition:ambiguous"),),
            trace_coordinates_px=(0, 50, 100),
            role_hint=None,
            qualified_anchor_roles=(BoundaryRole.START,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=10.0,
            pair_qualified=True,
        )
        lane = SimpleNamespace(
            sequence_profile=BasicAxisProfile(
                "sequence",
                1000,
                (0, 50, 100),
                (run,),
            ),
            sequence_edges=(),
            separator_bands=(),
        )
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        proposals = build_sequence_role_proposals(
            lane,
            geometry,
            (
                OrdinalBoundaryRole(0, 1, BoundaryRole.START),
                OrdinalBoundaryRole(1, 1, BoundaryRole.END),
            ),
            discovery_kind=SequenceDiscoveryKind.DIRECT_EXCEPTION,
        )

        self.assertEqual(proposals, ())

    def test_separated_segments_may_prove_one_common_physical_line(self) -> None:
        pairs = disjoint_family_pairs(
            (
                FiniteInterval(0.0, 20.0),
                FiniteInterval(40.0, 60.0),
                FiniteInterval(80.0, 100.0),
            ),
        )
        self.assertEqual(pairs, ((0, 1), (0, 2), (1, 2)))

    def test_conflicting_anomaly_kinds_remain_unclassified(self) -> None:
        left = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.WIDE,
            delta_interval_px=FiniteInterval(-1.0, 2.0),
            canonical_delta_px=0.5,
            observation_ids=(ObservationId("wide"),),
        )
        right = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.NARROW,
            delta_interval_px=FiniteInterval(-2.0, 1.0),
            canonical_delta_px=-0.5,
            observation_ids=(ObservationId("narrow"),),
        )

        merged = merge_local_advance_relations((left,), (right,))[0]

        self.assertEqual(merged.kind, LocalAdvanceKind.OBSERVED_UNCLASSIFIED)
        self.assertEqual(merged.delta_interval_px, FiniteInterval(-1.0, 1.0))

    def test_fixed_frame_tolerances_are_source_shared(self) -> None:
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio,
            0.0125,
        )
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_height_tolerance_ratio,
            0.0040,
        )
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(9.9, 10.1),
            height_scale_px_per_mm=PositiveInterval(9.9, 10.1),
        )
        self.assertEqual(geometry.frame_spec.frame_spec_id.split(":", 1)[0], "frame-spec")
        self.assertFalse(hasattr(geometry, "lane_id"))

    def test_dual_lane_scale_evidence_intersects_at_source_level(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        first = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(9.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(9.0, 10.0),
        )
        second = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(9.5, 10.5),
            height_scale_px_per_mm=PositiveInterval(9.25, 10.25),
        )
        shared = first.intersect_source_state(second)
        self.assertEqual(
            shared.width_state.feasible_scale_interval(),
            PositiveInterval(9.5, 10.0),
        )
        self.assertEqual(
            shared.height_state.feasible_scale_interval(),
            PositiveInterval(9.5, 10.0),
        )
        self.assertFalse(hasattr(shared, "lane_id"))

    def test_observed_width_does_not_recalibrate_source_height(self) -> None:
        frame = FramePhysicalSpec(70.0, 56.0, None)
        geometry = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(64.0, 69.0),
            height_scale_px_per_mm=PositiveInterval(64.0, 69.0),
        )
        original_height = geometry.height_state.extent_projection_px()
        narrowed_width = geometry.width_state.intersect_observed_extent(
            FiniteInterval(4520.0, 4560.0),
            observation_ids=(ObservationId("observed-width"),),
        )

        refined = SourceScanGeometry.from_axis_states(
            frame,
            narrowed_width,
            geometry.height_state,
        )

        self.assertEqual(
            refined.height_state.extent_projection_px(),
            original_height,
        )
        self.assertNotEqual(
            refined.width_state.extent_projection_px(),
            geometry.width_state.extent_projection_px(),
        )

    def test_gap_requires_two_compatible_pitch_segments(self) -> None:
        zero = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=(),
            direct_separator_gaps=(),
        )
        one = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=((make_edge(1, 0.0, "a"), make_edge(2, 380.0, "b")),),
            direct_separator_gaps=(),
        )
        two = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=((
                make_edge(1, 0.0, "a"),
                make_edge(2, 380.0, "b"),
                make_edge(3, 760.0, "c"),
            ),),
            direct_separator_gaps=(),
        )
        self.assertIsNone(zero.gap_interval_px)
        self.assertIsNone(zero.placement_pitch_interval_px)
        self.assertIsNone(zero.canonical_placement_pitch_px)
        self.assertEqual(one.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(one.gap_interval_px, FiniteInterval.exact(20.0))
        self.assertIsNone(one.placement_pitch_interval_px)
        self.assertEqual(two.state, EvidenceState.SUPPORTED)
        self.assertEqual(two.gap_interval_px, FiniteInterval.exact(20.0))
        self.assertEqual(
            two.placement_pitch_interval_px,
            FiniteInterval.exact(380.0),
        )

    def test_conflicting_pitch_segments_remain_unresolved(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=((
                make_edge(1, 0.0, "a"),
                make_edge(2, 380.0, "b"),
                make_edge(3, 800.0, "c"),
            ),),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)

    def test_unique_repeated_normal_gaps_leave_direct_outlier_local(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval(18.0, 22.0), ObservationId("normal-a")),
                (FiniteInterval(19.0, 23.0), ObservationId("normal-b")),
                (FiniteInterval(17.0, 21.0), ObservationId("normal-c")),
                (FiniteInterval(-2.0, 2.0), ObservationId("contact")),
            ),
        )
        self.assertEqual(model.state, EvidenceState.SUPPORTED)
        self.assertEqual(model.gap_interval_px, FiniteInterval(19.0, 21.0))
        self.assertEqual(
            model.unresolved_gap_proposals_px,
            (FiniteInterval(-2.0, 2.0),),
        )
        self.assertEqual(
            model.unresolved_observation_ids,
            (ObservationId("contact"),),
        )

    def test_equal_repeated_gap_explanations_remain_unresolved(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=(),
            direct_separator_gaps=(
                (FiniteInterval(18.0, 22.0), ObservationId("normal-a")),
                (FiniteInterval(19.0, 23.0), ObservationId("normal-b")),
                (FiniteInterval(48.0, 52.0), ObservationId("wide-a")),
                (FiniteInterval(49.0, 53.0), ObservationId("wide-b")),
            ),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)

    def test_single_pitch_from_two_role_families_cannot_establish_gap(
        self,
    ) -> None:
        model = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=(
                (make_edge(1, 0.0, "start-a"), make_edge(2, 380.0, "start-b")),
                (make_edge(1, 360.0, "end-a"), make_edge(2, 740.0, "end-b")),
            ),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(model.gap_interval_px)
        self.assertEqual(len(model.direct_gap_proposals_px), 2)

    def test_120_one_pitch_does_not_borrow_a_format_prior(self) -> None:
        model = LaneGapModel.from_ordinal_edges(
            make_width_state(),
            lane_id="lane:0",
            edge_families=((make_edge(1, 0.0, "a"), make_edge(2, 380.0, "b")),),
            direct_separator_gaps=(),
        )
        self.assertEqual(model.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(len(model.direct_gap_proposals_px), 1)
        self.assertIsNone(model.placement_pitch_interval_px)
        self.assertIsNone(model.canonical_placement_pitch_px)


if __name__ == "__main__":
    unittest.main()
