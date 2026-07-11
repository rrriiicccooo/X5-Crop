from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.domain import CropEnvelope, VisibleSequenceSpan
from x5crop.domain import AxisBleedParameters, Box
from x5crop.output.bleed import output_bleed_geometry
from x5crop.output.bleed_plan import output_bleed_plan
from x5crop.output.model import OutputGeometry
from x5crop.policies.registry import get_detection_policy
from x5crop.units import ScanCalibration


class InterFrameOverlapBleedTest(unittest.TestCase):
    def test_zero_bleed_still_applies_crop_envelope_uncertainty(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            visible_sequence_span=VisibleSequenceSpan(Box(10, 5, 190, 95)),
            crop_envelope=CropEnvelope(Box(9, 4, 191, 96)),
            frames=(Box(10, 5, 100, 95), Box(100, 5, 190, 95)),
        )
        candidate = replace(candidate, geometry=geometry)
        plan = output_bleed_plan(
            False,
            0.0,
            AxisBleedParameters(0, 0),
            get_detection_policy("135", "full").output,
            long_axis_bleed_capacity_px=50,
        )
        detection = apply_decision_gate(
            selection_fixture(candidate),
            plan,
            transform_geometry_fixture(),
            ScanCalibration(None, None, "unavailable", False),
            image_width=200,
            image_height=100,
        )
        self.assertEqual(
            detection.decision_geometry.frames,
            (Box(9, 4, 100, 96), Box(100, 4, 191, 96)),
        )

    def test_feasible_plan_increases_only_long_axis_bleed(self) -> None:
        policy = get_detection_policy("135", "full")
        plan = output_bleed_plan(
            True,
            72.0,
            AxisBleedParameters(20, 10),
            policy.output,
            long_axis_bleed_capacity_px=50,
        )
        self.assertTrue(plan.feasible)
        self.assertEqual(plan.effective_bleed, AxisBleedParameters(36, 10))

    def test_unresolved_plan_uses_available_capacity(self) -> None:
        policy = get_detection_policy("135", "full")
        plan = output_bleed_plan(
            True,
            140.0,
            AxisBleedParameters(20, 10),
            policy.output,
            long_axis_bleed_capacity_px=50,
        )
        self.assertFalse(plan.feasible)
        self.assertEqual(plan.overlap_required_long_axis_bleed_px, 70)
        self.assertEqual(plan.effective_bleed.long_axis, 50)
        self.assertEqual(plan.effective_bleed.short_axis, 10)

    def test_output_bleed_expands_frames_not_crop_envelope(self) -> None:
        geometry = OutputGeometry(
            CropEnvelope(Box(0, 0, 100, 60)),
            (Box(0, 0, 50, 60), Box(50, 0, 100, 60)),
        )
        expanded = output_bleed_geometry(
            geometry,
            AxisBleedParameters(36, 0),
            layout="horizontal",
            image_width=100,
            image_height=60,
        )
        self.assertEqual(expanded.crop_envelope, geometry.crop_envelope)
        self.assertEqual(expanded.frames[0], Box(0, 0, 86, 60))
        self.assertEqual(expanded.frames[1], Box(14, 0, 100, 60))

    def test_dual_lane_crop_envelopes_are_applied_per_lane(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            count=4,
            crop_envelope=CropEnvelope(Box(0, 0, 200, 100)),
            frames=(
                Box(5, 5, 100, 40),
                Box(100, 5, 195, 40),
                Box(5, 60, 100, 95),
                Box(100, 60, 195, 95),
            ),
            lane_boxes=(Box(0, 0, 200, 45), Box(0, 55, 200, 100)),
            lane_crop_envelopes=(
                CropEnvelope(Box(0, 0, 200, 45)),
                CropEnvelope(Box(0, 55, 200, 100)),
            ),
        )
        candidate = replace(candidate, geometry=geometry)
        plan = output_bleed_plan(
            False,
            0.0,
            AxisBleedParameters(0, 0),
            get_detection_policy("135", "full").output,
            long_axis_bleed_capacity_px=50,
        )
        detection = apply_decision_gate(
            selection_fixture(candidate),
            plan,
            transform_geometry_fixture(),
            ScanCalibration(None, None, "unavailable", False),
            image_width=200,
            image_height=100,
        )
        self.assertEqual(
            detection.decision_geometry.frames,
            (
                Box(0, 0, 100, 45),
                Box(100, 0, 200, 45),
                Box(0, 55, 100, 100),
                Box(100, 55, 200, 100),
            ),
        )


if __name__ == "__main__":
    unittest.main()
