from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from x5crop.detection.candidate.assessment.base_scoring import base_detection_assessment
from x5crop.detection.candidate.assessment.scoring import (
    content_quality_score,
    content_support_score,
    geometry_support_score,
    separator_support_score,
)
from x5crop.domain import Box, DetectionCandidate, Gap
from x5crop.formats import format_spec
from x5crop.gap_methods import GAP_DETECTED
from x5crop.policies.registry import get_detection_policy


def _policy():
    return get_detection_policy("120-645", "full")


class CandidateLifecycleScoringContractTest(unittest.TestCase):
    def test_candidate_scoring_does_not_branch_on_format_identity(self) -> None:
        root = Path(__file__).resolve().parents[2] / "x5crop/detection/candidate/assessment"
        offenders = [
            str(path.relative_to(Path(__file__).resolve().parents[2]))
            for path in root.rglob("*.py")
            if 'format_id ==' in path.read_text(encoding="utf-8")
            or 'format_id in' in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_outer_overcontainment_is_measurement_detail_not_a_signal(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        gray[:, ::2] = 255
        assessment = base_detection_assessment(
            gray,
            Box(0, 0, 100, 100),
            [
                Gap(1, 32.0, 1.0, GAP_DETECTED, 28.0, 36.0),
                Gap(2, 68.0, 1.0, GAP_DETECTED, 64.0, 72.0),
            ],
            [Box(0, 0, 28, 100), Box(36, 0, 64, 100), Box(72, 0, 100, 100)],
            3,
            format_spec("120-645"),
            "full",
            _policy(),
            origin=0.0,
            pitch=100.0 / 3.0,
        )

        self.assertEqual(assessment.detail["outer_area_profile"]["status"], "above_profile")
        self.assertEqual(
            assessment.detail["outer_area_profile"]["role"],
            "diagnostic_until_final_alignment",
        )
        self.assertFalse(hasattr(assessment, "candidate_signals"))

    def test_photo_edges_not_frame_boxes_own_photo_size_measurement(self) -> None:
        gray = np.zeros((120, 500), dtype=np.uint8)
        gray[:, ::2] = 255
        assessment = base_detection_assessment(
            gray,
            Box(0, 10, 445, 110),
            [
                Gap(1, 105.0, 1.0, GAP_DETECTED, 100.0, 110.0),
                Gap(2, 225.0, 1.0, GAP_DETECTED, 210.0, 240.0),
                Gap(3, 342.5, 1.0, GAP_DETECTED, 340.0, 345.0),
            ],
            [
                Box(0, 10, 105, 110),
                Box(105, 10, 225, 110),
                Box(225, 10, 343, 110),
                Box(343, 10, 445, 110),
            ],
            4,
            format_spec("120-645"),
            "full",
            _policy(),
            origin=0.0,
            pitch=445.0 / 4.0,
        )

        self.assertEqual(assessment.detail["width_cv_source"], "photo_edges")
        self.assertAlmostEqual(assessment.detail["photo_width_cv"], 0.0)
        self.assertGreater(assessment.detail["frame_box_width_cv"], 0.05)
        self.assertGreater(assessment.detail["separator_width_cv"], 0.70)

    def test_separator_width_variation_is_not_a_scoring_penalty(self) -> None:
        policy = _policy()
        narrow = {
            "expected_gaps": 3,
            "hard_gaps": 3,
            "grid_gaps": 0,
            "equal_gaps": 0,
            "separator_width_cv": 0.0,
        }
        variable = {**narrow, "separator_width_cv": 0.90}
        self.assertEqual(
            separator_support_score(narrow, policy),
            separator_support_score(variable, policy),
        )

    def test_model_gaps_receive_less_credit_than_hard_separators(self) -> None:
        policy = _policy()
        hard = {
            "expected_gaps": 3,
            "hard_gaps": 3,
            "grid_gaps": 0,
            "equal_gaps": 0,
        }
        model = {
            "expected_gaps": 3,
            "hard_gaps": 0,
            "grid_gaps": 2,
            "equal_gaps": 1,
        }
        self.assertGreater(
            separator_support_score(hard, policy),
            separator_support_score(model, policy),
        )

    def test_content_support_score_measures_support_availability(self) -> None:
        self.assertEqual(
            content_support_score(
                {
                    "used": True,
                    "frame_content_support_available": True,
                }
            ),
            1.0,
        )
        self.assertEqual(
            content_support_score(
                {
                    "used": True,
                    "frame_content_support_available": False,
                }
            ),
            0.0,
        )

    def test_content_quality_is_only_a_ranking_score(self) -> None:
        policy = _policy()
        score = content_quality_score(
            {
                "used": True,
                "support": "low_content",
                "median_mean": 0.01,
                "median_coverage": 0.01,
                "max_aspect_error": None,
            },
            policy.content,
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_geometry_score_ignores_raw_outer_area_and_frame_box_width(self) -> None:
        detection = DetectionCandidate(
            format_id="120-645",
            layout="horizontal",
            strip_mode="full",
            count=4,
            outer=Box(0, 0, 400, 100),
            frames=[Box(0, 0, 100, 100)] * 4,
            gaps=[],
            confidence=0.0,
            detail={
                "outer_area_ratio": 1.0,
                "width_cv_source": "frame_boxes",
                "frame_box_width_cv": 0.80,
            },
        )
        self.assertEqual(
            geometry_support_score(detection, {"used": False}, _policy()),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
