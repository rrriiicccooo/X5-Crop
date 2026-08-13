from __future__ import annotations

from tools.tests.chain_selection_support import *


class PlacementDominanceContractTest(unittest.TestCase):
    def test_distinct_direct_cross_pairs_are_not_minimum_safe_variants(
        self,
    ) -> None:
        first = make_placement(
            "first-direct-pair",
            cross_top=FiniteInterval(1.0, 2.0),
            cross_bottom=FiniteInterval(8.0, 9.0),
        )
        second = make_placement(
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
        smaller = make_cluster(
            "smaller-safe-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-a", "bottom"),
            direct_ids=("top-a", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        larger = make_cluster(
            "larger-safe-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-b", "bottom"),
            direct_ids=("top-b", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        smaller_combination = make_source_combination(
            "smaller-safe-cross",
            smaller,
            accounted_ids=("top-b",),
        )
        larger_combination = make_source_combination(
            "larger-safe-cross",
            larger,
            accounted_ids=("top-a",),
        )
        placements = make_placement_map(smaller, larger)
        placements[smaller.representative_placement_id] = make_placement(
            "smaller-safe-cross",
            cross_top=FiniteInterval(1.25, 2.0),
            cross_bottom=FiniteInterval(8.0, 8.75),
            cross_bottom_observation_id="bottom:shared",
        )
        placements[larger.representative_placement_id] = make_placement(
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
        inner = make_cluster(
            "inner-safe-cross",
            pair_count=1,
            direct_count=3,
            pair_ids=("bottom",),
            direct_ids=("bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=False,
            cross_axis_support_regions=3,
        )
        outer = make_cluster(
            "outer-safe-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-outer", "bottom"),
            direct_ids=("top-outer", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        inner_combination = make_source_combination("inner-safe-cross", inner)
        outer_combination = make_source_combination("outer-safe-cross", outer)
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
        placements = make_placement_map(inner, outer)
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
        left = make_placement(
            "shared-cross-left",
            cross_top=FiniteInterval.exact(1.0),
            cross_bottom=FiniteInterval.exact(9.0),
            cross_top_observation_id="shared-top",
            cross_bottom_observation_id="shared-bottom",
        )
        right = make_placement(
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
        inner = make_placement(
            "inner-inferred-top",
            cross_top=FiniteInterval(1.4, 2.0),
            cross_bottom=FiniteInterval(8.0, 8.5),
            cross_bottom_observation_id="bottom:shared",
        )
        outer = make_placement(
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
        smaller = make_placement("smaller-separator")
        larger = make_placement("larger-separator")

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
        inner = make_placement("inner-last-end")
        outer = make_placement("outer-last-end")
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
        smaller = make_cluster(
            "smaller-disjoint-scale",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-a", "bottom-a"),
            direct_ids=("top-a", "bottom-a", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=4,
        )
        larger = make_cluster(
            "larger-supported-scale",
            pair_count=2,
            direct_count=4,
            pair_ids=("top-b", "bottom-b"),
            direct_ids=("top-b", "bottom-b", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_support_regions=5,
        )
        smaller_combination = make_source_combination(
            "smaller-disjoint-scale",
            smaller,
            accounted_ids=("top-b", "bottom-b"),
        )
        larger_combination = make_source_combination(
            "larger-supported-scale",
            larger,
        )
        placements = make_placement_map(smaller, larger)
        placements[smaller.representative_placement_id] = make_placement(
            "smaller-disjoint-scale",
            cross_top=FiniteInterval(2.0, 2.5),
            cross_bottom=FiniteInterval(8.0, 8.5),
        )
        placements[larger.representative_placement_id] = make_placement(
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


if __name__ == "__main__":
    unittest.main()
