from __future__ import annotations

import unittest

from x5crop.formats import FORMATS, expected_separator_count
from x5crop.detection.candidate.plan.counts import count_hypothesis_plan
from x5crop.configuration.registry import get_detection_configuration
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.configuration.bundle import DetectionConfigurationBundle


class FormatSpecTests(unittest.TestCase):
    def test_format_factory_accepts_one_physical_size_source(self) -> None:
        import x5crop.formats as formats

        self.assertFalse(hasattr(formats, "_format_spec"))

    def test_physical_spec_and_report_exclude_unused_family_description(self) -> None:
        from x5crop.formats import FramePhysicalSpec, FrameSizeMm

        self.assertNotIn("family", FramePhysicalSpec.__dataclass_fields__)
        self.assertEqual(
            set(FrameSizeMm.__dataclass_fields__),
            {"width_mm", "height_mm"},
        )
        detail = detection_configuration_read_model(
            get_detection_configuration("135", "full")
        )
        self.assertNotIn("family", detail["physical"])

    def test_format_spec_is_a_typed_aggregate_without_flat_compatibility(self) -> None:
        from x5crop.formats import (
            FormatSpec,
            FramePhysicalSpec,
            ScanLayoutSpec,
            StripHandlingSpec,
        )

        self.assertEqual(set(FramePhysicalSpec.__dataclass_fields__), {"frame_size_mm_options"})
        self.assertEqual(
            set(StripHandlingSpec.__dataclass_fields__),
            {
                "default_count",
                "allowed_partial_counts",
                "complete_strip_can_be_underfilled",
            },
        )
        self.assertEqual(
            set(ScanLayoutSpec.__dataclass_fields__),
            {"kind", "lane_count", "lane_format_id"},
        )
        self.assertEqual(
            set(FormatSpec.__dataclass_fields__),
            {"format_id", "frame", "strip", "layout"},
        )
        for old_field in (
            "default_count",
            "allowed_counts",
            "allowed_partial_counts",
            "frame_size_mm_options",
            "physical_layout",
            "lane_count",
            "lane_format_id",
        ):
            self.assertFalse(hasattr(FORMATS["135"], old_field))

    def test_configuration_report_uses_physical_separator_count(self) -> None:
        for format_id, spec in FORMATS.items():
            for strip_mode in ("full", "partial"):
                with self.subTest(format_id=format_id, strip_mode=strip_mode):
                    configuration = get_detection_configuration(format_id, strip_mode)
                    detail = detection_configuration_read_model(configuration)
                    self.assertEqual(
                        detail["physical"]["expected_separator_count"],
                        expected_separator_count(spec.strip, spec.layout),
                    )

    def test_frame_aspects_are_derived_from_nominal_mm_size(self) -> None:
        expected_aspects = {
            "135": 36.0 / 24.0,
            "135-dual": 36.0 / 24.0,
            "half": 18.0 / 24.0,
            "xpan": 65.0 / 24.0,
            "120-645": 42.0 / 54.0,
            "120-66": 54.0 / 54.0,
            "120-67": 70.0 / 54.0,
        }

        for format_id, expected in expected_aspects.items():
            with self.subTest(format_id=format_id):
                spec = FORMATS[format_id]
                self.assertFalse(hasattr(spec, "horizontal_content_aspect"))
                self.assertAlmostEqual(
                    spec.frame.nominal_size_mm.width_mm
                    / spec.frame.nominal_size_mm.height_mm,
                    expected,
                )

    def test_dual_lane_composition_is_a_physical_format_fact(self) -> None:
        dual = FORMATS["135-dual"]
        self.assertEqual(dual.layout.kind, "dual_lane")
        self.assertEqual(dual.layout.lane_count, 2)
        self.assertEqual(dual.layout.lane_format_id, "135")

        for format_id, spec in FORMATS.items():
            if format_id == "135-dual":
                continue
            self.assertEqual(spec.layout.lane_count, 1)
            self.assertIsNone(spec.layout.lane_format_id)

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
            [(item.width_mm, item.height_mm) for item in spec.frame.frame_size_mm_options],
            [(54.0, 54.0), (56.0, 56.0)],
        )
        self.assertTrue(
            all(
                item.aspect == spec.frame.nominal_size_mm.aspect
                for item in spec.frame.frame_size_mm_options
            )
        )

    def test_all_120_formats_keep_discrete_54_and_56_short_axes(self) -> None:
        expected = {
            "120-645": ((42.0, 54.0), (42.0, 56.0)),
            "120-66": ((54.0, 54.0), (56.0, 56.0)),
            "120-67": ((70.0, 54.0), (70.0, 56.0)),
        }
        for format_id, sizes in expected.items():
            with self.subTest(format_id=format_id):
                self.assertEqual(
                    tuple(
                        (item.width_mm, item.height_mm)
                        for item in FORMATS[
                            format_id
                        ].frame.frame_size_mm_options
                    ),
                    sizes,
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
                    FORMATS[format_id].strip.complete_strip_can_be_underfilled,
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
                self.assertIn(spec.strip.default_count, counts)

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
                self.assertNotIn(spec.strip.default_count, counts)

    def test_partial_count_options_are_owned_only_by_strip_handling(self) -> None:
        expected = {
            "135": (1, 2, 3, 4, 5),
            "135-dual": (),
            "half": tuple(range(1, 12)),
            "xpan": (1, 2, 3),
            "120-645": (1, 2, 3),
            "120-66": (1, 2, 3),
            "120-67": (1, 2),
        }
        for format_id, allowed_partial_counts in expected.items():
            with self.subTest(format_id=format_id):
                self.assertEqual(
                    FORMATS[format_id].strip.allowed_partial_counts,
                    allowed_partial_counts,
                )

    def test_full_mode_cannot_override_nominal_strip_count(self) -> None:
        with self.assertRaises(ValueError):
            count_hypothesis_plan(
                strip_mode="full",
                requested_count=5,
                fmt=FORMATS["135"],
            )


if __name__ == "__main__":
    unittest.main()
