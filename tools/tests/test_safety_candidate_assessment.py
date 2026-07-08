from __future__ import annotations

import unittest

from x5crop.detection.candidate.assessment.safety import (
    SAFETY_CANDIDATE_GATE_BLOCKER,
    apply_safety_candidate_assessment,
)
from x5crop.detection.candidate.reasons import candidate_reasons
from x5crop.constants import CANDIDATE_SOURCE_SAFETY
from x5crop.domain import Box, Detection
from x5crop.policies.registry import get_detection_policy


def _candidate_gate_detail(passed: bool) -> dict:
    return {
        "passed": bool(passed),
        "checks": [],
        "blockers": [],
        "diagnostics": [],
        "confidence_caps": [],
    }


class SafetyCandidateAssessmentTest(unittest.TestCase):
    def test_safety_candidate_gate_blocker_is_candidate_assessment_detail(self) -> None:
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
                    "candidate_gate_passed": True,
                    "gate": _candidate_gate_detail(True),
                }
            },
        )

        apply_safety_candidate_assessment(
            detection,
            confidence_threshold=0.85,
            policy=policy,
        )

        self.assertAlmostEqual(detection.confidence, 0.84)
        self.assertEqual(detection.review_reasons, [])
        self.assertEqual(candidate_reasons(detection), [SAFETY_CANDIDATE_GATE_BLOCKER])
        assessment = detection.detail["candidate_assessment"]
        self.assertFalse(assessment["candidate_gate_passed"])
        self.assertFalse(assessment["gate"]["passed"])
        self.assertIn(SAFETY_CANDIDATE_GATE_BLOCKER, assessment["blockers"])
        self.assertIn(SAFETY_CANDIDATE_GATE_BLOCKER, assessment["gate"]["blockers"])
        self.assertEqual(assessment["source"], CANDIDATE_SOURCE_SAFETY)
        self.assertEqual(detection.detail["safety_candidate"]["candidate_gate_eligible"], False)
        self.assertEqual(
            detection.detail["safety_candidate"]["candidate_gate_signal"],
            SAFETY_CANDIDATE_GATE_BLOCKER,
        )
        self.assertEqual(
            detection.detail["candidate_confidence_caps"],
            [
                {
                    "owner": "candidate.assessment",
                    "reason": SAFETY_CANDIDATE_GATE_BLOCKER,
                    "cap_value": 0.84,
                    "confidence_before": 0.96,
                    "confidence_after": 0.84,
                    "changed": True,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
