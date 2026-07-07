from __future__ import annotations

import unittest

from x5crop.domain import Gap
from x5crop.detection.physical.photo_size import (
    photo_size_consistency_from_gap_edges,
    photo_size_consistency_from_separator_bands,
)
from x5crop.geometry.separator_band import SeparatorBand
from x5crop.geometry.separator_width_profile import (
    separator_width_relation_to_theory,
    theoretical_separator_width,
)


class PhotoSizePhysicalModelTests(unittest.TestCase):
    def test_separator_width_variation_does_not_make_photo_size_unstable(self) -> None:
        gaps = [
            Gap(1, 105.0, 1.0, "detected", 100.0, 110.0),
            Gap(2, 245.0, 1.0, "detected", 210.0, 280.0),
            Gap(3, 390.0, 1.0, "detected", 380.0, 400.0),
        ]

        detail = photo_size_consistency_from_gap_edges(
            gaps,
            origin=0.0,
            pitch=125.0,
            count=4,
            target_photo_width=100.0,
        ).detail()

        self.assertTrue(detail["used"])
        self.assertEqual(detail["photo_widths"], [100.0, 100.0, 100.0, 100.0])
        self.assertAlmostEqual(detail["photo_width_cv"], 0.0)
        self.assertGreater(detail["separator_width_cv"], 0.70)
        self.assertEqual(detail["separator_width_role"], "observed_detail_not_stability_penalty")

    def test_band_sequence_rank_penalty_prefers_photo_width_consistency(self) -> None:
        variable_separator_stable_photo = [
            SeparatorBand(100.0, 110.0, 105.0, 10.0, 0.8),
            SeparatorBand(210.0, 280.0, 245.0, 70.0, 0.8),
            SeparatorBand(380.0, 400.0, 390.0, 20.0, 0.8),
        ]
        stable_separator_unstable_photo = [
            SeparatorBand(100.0, 120.0, 110.0, 20.0, 0.8),
            SeparatorBand(200.0, 220.0, 210.0, 20.0, 0.8),
            SeparatorBand(340.0, 360.0, 350.0, 20.0, 0.8),
        ]

        stable_photo = photo_size_consistency_from_separator_bands(
            variable_separator_stable_photo,
            target_photo_width=100.0,
        )
        unstable_photo = photo_size_consistency_from_separator_bands(
            stable_separator_unstable_photo,
            target_photo_width=100.0,
        )

        self.assertLess(stable_photo.rank_penalty(), unstable_photo.rank_penalty())
        self.assertGreater(stable_photo.separator_width_cv or 0.0, 0.70)
        self.assertAlmostEqual(stable_photo.photo_width_cv or 0.0, 0.0)

    def test_incomplete_gap_edges_keep_target_photo_width_detail(self) -> None:
        detail = photo_size_consistency_from_gap_edges(
            [Gap(1, 100.0, 1.0, "equal")],
            origin=0.0,
            pitch=120.0,
            count=2,
            target_photo_width=96.0,
        ).detail()

        self.assertFalse(detail["used"])
        self.assertEqual(detail["reason"], "incomplete_separator_edges")
        self.assertEqual(detail["target_photo_width"], 96.0)

    def test_separator_width_theory_is_descriptive_not_a_prior(self) -> None:
        theory = theoretical_separator_width(
            long_axis=445.0,
            short_axis=100.0,
            count=4,
            frame_aspect=1.0,
        )
        detail = theory.detail()

        self.assertTrue(detail["used"])
        self.assertEqual(detail["reason"], "ok")
        self.assertEqual(detail["mean_separator_width_if_even"], 15.0)
        self.assertEqual(detail["target_photo_width"], 100.0)
        self.assertEqual(separator_width_relation_to_theory(10.0, theory), "narrower_than_theory")
        self.assertEqual(separator_width_relation_to_theory(20.0, theory), "broader_than_theory")


if __name__ == "__main__":
    unittest.main()
