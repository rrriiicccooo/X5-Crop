from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from x5crop.detection.candidate.assessment.dual_lane import (
    apply_dual_lane_content_assessment,
)
from x5crop.detection.candidate.signals import (
    SIGNAL_CONTENT_ASPECT_CONFLICT,
    candidate_signals,
)
from x5crop.domain import Box, DetectionCandidate
from x5crop.policies.registry import get_detection_policy


class DualLaneAssessmentTest(unittest.TestCase):
    def test_content_conflict_cap_is_candidate_assessment_detail(self) -> None:
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=6,
            outer=Box(0, 0, 120, 20),
            frames=[],
            gaps=[],
            confidence=0.96,
            detail={},
        )
        policy = get_detection_policy("135", "full")
        gray = np.zeros((20, 120), dtype=np.uint8)

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
                gray,
                detection,
                object(),
                policy,
                confidence_threshold=0.85,
                horizontal_frame_aspect=1.5,
            )

        self.assertEqual(detection.confidence, 0.82)
        self.assertFalse(hasattr(detection, "final_review_reasons"))
        self.assertEqual(candidate_signals(detection), [SIGNAL_CONTENT_ASPECT_CONFLICT])
        self.assertEqual(
            detection.detail["candidate_confidence_caps"],
            [
                {
                    "owner": "candidate.assessment",
                    "reason": SIGNAL_CONTENT_ASPECT_CONFLICT,
                    "cap_value": 0.82,
                    "confidence_before": 0.96,
                    "confidence_after": 0.82,
                    "changed": True,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
