from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.cache import MeasurementCache
from x5crop.detection.evidence.exposure_overlap import exposure_overlap_evidence
from x5crop.detection.evidence.gap_evidence import GapEvidenceRecord
from x5crop.domain import AxisBleedParameters, Box
from x5crop.output.bleed import output_bleed_geometry
from x5crop.output.model import OutputGeometry
from x5crop.output.protection import output_protection_plan
from x5crop.policies.registry import get_detection_policy


class ExposureOverlapProtectionTest(unittest.TestCase):
    def test_evidence_and_protection_are_universal_capabilities(self) -> None:
        reference = get_detection_policy("135", "full")
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
                policy = get_detection_policy(format_id, strip_mode)
                self.assertEqual(
                    policy.exposure_overlap_evidence,
                    reference.exposure_overlap_evidence,
                )
                self.assertFalse(hasattr(policy.exposure_overlap_evidence, "enabled"))

    def test_evidence_only_reports_physical_overlap(self) -> None:
        candidate = candidate_fixture()
        gray = np.zeros((100, 200), dtype=np.uint8)
        cache = MeasurementCache(
            "horizontal",
            gray,
            gray,
            gray.astype(np.float32),
        )
        record = GapEvidenceRecord(
            1,
            "equal",
            "geometry_model",
            100.0,
            100.0,
            0.0,
            40.0,
            "not_hard_separator",
            "medium",
            True,
            (80, 120),
            None,
        )
        policy = get_detection_policy("135", "full")
        with patch(
            "x5crop.detection.evidence.exposure_overlap.gap_evidence_record",
            return_value=record,
        ):
            evidence = exposure_overlap_evidence(
                candidate.geometry,
                cache,
                separator_policy=policy.separator,
                parameters=policy.exposure_overlap_evidence,
            )
        self.assertTrue(evidence.detected)
        self.assertEqual(evidence.widest_overlap_band_px, 40.0)
        self.assertFalse(hasattr(evidence, "feasible"))

    def test_feasible_plan_increases_long_axis_bleed(self) -> None:
        policy = get_detection_policy("135", "full")
        plan = output_protection_plan(
            True,
            72.0,
            AxisBleedParameters(20, 10),
            policy.output.exposure_overlap_protection,
            long_axis_bleed_capacity_px=50,
        )
        self.assertTrue(plan.feasible)
        self.assertEqual(plan.output_bleed, AxisBleedParameters(36, 10))

    def test_unresolved_plan_uses_available_capacity(self) -> None:
        policy = get_detection_policy("135", "full")
        plan = output_protection_plan(
            True,
            140.0,
            AxisBleedParameters(20, 10),
            policy.output.exposure_overlap_protection,
            long_axis_bleed_capacity_px=50,
        )
        self.assertFalse(plan.feasible)
        self.assertEqual(plan.required_long_axis_bleed_px, 70)
        self.assertEqual(plan.output_bleed.long_axis, 50)

    def test_output_bleed_expands_frame_geometry_only(self) -> None:
        geometry = OutputGeometry(
            Box(0, 0, 100, 60),
            (Box(0, 0, 50, 60), Box(50, 0, 100, 60)),
        )
        expanded = output_bleed_geometry(
            geometry,
            AxisBleedParameters(36, 0),
            layout="horizontal",
            image_width=100,
            image_height=60,
        )
        self.assertEqual(expanded.frames[0], Box(0, 0, 86, 60))
        self.assertEqual(expanded.frames[1], Box(14, 0, 100, 60))


if __name__ == "__main__":
    unittest.main()
