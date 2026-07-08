import unittest

import numpy as np

from x5crop.detection.candidate.assessment.base_scoring import base_detection_assessment
from x5crop.detection.candidate.assessment.scoring import geometry_support_score
from x5crop.detection.evidence.photo_width import photo_width_cv_from_detail
from x5crop.detection.candidate.plan.counts import raw_detection_rank
from x5crop.domain import Detection, Gap
from x5crop.domain import Box
from x5crop.formats import format_spec
from x5crop.gap_methods import GAP_DETECTED
from x5crop.geometry.gap_geometry import (
    gap_width_cv,
    photo_width_cv_from_gap_edges,
    photo_widths_from_gap_edges,
    separator_width_cv,
)
from x5crop.policies.registry import get_detection_policy


class PhotoWidthMetricsTest(unittest.TestCase):
    def _policy(self):
        return get_detection_policy("120-645", "full")

    def test_separator_width_variation_does_not_change_photo_width_cv(self) -> None:
        gaps = [
            Gap(1, 105.0, 1.0, GAP_DETECTED, 100.0, 110.0),
            Gap(2, 225.0, 1.0, GAP_DETECTED, 210.0, 240.0),
            Gap(3, 342.5, 1.0, GAP_DETECTED, 340.0, 345.0),
        ]
        count = 4
        origin = 0.0
        pitch = 445.0 / count

        self.assertEqual(
            photo_widths_from_gap_edges(gaps, origin, pitch, count),
            [100.0, 100.0, 100.0, 100.0],
        )
        self.assertAlmostEqual(
            photo_width_cv_from_gap_edges(gaps, origin, pitch, count),
            0.0,
        )
        self.assertGreater(separator_width_cv(gaps), 0.70)
        self.assertGreater(gap_width_cv(gaps, origin, pitch, count), 0.05)

    def test_base_scoring_uses_photo_width_cv_before_frame_box_width_cv(self) -> None:
        gray = np.zeros((120, 500), dtype=np.uint8)
        gray[:, ::2] = 255
        outer = Box(0, 10, 445, 110)
        gaps = [
            Gap(1, 105.0, 1.0, GAP_DETECTED, 100.0, 110.0),
            Gap(2, 225.0, 1.0, GAP_DETECTED, 210.0, 240.0),
            Gap(3, 342.5, 1.0, GAP_DETECTED, 340.0, 345.0),
        ]
        boxes = [
            Box(0, 10, 105, 110),
            Box(105, 10, 225, 110),
            Box(225, 10, 343, 110),
            Box(343, 10, 445, 110),
        ]

        assessment = base_detection_assessment(
            gray,
            outer,
            gaps,
            boxes,
            4,
            format_spec("120-645"),
            "full",
            self._policy(),
            origin=0.0,
            pitch=445.0 / 4.0,
        )

        self.assertEqual(assessment.detail["width_cv_source"], "photo_edges")
        self.assertAlmostEqual(assessment.detail["photo_width_cv"], 0.0)
        self.assertGreater(assessment.detail["frame_box_width_cv"], 0.05)
        self.assertGreater(assessment.detail["separator_width_cv"], 0.70)
        self.assertNotIn("photo_width_unstable", assessment.candidate_signals)

    def test_geometry_support_respects_zero_photo_width_cv(self) -> None:
        detection = Detection(
            film_format="120-645",
            layout="horizontal",
            strip_mode="full",
            count=4,
            outer=Box(0, 10, 445, 110),
            frames=[
                Box(0, 10, 105, 110),
                Box(105, 10, 225, 110),
                Box(225, 10, 343, 110),
                Box(343, 10, 445, 110),
            ],
            gaps=[],
            confidence=0.0,
            final_review_reasons=[],
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "outer_area_ratio": 0.74,
            },
        )

        score = geometry_support_score(
            detection,
            {"used": False, "support": "unknown", "max_aspect_error": None},
            self._policy(),
        )

        self.assertGreater(score, 0.90)

    def test_photo_width_detail_requires_explicit_photo_width_cv(self) -> None:
        self.assertIsNone(
            photo_width_cv_from_detail(
                {
                    "width_cv": 0.0,
                    "width_cv_source": "photo_edges",
                }
            )
        )

    def test_geometry_support_ignores_frame_box_width_detail(self) -> None:
        detection = Detection(
            film_format="120-645",
            layout="horizontal",
            strip_mode="full",
            count=4,
            outer=Box(0, 10, 445, 110),
            frames=[
                Box(0, 10, 80, 110),
                Box(105, 10, 250, 110),
                Box(260, 10, 320, 110),
                Box(343, 10, 445, 110),
            ],
            gaps=[],
            confidence=0.0,
            final_review_reasons=[],
            detail={
                "width_cv": 0.20,
                "width_cv_source": "frame_boxes",
                "frame_box_width_cv": 0.20,
                "outer_area_ratio": 0.74,
            },
        )

        score = geometry_support_score(
            detection,
            {"used": False, "support": "unknown", "max_aspect_error": None},
            self._policy(),
        )

        self.assertGreater(score, 0.90)

    def test_raw_detection_rank_does_not_reward_frame_box_width_detail(self) -> None:
        stable_frame_boxes = Detection(
            film_format="120-645",
            layout="horizontal",
            strip_mode="full",
            count=4,
            outer=Box(0, 0, 400, 100),
            frames=[],
            gaps=[],
            confidence=0.82,
            final_review_reasons=[],
            detail={"width_cv": 0.0, "width_cv_source": "frame_boxes"},
        )
        unstable_frame_boxes = Detection(
            film_format="120-645",
            layout="horizontal",
            strip_mode="full",
            count=4,
            outer=Box(0, 0, 400, 100),
            frames=[],
            gaps=[],
            confidence=0.82,
            final_review_reasons=[],
            detail={"width_cv": 0.20, "width_cv_source": "frame_boxes"},
        )

        self.assertEqual(
            raw_detection_rank(stable_frame_boxes, 0.85),
            raw_detection_rank(unstable_frame_boxes, 0.85),
        )


if __name__ == "__main__":
    unittest.main()
