from __future__ import annotations

from tools.tests.chain_selection_support import *


class CrossDominanceContractTest(unittest.TestCase):
    def test_sampling_cluster_requires_exact_boxes_and_common_intervals(
        self,
    ) -> None:
        first = make_chain(
            "first",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(1.0, 2.0),
        )
        equivalent = make_chain(
            "equivalent",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(1.5, 2.5),
        )
        displaced = make_chain(
            "displaced",
            box=Box(1, 0, 11, 10),
            interval=FiniteInterval(1.5, 2.5),
        )
        disjoint = make_chain(
            "disjoint",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(3.0, 4.0),
        )
        placements = {
            item.placement_id: make_placement(item.placement_id.split(":", 1)[1])
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
        authority = make_cluster(
            "authority",
            pair_count=2,
            direct_count=4,
            pair_ids=("a", "b", "c"),
            direct_ids=("a", "b", "c", "d"),
        )
        explained = make_cluster(
            "explained",
            pair_count=1,
            direct_count=3,
            pair_ids=("a", "b"),
            direct_ids=("a", "b", "d"),
        )
        unexplained = make_cluster(
            "unexplained",
            pair_count=1,
            direct_count=3,
            pair_ids=("a", "x"),
            direct_ids=("a", "x", "d"),
        )
        authority_combination = make_source_combination("authority", authority)
        explained_combination = make_source_combination("explained", explained)
        unexplained_combination = make_source_combination(
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
                make_placement_map(authority, explained, unexplained),
            )
        )
        self.assertFalse(
            source_strictly_dominates(
                authority_combination,
                unexplained_combination,
                make_placement_map(authority, explained, unexplained),
            )
        )

    def test_complete_separator_band_precedes_explained_isolated_edge(self) -> None:
        band_chain = make_cluster(
            "separator-band",
            pair_count=2,
            direct_count=3,
            pair_ids=("top", "bottom", "band"),
            direct_ids=("top", "bottom", "band"),
            separator_band_count=1,
        )
        isolated_edge_chain = make_cluster(
            "isolated-edge",
            pair_count=2,
            direct_count=4,
            pair_ids=("top", "bottom"),
            direct_ids=("top", "bottom", "edge-a", "edge-b"),
            separator_band_count=0,
        )
        band_combination = make_source_combination(
            "separator-band",
            band_chain,
            accounted_ids=("edge-a", "edge-b"),
        )
        isolated_combination = make_source_combination(
            "isolated-edge",
            isolated_edge_chain,
        )
        clusters = {
            item.cluster_id: item
            for item in (band_chain, isolated_edge_chain)
        }
        placements = make_placement_map(band_chain, isolated_edge_chain)
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
        cross_pair = make_cluster(
            "cross-pair",
            pair_count=1,
            direct_count=4,
            pair_ids=("top", "bottom"),
            direct_ids=("top", "bottom", "edge-a", "edge-b"),
            separator_band_count=0,
            cross_axis_pair_supported=True,
        )
        separator_chain = make_cluster(
            "separator-chain",
            pair_count=2,
            direct_count=4,
            pair_ids=("band-a", "band-b"),
            direct_ids=("cross", "outer", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=False,
        )
        cross_combination = make_source_combination(
            "cross-pair",
            cross_pair,
            accounted_ids=separator_chain.direct_observation_ids,
        )
        separator_combination = make_source_combination(
            "separator-chain",
            separator_chain,
            accounted_ids=cross_pair.direct_observation_ids,
        )
        clusters = {
            item.cluster_id: item for item in (cross_pair, separator_chain)
        }
        placements = make_placement_map(cross_pair, separator_chain)
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
        paired = make_cluster(
            "paired-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("top", "bottom", "band-a", "band-b"),
            direct_ids=("top", "bottom", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=True,
        )
        isolated = make_cluster(
            "isolated-cross",
            pair_count=2,
            direct_count=5,
            pair_ids=("edge", "band-a", "band-b"),
            direct_ids=("top", "edge", "outer", "band-a", "band-b"),
            separator_band_count=2,
            cross_axis_pair_supported=False,
        )
        paired_combination = make_source_combination(
            "paired-cross",
            paired,
            accounted_ids=isolated.direct_observation_ids,
        )
        isolated_combination = make_source_combination(
            "isolated-cross",
            isolated,
            accounted_ids=paired.direct_observation_ids,
        )
        clusters = {item.cluster_id: item for item in (paired, isolated)}
        placements = make_placement_map(paired, isolated)
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
        stronger = make_cluster(
            "stronger-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("a", "b"),
            direct_ids=("a", "b", "c", "d"),
            cross_axis_support_regions=6,
        )
        weaker = make_cluster(
            "weaker-cross",
            pair_count=2,
            direct_count=4,
            pair_ids=("a", "b"),
            direct_ids=("a", "b", "c", "d"),
            cross_axis_support_regions=4,
        )
        stronger_combination = make_source_combination("stronger-cross", stronger)
        weaker_combination = make_source_combination("weaker-cross", weaker)
        clusters = {
            item.cluster_id: item for item in (stronger, weaker)
        }
        self.assertTrue(
            source_strictly_dominates(
                stronger_combination,
                weaker_combination,
                make_placement_map(stronger, weaker),
            )
        )

    def test_cross_measurement_uses_fit_quality_not_pixel_quantity_or_interval_width(
        self,
    ) -> None:
        precise = make_placement(
            "precise-cross-measurement",
            cross_top=FiniteInterval(1.0, 2.0),
        )
        noisy = make_placement(
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
        consistent = make_placement(
            "role-consistent-cross",
            residual=2.0,
            top_role_consistency=0.8,
            bottom_role_consistency=1.0,
        )
        ambiguous = make_placement(
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
        common_direction = make_placement(
            "common-direction-cross",
            residual=2.0,
            top_role_consistency=0.6,
            bottom_role_consistency=0.6,
            top_fit_direction=FiniteInterval(0.10, 0.20),
            bottom_fit_direction=FiniteInterval(0.15, 0.25),
        )
        displaced_direction = make_placement(
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
        stronger_top = make_placement(
            "stronger-top-cross",
            residual=0.25,
            top_role_consistency=0.9,
            bottom_role_consistency=0.7,
        )
        stronger_bottom = make_placement(
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


if __name__ == "__main__":
    unittest.main()
