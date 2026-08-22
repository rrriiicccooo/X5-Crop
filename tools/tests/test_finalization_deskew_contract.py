from __future__ import annotations

import math
from types import SimpleNamespace
import unittest

from x5crop.detection.final.deskew import assess_output_deskew
from x5crop.detection.final.finalize import finalize_detection
from x5crop.detection.output_deskew import (
    DeskewEdgeFit,
    DeskewSkipReason,
    LightweightDeskewObservation,
)
from x5crop.domain import Box, EvidenceState


def _supported_observation(angle_degrees: float) -> LightweightDeskewObservation:
    slope = math.tan(math.radians(abs(angle_degrees)))
    if angle_degrees < 0.0:
        slope = -slope
    fit = DeskewEdgeFit(
        slope=slope,
        angle_degrees=math.degrees(math.atan(slope)),
        sample_count=8,
        inlier_count=8,
        median_residual_px=0.25,
    )
    return LightweightDeskewObservation(
        state=EvidenceState.SUPPORTED,
        angle_degrees=angle_degrees,
        top_fit=fit,
        bottom_fit=fit,
        sample_trace_count=8,
        skip_reason=None,
    )


def _unavailable_observation() -> LightweightDeskewObservation:
    return LightweightDeskewObservation(
        state=EvidenceState.UNAVAILABLE,
        angle_degrees=None,
        top_fit=None,
        bottom_fit=None,
        sample_trace_count=0,
        skip_reason=DeskewSkipReason.NO_DARK_SUPPORT,
    )


def _candidate(slot_count: int = 2):
    source_core = object()
    resolved = SimpleNamespace(output_slot_count=slot_count)
    identities = tuple(f"slot:{index}" for index in range(slot_count))
    footprints = tuple(
        SimpleNamespace(
            required_source_footprint=(
                (10.25 + index * 40.0, 12.5),
                (35.75 + index * 40.0, 12.5),
                (35.75 + index * 40.0, 42.25),
                (10.25 + index * 40.0, 42.25),
            ),
            sampling_authority_box=Box(0, 0, 160, 100),
        )
        for index in range(slot_count)
    )
    return SimpleNamespace(
        source_core=source_core,
        resolved_output_slots=resolved,
        output_slot_identities=identities,
        output_footprints=footprints,
    )


class FinalizationDeskewContractTest(unittest.TestCase):
    def test_measurement_skip_is_identity_and_does_not_block_approved_output(
        self,
    ) -> None:
        detection = finalize_detection(
            _candidate(),
            SimpleNamespace(status="approved_auto"),
            _unavailable_observation(),
            layout="horizontal",
            source_width=160,
            source_height=100,
        )

        self.assertTrue(detection.frame_export_eligible)
        self.assertFalse(detection.deskew_assessment.deskew_applied)
        self.assertTrue(detection.deskew_assessment.transform.is_identity)
        self.assertIsNone(detection.deskew_assessment.observed_angle_degrees)
        self.assertIsNone(
            detection.deskew_assessment.applied_source_rotation_degrees
        )
        self.assertEqual(
            detection.deskew_assessment.skip_reason,
            DeskewSkipReason.NO_DARK_SUPPORT,
        )
        self.assertEqual(detection.final_boxes[0], Box(10, 12, 36, 43))

    def test_endpoint_displacement_threshold_preserves_real_zero_observation(
        self,
    ) -> None:
        long_extent = 1000
        below = math.degrees(math.atan(2.999 / (long_extent - 1)))
        above = math.degrees(math.atan(3.001 / (long_extent - 1)))

        zero = assess_output_deskew(
            _supported_observation(0.0),
            layout="horizontal",
            source_width=long_extent,
            source_height=100,
        )
        not_needed = assess_output_deskew(
            _supported_observation(below),
            layout="horizontal",
            source_width=long_extent,
            source_height=100,
        )
        applied = assess_output_deskew(
            _supported_observation(above),
            layout="horizontal",
            source_width=long_extent,
            source_height=100,
        )

        for assessment in (zero, not_needed):
            self.assertFalse(assessment.deskew_applied)
            self.assertTrue(assessment.transform.is_identity)
            self.assertEqual(
                assessment.skip_reason,
                DeskewSkipReason.ROTATION_NOT_NEEDED,
            )
            self.assertIsNotNone(assessment.observed_angle_degrees)
            self.assertEqual(assessment.applied_source_rotation_degrees, 0.0)
        self.assertTrue(applied.deskew_applied)
        self.assertFalse(applied.transform.is_identity)
        self.assertIsNone(applied.skip_reason)

    def test_horizontal_and_vertical_source_rotation_signs_are_explicit(
        self,
    ) -> None:
        cases = (
            ("horizontal", 1.0, -1.0),
            ("horizontal", -1.0, 1.0),
            ("vertical", 1.0, 1.0),
            ("vertical", -1.0, -1.0),
        )
        for layout, observed, expected in cases:
            with self.subTest(layout=layout, observed=observed):
                assessment = assess_output_deskew(
                    _supported_observation(observed),
                    layout=layout,
                    source_width=1000 if layout == "horizontal" else 100,
                    source_height=100 if layout == "horizontal" else 1000,
                )
                self.assertTrue(assessment.deskew_applied)
                self.assertAlmostEqual(
                    assessment.applied_source_rotation_degrees,
                    expected,
                )

    def test_rotated_final_box_is_the_exact_transformed_polygon_envelope(
        self,
    ) -> None:
        candidate = _candidate(slot_count=1)
        detection = finalize_detection(
            candidate,
            SimpleNamespace(status="approved_auto"),
            _supported_observation(1.0),
            layout="horizontal",
            source_width=160,
            source_height=100,
        )
        transform = detection.deskew_assessment.transform
        box = detection.final_boxes[0]
        mapped = tuple(
            transform.map_point(*point)
            for point in candidate.output_footprints[0].required_source_footprint
        )

        self.assertTrue(all(box.left <= x < box.right for x, _ in mapped))
        self.assertTrue(all(box.top <= y < box.bottom for _, y in mapped))
        self.assertTrue(all(item is transform for item in detection.output_transforms))
        self.assertGreaterEqual(box.left, 0)
        self.assertGreaterEqual(box.top, 0)
        self.assertLessEqual(box.right, transform.output_extent.width)
        self.assertLessEqual(box.bottom, transform.output_extent.height)

    def test_review_skips_measurement_and_exposes_no_official_geometry(
        self,
    ) -> None:
        detection = finalize_detection(
            _candidate(),
            SimpleNamespace(status="needs_review"),
            None,
            layout="horizontal",
            source_width=1000,
            source_height=100,
        )

        self.assertFalse(detection.deskew_assessment.deskew_applied)
        self.assertEqual(
            detection.deskew_assessment.skip_reason,
            DeskewSkipReason.OUTPUT_NOT_ELIGIBLE,
        )
        self.assertEqual(detection.output_transforms, ())
        self.assertEqual(detection.output_footprints, ())
        self.assertEqual(detection.sampling_authority_boxes, ())
        self.assertEqual(detection.final_boxes, ())


if __name__ == "__main__":
    unittest.main()
