from __future__ import annotations

from tools.tests.photo_geometry_support import *


class FixedFormatRuntimeContractTest(unittest.TestCase):
    def test_direct_use_limit_is_closed_and_has_no_positive_epsilon(self) -> None:
        exact = DirectUseBudgetEdgeAssessment(
            role=BoundaryRole.START,
            expansion_px=180.0,
            expansion_mm=1.8,
            limit_mm=1.8,
            within_limit=True,
            worst_placement_solution_id="placement:exact",
        )
        self.assertTrue(exact.within_limit)
        over = DirectUseBudgetEdgeAssessment(
            role=BoundaryRole.START,
            expansion_px=180.000000001,
            expansion_mm=1.80000000001,
            limit_mm=1.8,
            within_limit=False,
            worst_placement_solution_id="placement:over",
        )
        self.assertFalse(over.within_limit)

    def test_matched_holder_full_count_keeps_complete_query_coverage(self) -> None:
        pixels = np.zeros((100, 720), dtype=np.uint8)
        workspace, configuration, candidate = make_candidate(pixels)
        self.assertEqual(configuration.count_request.strip_mode, "full")
        self.assertEqual(candidate.resolved_output_slots, ResolvedOutputSlots((6,)))
        lane = candidate.geometry.lane_reconstructions[0]
        tiles = tuple(
            sorted(
                lane.prepared.anchor_domain.tiles,
                key=lambda item: item.core_px.minimum,
            )
        )
        self.assertEqual(tiles[0].core_px.minimum, 0.0)
        self.assertGreaterEqual(
            tiles[-1].core_px.maximum,
            lane.prepared.anchor_domain.long_axis_extent_px,
        )
        self.assertTrue(
            all(
                left.core_px.maximum == right.core_px.minimum
                for left, right in zip(tiles, tiles[1:])
            )
        )
        self.assertTrue(
            all(
                measurement.coverage.complete
                for measurement in lane.prepared.measurement_sets
            )
        )
        self.assertIs(
            workspace.boundary_measurement_field.source_gray,
            workspace.source_gray,
        )

    def test_zero_anchor_never_invents_blank_geometry(self) -> None:
        _workspace, _configuration, candidate = make_candidate(
            np.zeros((100, 720), dtype=np.uint8)
        )
        self.assertFalse(candidate.gate.passed)
        self.assertEqual(candidate.geometry.safe_crop_envelopes, ())
        self.assertTrue(
            all(
                not lane.placement_competition.placements
                for lane in candidate.geometry.lane_reconstructions
            )
        )


if __name__ == "__main__":
    unittest.main()
