from __future__ import annotations

import unittest

from tools.tests.physical_gate_support import separator_observation
from x5crop.detection.candidate.proposal.outer import separator_sequence_rank
from x5crop.detection.physical.photo_size import (
    photo_size_consistency_from_gap_edges,
    photo_size_consistency_from_separator_bands,
)
from x5crop.geometry.separator_band import SeparatorBand
from x5crop.policies.parameters.outer import SeparatorOuterBandParameters


class PhotoSizePhysicalModelTests(unittest.TestCase):
    def test_separator_width_variation_does_not_make_photo_size_unstable(self) -> None:
        result = photo_size_consistency_from_gap_edges(
            [
                separator_observation(1, 110.0, start=100.0, end=120.0),
                separator_observation(2, 235.0, start=220.0, end=250.0),
            ],
            origin=0.0,
            pitch=350.0 / 3.0,
            count=3,
            target_photo_width=100.0,
        )
        self.assertTrue(result.used)
        self.assertEqual(result.photo_widths, (100.0, 100.0, 100.0))
        self.assertEqual(result.photo_width_cv, 0.0)
        self.assertGreater(result.separator_width_cv or 0.0, 0.0)

    def test_sequence_rank_prefers_photo_width_consistency(self) -> None:
        stable = photo_size_consistency_from_separator_bands(
            [
                SeparatorBand(100, 120, 110, 20, 0.8),
                SeparatorBand(220, 250, 235, 30, 0.8),
                SeparatorBand(350, 360, 355, 10, 0.8),
            ],
            target_photo_width=100.0,
        )
        unstable = photo_size_consistency_from_separator_bands(
            [
                SeparatorBand(100, 120, 110, 20, 0.8),
                SeparatorBand(190, 210, 200, 20, 0.8),
                SeparatorBand(340, 360, 350, 20, 0.8),
            ],
            target_photo_width=100.0,
        )
        parameters = SeparatorOuterBandParameters()
        self.assertLess(
            separator_sequence_rank(
                stable,
                0.0,
                0.8,
                parameters.sequence_pair_score_weight,
                parameters.photo_width_cv_rank_weight,
            ),
            separator_sequence_rank(
                unstable,
                0.0,
                0.8,
                parameters.sequence_pair_score_weight,
                parameters.photo_width_cv_rank_weight,
            ),
        )

    def test_incomplete_edges_are_unavailable_not_equal_pitch_proof(self) -> None:
        result = photo_size_consistency_from_gap_edges(
            [separator_observation(1, 100.0, method="equal")],
            0.0,
            120.0,
            2,
            target_photo_width=96.0,
        )
        self.assertFalse(result.used)
        self.assertEqual(
            result.reason,
            "insufficient_edge_bounded_photo_measurements",
        )

    def test_model_edges_are_not_photo_dimension_measurements(self) -> None:
        result = photo_size_consistency_from_gap_edges(
            [
                separator_observation(
                    1,
                    100.0,
                    method="equal",
                    start=95.0,
                    end=105.0,
                )
            ],
            0.0,
            200.0,
            2,
            target_photo_width=95.0,
        )

        self.assertFalse(result.used)
        self.assertEqual(
            result.reason,
            "insufficient_edge_bounded_photo_measurements",
        )


if __name__ == "__main__":
    unittest.main()
