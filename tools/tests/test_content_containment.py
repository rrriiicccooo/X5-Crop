import unittest

import numpy as np

from x5crop.domain import Box, DetectionCandidate
from x5crop.detection.evidence.content.containment import content_containment_detail
from x5crop.detection.evidence.outer_alignment import outer_content_alignment_detail
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.parameters.content import ContentEvidenceParameters


class ContentContainmentTest(unittest.TestCase):
    def test_empty_edge_frames_are_allowed_when_content_frames_are_intact(self) -> None:
        detail = {
            "used": True,
            "support": "low_content",
            "frame_scores": [
                {"index": 1, "mean": 0.01, "coverage": 0.02, "aspect_error": None},
                {"index": 2, "mean": 0.18, "coverage": 0.42, "aspect_error": 0.04},
                {"index": 3, "mean": 0.16, "coverage": 0.35, "aspect_error": 0.05},
                {"index": 4, "mean": 0.02, "coverage": 0.03, "aspect_error": None},
            ],
        }

        containment = content_containment_detail(
            detail,
            ContentEvidenceParameters(),
            expected_count=4,
        )

        self.assertTrue(containment["content_containment_ok"])
        self.assertFalse(containment["content_integrity_failed"])
        self.assertEqual(containment["support"], "ok")
        self.assertEqual(containment["content_bearing_frame_indexes"], [2, 3])
        self.assertEqual(containment["empty_frame_indexes"], [1, 4])
        self.assertEqual(containment["leading_empty_count"], 1)
        self.assertEqual(containment["trailing_empty_count"], 1)
        self.assertEqual(containment["internal_empty_count"], 0)
        holder_texture = containment["holder_texture_evidence"]
        self.assertTrue(holder_texture["used"])
        self.assertEqual(holder_texture["evidence_role"], "holder_texture_guidance")
        self.assertTrue(holder_texture["holder_texture_low"])
        self.assertEqual(holder_texture["holder_frame_indexes"], [1, 4])

    def test_no_content_is_still_not_safe(self) -> None:
        detail = {
            "used": True,
            "frame_scores": [
                {"index": 1, "mean": 0.01, "coverage": 0.02, "aspect_error": None},
                {"index": 2, "mean": 0.02, "coverage": 0.03, "aspect_error": None},
            ],
        }

        containment = content_containment_detail(
            detail,
            ContentEvidenceParameters(),
            expected_count=2,
        )

        self.assertFalse(containment["content_containment_ok"])
        self.assertTrue(containment["content_integrity_failed"])
        self.assertEqual(containment["support"], "low_content")

    def test_aspect_conflict_on_content_frame_is_integrity_failure(self) -> None:
        detail = {
            "used": True,
            "frame_scores": [
                {"index": 1, "mean": 0.18, "coverage": 0.42, "aspect_error": 0.50},
                {"index": 2, "mean": 0.02, "coverage": 0.03, "aspect_error": None},
            ],
        }

        containment = content_containment_detail(
            detail,
            ContentEvidenceParameters(),
            expected_count=2,
        )

        self.assertFalse(containment["content_containment_ok"])
        self.assertTrue(containment["content_integrity_failed"])
        self.assertEqual(containment["support"], "aspect_conflict")

    def test_outer_overcontainment_is_allowed(self) -> None:
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 220:680] = 0
        detection = DetectionCandidate(
            format_id="120-645",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 900, 120),
            frames=[Box(0, 0, 300, 120), Box(300, 0, 600, 120), Box(600, 0, 900, 120)],
            gaps=[],
            confidence=0.0,
            detail={},
        )

        policy = get_detection_policy("120-645", "full")
        alignment = outer_content_alignment_detail(
            gray,
            detection,
            cache=None,
            alignment_policy=policy.outer.alignment_evidence,
        )

        self.assertTrue(alignment["used"])
        self.assertTrue(alignment["ok"])
        self.assertEqual(alignment["reason"], "ok")
        self.assertTrue(alignment["overcontainment_allowed"])
        self.assertTrue(alignment["overcontains_long_axis"])

    def test_outer_undercrop_is_integrity_failure(self) -> None:
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 50:850] = 0
        detection = DetectionCandidate(
            format_id="120-645",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(250, 0, 650, 120),
            frames=[Box(250, 0, 383, 120), Box(383, 0, 516, 120), Box(516, 0, 650, 120)],
            gaps=[],
            confidence=0.0,
            detail={},
        )

        policy = get_detection_policy("120-645", "full")
        alignment = outer_content_alignment_detail(
            gray,
            detection,
            cache=None,
            alignment_policy=policy.outer.alignment_evidence,
        )

        self.assertTrue(alignment["used"])
        self.assertFalse(alignment["ok"])
        self.assertEqual(alignment["reason"], "content_outside_outer_long_axis")
        self.assertGreater(alignment["max_long_undercrop"], 0)


if __name__ == "__main__":
    unittest.main()
