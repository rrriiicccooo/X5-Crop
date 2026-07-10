from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from x5crop.constants import CANDIDATE_SOURCE_SAFETY
from x5crop.detection.candidate.assessment.candidate import apply_candidate_assessment_policy
from x5crop.detection.candidate.assessment.safety import (
    SAFETY_CANDIDATE_BLOCKER,
    apply_safety_candidate_assessment,
)
from x5crop.detection.candidate.signals import candidate_signals
from x5crop.domain import Box, DetectionCandidate
from x5crop.formats import format_spec
from x5crop.policies.registry import get_detection_policy
from x5crop.run_config import RunConfig


def _config() -> RunConfig:
    return RunConfig(
        input_path=Path("synthetic.tif"),
        output_dir=None,
        format_id="135",
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        requested_count=1,
        page=0,
        bleed_x=0,
        bleed_y=0,
        deskew="off",
        deskew_fallback="off",
        deskew_min_angle=-2.0,
        deskew_max_angle=2.0,
        confidence_threshold=0.85,
        review_dir=None,
        copy_review_files=False,
        export_review=False,
        compression="auto",
        debug=False,
        debug_analysis=False,
        dry_run=True,
        diagnostics=False,
        overwrite=True,
        report=True,
        debug_errors=False,
        reuse_analysis=False,
        jobs=1,
    )


class SafetyCandidateAssessmentTest(unittest.TestCase):
    def test_safety_candidate_blocker_is_candidate_assessment_detail(self) -> None:
        policy = get_detection_policy("135", "full")
        gray = np.zeros((100, 120), dtype=np.uint8)
        gray[:, 20:100] = 120
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 110, 90),
            frames=[Box(10, 10, 110, 90)],
            gaps=[],
            confidence=0.96,
            detail={"candidate_plan": {"source": CANDIDATE_SOURCE_SAFETY}},
        )
        detection = apply_candidate_assessment_policy(
            gray,
            detection,
            _config(),
            format_spec("135"),
            CANDIDATE_SOURCE_SAFETY,
            policy=policy,
        )

        apply_safety_candidate_assessment(
            detection,
            policy=policy,
        )

        self.assertAlmostEqual(detection.confidence, 0.84)
        self.assertFalse(hasattr(detection, "final_review_reasons"))
        self.assertNotIn(SAFETY_CANDIDATE_BLOCKER, candidate_signals(detection))
        assessment = detection.detail["candidate_assessment"]
        self.assertNotIn("candidate_gate_ok", assessment)
        self.assertFalse(assessment["candidate_gate"]["passed"])
        self.assertIn(SAFETY_CANDIDATE_BLOCKER, assessment["blockers"])
        self.assertIn(SAFETY_CANDIDATE_BLOCKER, assessment["candidate_gate"]["blockers"])
        self.assertEqual(assessment["source"], CANDIDATE_SOURCE_SAFETY)
        self.assertEqual(detection.detail["safety_candidate"]["candidate_gate_eligible"], False)
        self.assertEqual(
            detection.detail["safety_candidate"]["candidate_blocker_signal"],
            SAFETY_CANDIDATE_BLOCKER,
        )
        self.assertEqual(assessment["confidence_caps"][0]["reason"], "candidate_gate_failed")


if __name__ == "__main__":
    unittest.main()
