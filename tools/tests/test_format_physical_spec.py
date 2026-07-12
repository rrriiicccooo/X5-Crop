from __future__ import annotations

import unittest

from x5crop.formats import FORMATS
from x5crop.detection.candidate.plan.count_hypotheses import count_hypothesis_plan
from x5crop.configuration.registry import get_detection_configuration
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.configuration.bundle import DetectionConfigurationBundle


class FormatPhysicalSpecTests(unittest.TestCase):
    def test_expected_separator_count_is_derived_not_stored(self) -> None:
        from x5crop.formats import FormatPhysicalSpec

        self.assertNotIn(
            "expected_separator_count",
            FormatPhysicalSpec.__dataclass_fields__,
        )
        self.assertIsInstance(FormatPhysicalSpec.expected_separator_count, property)

    def test_configuration_report_uses_physical_separator_count(self) -> None:
        for format_id, spec in FORMATS.items():
            for strip_mode in ("full", "partial"):
                with self.subTest(format_id=format_id, strip_mode=strip_mode):
                    configuration = get_detection_configuration(format_id, strip_mode)
                    detail = detection_configuration_read_model(configuration)
                    self.assertEqual(
                        detail["physical"]["expected_separator_count"],
                        spec.expected_separator_count,
                    )

    def test_frame_aspects_are_derived_from_nominal_mm_size(self) -> None:
        expected_aspects = {
            "135": 36.0 / 24.0,
            "135-dual": 36.0 / 24.0,
            "half": 18.0 / 24.0,
            "xpan": 65.0 / 24.0,
            "120-645": 42.0 / 56.0,
            "120-66": 56.0 / 56.0,
            "120-67": 70.0 / 56.0,
        }

        for format_id, expected in expected_aspects.items():
            with self.subTest(format_id=format_id):
                spec = FORMATS[format_id]
                self.assertAlmostEqual(spec.horizontal_content_aspect, expected)
                self.assertAlmostEqual(
                    spec.nominal_frame_size_mm.width_mm / spec.nominal_frame_size_mm.height_mm,
                    expected,
                )

    def test_dual_lane_composition_is_a_physical_format_fact(self) -> None:
        dual = FORMATS["135-dual"]
        self.assertEqual(dual.physical_layout, "dual_lane")
        self.assertEqual(dual.lane_count, 2)
        self.assertEqual(dual.lane_format_id, "135")
        self.assertEqual(dual.expected_separator_count, 10)

        for format_id, spec in FORMATS.items():
            if format_id == "135-dual":
                continue
            self.assertEqual(spec.lane_count, 1)
            self.assertIsNone(spec.lane_format_id)

    def test_dual_lane_bundle_resolves_the_physical_lane_configuration(self) -> None:
        bundle = DetectionConfigurationBundle.for_format_mode("135-dual", "full")
        self.assertEqual(
            bundle.initial_configuration.physical_spec.format_id,
            "135-dual",
        )
        self.assertEqual(
            bundle.configuration_for("135", "full").physical_spec.format_id,
            "135",
        )

    def test_medium_square_records_same_aspect_size_variant(self) -> None:
        spec = FORMATS["120-66"]
        self.assertEqual(
            [(item.width_mm, item.height_mm, item.label) for item in spec.frame_size_mm_options],
            [(56.0, 56.0, "nominal"), (54.0, 54.0, "camera_variant")],
        )
        self.assertTrue(
            all(
                item.aspect == spec.horizontal_content_aspect
                for item in spec.frame_size_mm_options
            )
        )

    def test_only_xpan_and_medium_square_can_be_complete_underfilled_strips(self) -> None:
        expected = {
            "135": False,
            "135-dual": False,
            "half": False,
            "xpan": True,
            "120-645": False,
            "120-66": True,
            "120-67": False,
        }
        for format_id, can_underfill in expected.items():
            with self.subTest(format_id=format_id):
                self.assertEqual(
                    FORMATS[format_id].complete_strip_can_be_underfilled,
                    can_underfill,
                )

    def test_configuration_report_exposes_physical_aspect_source(self) -> None:
        configuration = get_detection_configuration("half", "full")
        detail = detection_configuration_read_model(configuration)
        physical = detail["physical"]

        self.assertEqual(physical["aspect_source"], "frame_size_mm")
        self.assertEqual(physical["nominal_frame_size_mm"]["width_mm"], 18.0)
        self.assertEqual(physical["nominal_frame_size_mm"]["height_mm"], 24.0)
        self.assertAlmostEqual(physical["frame_aspect"], 0.75)

    def test_configuration_report_exposes_complete_underfilled_trait(self) -> None:
        configuration = get_detection_configuration("120-66", "partial")
        detail = detection_configuration_read_model(configuration)
        self.assertTrue(detail["physical"]["complete_strip_can_be_underfilled"])

    def test_complete_underfilled_formats_include_default_count_in_partial_auto(self) -> None:
        for format_id in ("xpan", "120-66"):
            with self.subTest(format_id=format_id):
                spec = FORMATS[format_id]
                plan = count_hypothesis_plan(
                    strip_mode="partial",
                    requested_count=None,
                    fmt=spec,
                )
                counts = [hypothesis.count for hypothesis in plan.hypotheses]
                self.assertIn(spec.default_count, counts)

    def test_other_formats_do_not_include_default_count_in_partial_auto(self) -> None:
        for format_id in ("135", "half", "120-645", "120-67"):
            with self.subTest(format_id=format_id):
                spec = FORMATS[format_id]
                plan = count_hypothesis_plan(
                    strip_mode="partial",
                    requested_count=None,
                    fmt=spec,
                )
                counts = [hypothesis.count for hypothesis in plan.hypotheses]
                self.assertNotIn(spec.default_count, counts)


if __name__ == "__main__":
    unittest.main()
