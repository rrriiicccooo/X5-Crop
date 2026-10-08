from __future__ import annotations

from tools.tests.photo_geometry_support import *


class FixedFormatRuntimeContractTest(unittest.TestCase):
    def test_fixed_output_coverage_limit_only_absorbs_float_roundoff(self) -> None:
        exact = DirectUseBudgetEdgeAssessment(BoundaryRole.START, 180.0, 180.0, True)
        self.assertTrue(exact.within_limit)
        over = DirectUseBudgetEdgeAssessment(BoundaryRole.START, 180.000001, 180.0, False)
        self.assertFalse(over.within_limit)

    def test_matched_holder_default_count_keeps_complete_query_coverage(self) -> None:
        pixels = np.zeros((100, 720), dtype=np.uint8)
        workspace, configuration, candidate = make_candidate(pixels)
        self.assertIsNone(configuration.count_request.user_count)
        self.assertEqual(
            configuration.count_request.authority.value,
            "matched_holder_default_count",
        )
        self.assertEqual(candidate.resolved_output_slots, ResolvedOutputSlots((6,)))
        lane = candidate.geometry.lane_reconstructions[0]
        windows = tuple(
            sorted(
                lane.prepared.anchor_domain.windows,
                key=lambda item: item.core_px.minimum,
            )
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].window_id, "anchor-window:lane:0:conservative")
        self.assertEqual(windows[0].core_px.minimum, 0.0)
        self.assertGreaterEqual(
            windows[0].core_px.maximum,
            lane.prepared.anchor_domain.long_axis_extent_px,
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
        self.assertEqual(candidate.geometry.output_footprints, ())
        self.assertTrue(
            all(
                not lane.placement_competition.placements
                for lane in candidate.geometry.lane_reconstructions
            )
        )


if __name__ == "__main__":
    unittest.main()
