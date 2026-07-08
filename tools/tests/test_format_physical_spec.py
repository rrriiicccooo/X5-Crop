from __future__ import annotations

import unittest

from x5crop.formats import CONTENT_ASPECTS_HORIZONTAL, FORMATS
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.reporting import detection_policy_report_detail


class FormatPhysicalSpecTests(unittest.TestCase):
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
                self.assertAlmostEqual(spec.frame_aspect, expected)
                self.assertAlmostEqual(
                    spec.nominal_frame_size_mm.width_mm / spec.nominal_frame_size_mm.height_mm,
                    expected,
                )

    def test_content_aspect_map_is_derived_from_format_specs(self) -> None:
        self.assertEqual(
            CONTENT_ASPECTS_HORIZONTAL,
            {format_id: spec.horizontal_content_aspect for format_id, spec in FORMATS.items()},
        )

    def test_medium_square_records_same_aspect_size_variant(self) -> None:
        spec = FORMATS["120-66"]
        self.assertEqual(
            [(item.width_mm, item.height_mm, item.label) for item in spec.frame_size_mm_options],
            [(56.0, 56.0, "nominal"), (54.0, 54.0, "camera_variant")],
        )
        self.assertTrue(
            all(item.aspect == spec.frame_aspect for item in spec.frame_size_mm_options)
        )

    def test_policy_report_exposes_physical_aspect_source(self) -> None:
        policy = get_detection_policy("half", "full")
        detail = detection_policy_report_detail(policy)
        physical = detail["physical"]

        self.assertEqual(physical["aspect_source"], "frame_size_mm")
        self.assertEqual(physical["nominal_frame_size_mm"]["width_mm"], 18.0)
        self.assertEqual(physical["nominal_frame_size_mm"]["height_mm"], 24.0)
        self.assertAlmostEqual(physical["frame_aspect"], 0.75)


if __name__ == "__main__":
    unittest.main()
