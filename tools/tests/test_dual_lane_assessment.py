from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from x5crop.detection.candidate.assessment.dual_lane import (
    apply_dual_lane_content_assessment,
)
from x5crop.domain import Box, DetectionCandidate
from x5crop.policies.registry import get_detection_policy


class DualLaneAssessmentTest(unittest.TestCase):
    def test_content_conflict_is_diagnostic_not_a_cap_or_final_reason(self) -> None:
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=6,
            outer=Box(0, 0, 120, 20),
            frames=[],
            gaps=[],
            confidence=0.96,
            detail={"candidate_assessment": {"diagnostics": []}},
        )
        policy = get_detection_policy("135", "full")

        with (
            patch(
                "x5crop.detection.candidate.assessment.dual_lane.content_evidence_detail",
                return_value={"used": True, "support": "aspect_conflict"},
            ),
            patch(
                "x5crop.detection.candidate.assessment.dual_lane.outer_content_alignment_detail",
                return_value={"used": False},
            ),
        ):
            apply_dual_lane_content_assessment(
                np.zeros((20, 120), dtype=np.uint8),
                detection,
                object(),
                policy,
                horizontal_frame_aspect=1.5,
            )

        self.assertEqual(detection.confidence, 0.96)
        self.assertFalse(hasattr(detection, "final_review_reasons"))
        self.assertEqual(
            detection.detail["candidate_assessment"]["diagnostics"],
            ["content_aspect_uncertain"],
        )
        self.assertNotIn("candidate_confidence_caps", detection.detail)


if __name__ == "__main__":
    unittest.main()
