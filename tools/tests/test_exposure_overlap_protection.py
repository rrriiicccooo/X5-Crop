from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import final_detection_fixture
from x5crop.detection.evidence.exposure_overlap import (
    exposure_overlap_evidence_detail,
)
from x5crop.domain import AxisBleedParameters, Box, FinalDetection, Gap
from x5crop.output.bleed import apply_output_protection_plan
from x5crop.output.protection import output_protection_plan
from x5crop.policies.registry import get_detection_policy


def _detection() -> FinalDetection:
    detection = final_detection_fixture(status="approved_auto")
    detection.count = 2
    detection.outer = Box(0, 0, 100, 60)
    detection.frames = [Box(0, 0, 50, 60), Box(50, 0, 100, 60)]
    detection.gaps = [Gap(1, 50.0, 0.5, "grid")]
    detection.confidence = 0.95
    detection.detail = {}
    return detection


class ExposureOverlapProtectionTest(unittest.TestCase):
    def test_evidence_capability_is_universal_across_format_modes(self) -> None:
        reference = get_detection_policy("135", "full").exposure_overlap_evidence
        for format_id in (
            "135",
            "135-dual",
            "half",
            "xpan",
            "120-645",
            "120-66",
            "120-67",
        ):
            for strip_mode in ("full", "partial"):
                with self.subTest(format_id=format_id, strip_mode=strip_mode):
                    policy = get_detection_policy(format_id, strip_mode)
                    self.assertEqual(policy.exposure_overlap_evidence, reference)
                    self.assertFalse(hasattr(policy.exposure_overlap_evidence, "enabled"))
                    self.assertFalse(
                        hasattr(policy.output.exposure_overlap_protection, "enabled")
                    )

    def test_evidence_only_measures_physical_overlap(self) -> None:
        detection = _detection()
        record = {
            "exposure_overlap_class": "medium",
            "width_px": 0.0,
            "signals": {"window": {"start": 10, "end": 50}},
        }
        policy = get_detection_policy("135", "full")
        with patch(
            "x5crop.detection.evidence.exposure_overlap.gap_evidence_record",
            return_value=record,
        ):
            evidence = exposure_overlap_evidence_detail(
                np.zeros((80, 120), dtype=np.uint8),
                detection,
                cache=None,
                separator_policy=policy.separator,
                exposure_overlap_policy=policy.exposure_overlap_evidence,
            )

        self.assertTrue(evidence["exposure_overlap_detected"])
        self.assertEqual(evidence["widest_overlap_band_px"], 40.0)
        self.assertNotIn("feasible", evidence)
        self.assertNotIn("final_review_reason", evidence)

    def test_feasible_plan_increases_long_axis_bleed(self) -> None:
        policy = get_detection_policy("135", "full")
        plan = output_protection_plan(
            {
                "exposure_overlap_detected": True,
                "widest_overlap_band_px": 72.0,
            },
            AxisBleedParameters(long_axis=20, short_axis=10),
            policy.output.exposure_overlap_protection,
        )

        self.assertTrue(plan.feasible)
        self.assertEqual(plan.required_long_axis_bleed_px, 36)
        self.assertEqual(plan.output_bleed, AxisBleedParameters(36, 10))

    def test_unresolved_plan_uses_available_capacity_for_review_output(self) -> None:
        policy = get_detection_policy("135", "full")
        plan = output_protection_plan(
            {
                "exposure_overlap_detected": True,
                "widest_overlap_band_px": 140.0,
            },
            AxisBleedParameters(long_axis=20, short_axis=10),
            policy.output.exposure_overlap_protection,
        )

        self.assertFalse(plan.feasible)
        self.assertEqual(plan.required_long_axis_bleed_px, 70)
        self.assertEqual(plan.output_bleed, AxisBleedParameters(50, 10))

    def test_finalization_applies_the_same_plan(self) -> None:
        detection = _detection()
        policy = get_detection_policy("135", "full")
        plan = output_protection_plan(
            {
                "exposure_overlap_detected": True,
                "widest_overlap_band_px": 72.0,
            },
            AxisBleedParameters(long_axis=20, short_axis=10),
            policy.output.exposure_overlap_protection,
        )

        apply_output_protection_plan(
            detection,
            plan,
            image_w=100,
            image_h=60,
        )

        self.assertEqual(detection.frames[0], Box(0, 0, 86, 60))
        self.assertEqual(detection.frames[1], Box(14, 0, 100, 60))
        self.assertEqual(
            detection.detail["output_protection_plan"],
            {**plan.report_detail(), "applied": True},
        )


if __name__ == "__main__":
    unittest.main()
