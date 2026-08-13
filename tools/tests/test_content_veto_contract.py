from __future__ import annotations

from tools.tests.chain_selection_support import *


class ContentVetoContractTest(unittest.TestCase):
    def test_displaced_cross_pair_is_not_treated_as_minimum_safe_variant(self) -> None:
        smaller = make_cluster(
            "smaller-off-center",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-a", "bottom-a"),
            direct_ids=("top-a", "bottom-a", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        larger = make_cluster(
            "larger-centered",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-b", "bottom-b"),
            direct_ids=("top-b", "bottom-b", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        smaller_combination = make_source_combination(
            "smaller-off-center",
            smaller,
        )
        larger_combination = make_source_combination(
            "larger-centered",
            larger,
        )
        placements = make_placement_map(smaller, larger)
        placements[smaller.representative_placement_id] = make_placement(
            "smaller-off-center",
            cross_top=FiniteInterval.exact(0.0),
            cross_bottom=FiniteInterval.exact(8.0),
        )
        placements[larger.representative_placement_id] = make_placement(
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
        inner_top = make_cluster(
            "inner-top-shared-bottom",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-inner", "bottom"),
            direct_ids=("top-inner", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        outer_top = make_cluster(
            "outer-top-shared-bottom",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-outer", "bottom"),
            direct_ids=("top-outer", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        inner_combination = make_source_combination(
            "inner-top-shared-bottom",
            inner_top,
            accounted_ids=("top-outer",),
        )
        outer_combination = make_source_combination(
            "outer-top-shared-bottom",
            outer_top,
        )
        placements = make_placement_map(inner_top, outer_top)
        placements[inner_top.representative_placement_id] = make_placement(
            "inner-top-shared-bottom",
            cross_top=FiniteInterval(1.4, 2.0),
            cross_bottom=FiniteInterval(8.0, 8.5),
            cross_bottom_observation_id="bottom:shared",
        )
        placements[outer_top.representative_placement_id] = make_placement(
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
        stronger_sequence = make_cluster(
            "same-cross-stronger-sequence",
            pair_count=2,
            direct_count=5,
            pair_ids=("top", "bottom", "band-a", "band-b"),
            direct_ids=("top", "bottom", "outer", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        weaker_sequence = make_cluster(
            "same-cross-weaker-sequence",
            pair_count=2,
            direct_count=4,
            pair_ids=("top", "bottom", "band-a", "band-b"),
            direct_ids=("top", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        stronger_combination = make_source_combination(
            "same-cross-stronger-sequence",
            stronger_sequence,
        )
        weaker_combination = make_source_combination(
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
        placements = make_placement_map(stronger_sequence, weaker_sequence)
        placements[
            stronger_sequence.representative_placement_id
        ] = make_placement(
            "same-cross-stronger-sequence",
            cross_top=FiniteInterval(1.0, 2.0),
            cross_bottom=FiniteInterval(8.0, 9.0),
            cross_top_observation_id="top:shared",
            cross_bottom_observation_id="bottom:shared",
        )
        placements[
            weaker_sequence.representative_placement_id
        ] = make_placement(
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
        consistent = make_cluster(
            "consistent-direction",
            **common,
            sampling_box=Box(0, 0, 12, 12),
            direction_disagreement=0.01,
        )
        inconsistent = make_cluster(
            "inconsistent-direction",
            **common,
            sampling_box=Box(0, 0, 12, 12),
            direction_disagreement=0.03,
        )
        consistent_combination = make_source_combination(
            "consistent-direction", consistent
        )
        inconsistent_combination = make_source_combination(
            "inconsistent-direction", inconsistent
        )
        clusters = {
            item.cluster_id: item for item in (consistent, inconsistent)
        }
        self.assertFalse(
            source_strictly_dominates(
                consistent_combination,
                inconsistent_combination,
                make_placement_map(consistent, inconsistent),
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                inconsistent_combination,
                consistent_combination,
                make_placement_map(consistent, inconsistent),
            )
        )

    def test_start_end_and_contact_content_are_neutral(self) -> None:
        outside_observation = make_observation(Box(0, 12, 5, 16))
        outside = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(outside_observation, layout="horizontal"),
        )
        contact_observation = make_observation(Box(18, 12, 22, 16))
        contact = content_veto_assessment(
            make_content_placement(
                (make_frame(10.0, 20.0), make_frame(20.0, 30.0)),
                (LocalAdvanceKind.CONTACT,),
            ),
            build_content_topology_index(contact_observation, layout="horizontal"),
        )
        overlap = content_veto_assessment(
            make_content_placement(
                (make_frame(10.0, 21.0), make_frame(19.0, 30.0)),
                (LocalAdvanceKind.OVERLAP,),
            ),
            build_content_topology_index(contact_observation, layout="horizontal"),
        )
        self.assertFalse(outside.vetoed)
        self.assertFalse(contact.vetoed)
        self.assertFalse(overlap.vetoed)

    def test_only_slot_crop_or_normal_separator_crossing_vetoes(self) -> None:
        slot_observation = make_observation(Box(12, 8, 16, 13))
        slot = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(slot_observation, layout="horizontal"),
        )
        separator_observation = make_observation(Box(16, 12, 24, 16))
        separator = content_veto_assessment(
            make_content_placement(
                (make_frame(10.0, 18.0), make_frame(22.0, 30.0)),
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
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(
                make_observation(Box(9, 8, 11, 13)),
                layout="horizontal",
            ),
        )
        self.assertFalse(corner.vetoed)

    def test_content_one_cell_inside_corner_is_still_edge_interior(self) -> None:
        assessment = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(
                make_observation(Box(10, 8, 14, 13)),
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
        observation = make_observation(Box(0, 8, 16, 13))
        assessment = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(observation, layout="horizontal"),
        )
        self.assertIn(
            ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
            {item.reason for item in assessment.facts},
        )

    def test_content_veto_uses_the_safe_envelope_discard_edge(self) -> None:
        frame = make_frame(10.0, 20.0)
        frame.top = replace(
            frame.top,
            full_position_interval_px=FiniteInterval(10.0, 12.0),
        )
        assessment = content_veto_assessment(
            make_content_placement((frame,), ()),
            build_content_topology_index(
                make_observation(Box(12, 8, 16, 13)),
                layout="horizontal",
            ),
        )
        self.assertEqual(
            {item.reason for item in assessment.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )

    def test_angled_boundary_projects_at_each_real_content_cell(self) -> None:
        frame = make_frame(
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
