from __future__ import annotations

import unittest

from x5crop.detection.candidate.assessment.safety import (
    SAFETY_CANDIDATE_REVIEW_ONLY_REASON,
    apply_safety_candidate_assessment,
)
from x5crop.domain import Box, Detection
from x5crop.policies.registry import get_detection_policy


class SafetyCandidateAssessmentTest(unittest.TestCase):
    def test_safety_candidate_review_only_contract_is_candidate_assessment_detail(self) -> None:
        policy = get_detection_policy("135", "full")
        detection = Detection(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=6,
            outer=Box(0, 0, 120, 20),
            frames=[],
            gaps=[],
            confidence=0.96,
            review_reasons=[],
            detail={
                "candidate_assessment": {
                    "source": "separator",
                    "auto_gate": True,
                    "auto_gate_inputs": {"source": "separator"},
                }
            },
        )

        apply_safety_candidate_assessment(
            detection,
            confidence_threshold=0.85,
            policy=policy,
        )

        self.assertAlmostEqual(detection.confidence, 0.84)
        self.assertEqual(detection.review_reasons, [SAFETY_CANDIDATE_REVIEW_ONLY_REASON])
        assessment = detection.detail["candidate_assessment"]
        self.assertFalse(assessment["auto_gate"])
        self.assertEqual(assessment["source"], "safety_candidate")
        self.assertEqual(assessment["auto_gate_inputs"]["source"], "safety_candidate")
        self.assertEqual(detection.detail["safety_candidate"]["review_only"], True)
        self.assertEqual(
            detection.detail["candidate_confidence_caps"],
            [
                {
                    "owner": "candidate.assessment",
                    "reason": SAFETY_CANDIDATE_REVIEW_ONLY_REASON,
                    "cap_value": 0.84,
                    "confidence_before": 0.96,
                    "confidence_after": 0.84,
                    "changed": True,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
