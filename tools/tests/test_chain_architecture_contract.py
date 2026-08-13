from __future__ import annotations

from tools.tests.physical_chain_support import *


class ChainArchitectureContractTest(unittest.TestCase):
    def test_exception_proposals_are_not_hidden_by_normal_candidates(self) -> None:
        source = inspect.getsource(materialize_source_placements)
        self.assertNotIn("and layer", source)
        self.assertNotIn("break", source)

    def test_local_separator_angle_is_not_a_second_direction_gate(self) -> None:
        source = inspect.getsource(complete_chain_record)
        self.assertNotIn("joint_direction_compatibility", source)

    def test_safe_crop_envelope_is_built_only_after_source_selection(self) -> None:
        orchestration = inspect.getsource(reconstruct_photo_geometry)
        self.assertGreater(
            orchestration.index("resolve_selected_source_output"),
            orchestration.index("build_lane_candidate_reconstructions"),
        )
        source = inspect.getsource(resolve_selected_source_output)
        self.assertGreater(
            source.index("safe_crop_envelope_from_placement"),
            source.index("select_source_placement_clusters"),
        )
        self.assertNotIn("candidate_envelopes", source)
        self.assertNotIn("materialize_complete_chain", source)
        self.assertNotIn("chain_sampling_geometry", source)
        self.assertNotIn("complete_chain_record", source)
        self.assertIn("selected_chain_physical_signature", source)
        self.assertLess(
            orchestration.index("bind_shared_source_geometry_before_selection"),
            orchestration.index("build_lane_candidate_reconstructions"),
        )

    def test_complete_separator_chain_is_a_physical_directed_path(self) -> None:
        fit_positions: dict[str, FiniteInterval] = {}

        def band(
            name: str,
            left_position: float,
            relation_ordinal: int,
        ) -> SeparatorBandRoleProposal:
            observation_id = ObservationId(f"band:{name}")
            left_run = f"run:{name}:left"
            right_run = f"run:{name}:right"
            fit_positions[left_run] = FiniteInterval.exact(left_position)
            fit_positions[right_run] = FiniteInterval.exact(
                left_position + 10.0
            )
            left_role = OrdinalBoundaryRole(
                relation_ordinal * 2 - 1,
                relation_ordinal,
                BoundaryRole.END,
            )
            right_role = OrdinalBoundaryRole(
                relation_ordinal * 2,
                relation_ordinal + 1,
                BoundaryRole.START,
            )
            return SeparatorBandRoleProposal(
                proposal_id=f"proposal:{name}:{relation_ordinal}",
                band_observation_id=observation_id,
                relation_ordinal=relation_ordinal,
                phase_interval_px=FiniteInterval(-1000.0, 1000.0),
                gap_interval_px=FiniteInterval.exact(10.0),
                left_role_proposal=SequenceRoleProposal(
                    proposal_id=f"role:{name}:{relation_ordinal}:left",
                    run_id=left_run,
                    role=left_role,
                    phase_interval_px=FiniteInterval(-1000.0, 1000.0),
                    transition_ids=(ObservationId(f"transition:{name}:left"),),
                    role_coordinate_px=0.0,
                    separator_band_observation_id=observation_id,
                ),
                right_role_proposal=SequenceRoleProposal(
                    proposal_id=f"role:{name}:{relation_ordinal}:right",
                    run_id=right_run,
                    role=right_role,
                    phase_interval_px=FiniteInterval(-1000.0, 1000.0),
                    transition_ids=(ObservationId(f"transition:{name}:right"),),
                    role_coordinate_px=0.0,
                    separator_band_observation_id=observation_id,
                ),
            )

        proposals = tuple(
            band(name, position, ordinal)
            for name, position in (
                ("first", 100.0),
                ("internal-distractor", 150.0),
                ("second", 210.0),
            )
            for ordinal in (1, 2)
        )
        groups = direct_separator_groups(
            proposals,
            relation_count=2,
            width_interval_px=FiniteInterval.exact(100.0),
            canonical_width_px=100.0,
            fit_position_by_run=fit_positions,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(
            tuple(
                str(item.band_observation_id)
                for item in groups[0].separator_band_proposals
            ),
            ("band:first", "band:second"),
        )
        self.assertEqual(
            tuple(
                item.relation_ordinal
                for item in groups[0].separator_band_proposals
            ),
            (1, 2),
        )

    def test_lane_edge_family_need_not_touch_two_different_slots(self) -> None:
        source = inspect.getsource(materialize_cross_placement)
        self.assertNotIn("supported_frame_count", source)
        self.assertNotIn("local cross line cannot own", source)

    def test_contact_overlap_and_large_gap_have_no_fixed_gap_window(self) -> None:
        geometry = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        gap_model = LaneGapModel.from_ordinal_edges(
            geometry.width_state,
            lane_id="lane:test",
            edge_families=(),
            direct_separator_gaps=(),
        )
        contact = local_advance_delta_from_observed_gap(
            FiniteInterval.exact(0.0), geometry, gap_model
        )
        overlap = local_advance_delta_from_observed_gap(
            FiniteInterval.exact(-20.0), geometry, gap_model
        )
        wide = local_advance_delta_from_observed_gap(
            FiniteInterval.exact(200.0), geometry, gap_model
        )
        self.assertIsNotNone(contact)
        self.assertIsNotNone(overlap)
        self.assertIsNotNone(wide)

    def test_complete_chain_materializer_has_no_first_n_truncation(self) -> None:
        source = inspect.getsource(materialize_lane_placements)
        self.assertNotIn("top", source.lower())
        self.assertNotIn("[:MAX_", source)

    def test_empty_phase_input_creates_no_evidence(self) -> None:
        groups, work = build_sequence_groups((), ())
        self.assertEqual(groups, ())
        self.assertEqual(work.ordinal_role_lookup_count, 0)
        self.assertEqual(work.ordinal_role_match_count, 0)

    def test_local_advance_authority_is_a_hard_chain_fact(self) -> None:
        source = inspect.getsource(placement_local_advance_authorized)
        self.assertIn("lane_gap_model.state == EvidenceState.SUPPORTED", source)
        self.assertIn("observed_roles", source)


if __name__ == "__main__":
    unittest.main()
