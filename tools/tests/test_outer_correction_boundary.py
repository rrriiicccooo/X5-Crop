from __future__ import annotations

import unittest

from x5crop.detection.candidate.extension.outer_correction import _outer_correction_plan_detail
from x5crop.domain import Box, Detection
from x5crop.policies.registry import get_detection_policy


def _detection(strip_mode: str, *, source: str = "separator", hard_ok: bool = True) -> Detection:
    return Detection(
        film_format="120-66",
        layout="horizontal",
        strip_mode=strip_mode,
        count=3,
        outer=Box(0, 0, 300, 100),
        frames=[],
        gaps=[],
        confidence=0.0,
        review_reasons=[],
        detail={
            "candidate_assessment": {
                "source": source,
                "separator_support": {"ok": hard_ok},
            }
        },
    )


class OuterCorrectionBoundaryTest(unittest.TestCase):
    def test_full_separator_candidate_can_enter_all_correction_families(self) -> None:
        policy = get_detection_policy("120-66", "full")
        detail = _outer_correction_plan_detail(_detection("full"), policy, explicit_count=True)

        self.assertEqual(detail["eligibility_owner"], "candidate.extension")
        self.assertEqual(
            set(detail["eligible_families"]),
            {"long_axis_geometry", "short_axis_geometry", "content_containment"},
        )
        self.assertEqual(detail["skipped_reasons"], {})

    def test_partial_explicit_count_can_enter_all_correction_families(self) -> None:
        policy = get_detection_policy("120-66", "partial")
        detail = _outer_correction_plan_detail(_detection("partial"), policy, explicit_count=True)

        self.assertEqual(
            set(detail["eligible_families"]),
            {"long_axis_geometry", "short_axis_geometry", "content_containment"},
        )

    def test_partial_auto_count_blocks_correction_in_candidate_extension(self) -> None:
        policy = get_detection_policy("120-66", "partial")
        detail = _outer_correction_plan_detail(_detection("partial"), policy, explicit_count=False)

        self.assertEqual(detail["eligible_families"], [])
        self.assertEqual(
            set(detail["skipped_reasons"].values()),
            {"partial_requires_explicit_count"},
        )

    def test_content_candidate_is_blocked_before_physical_correction(self) -> None:
        policy = get_detection_policy("120-66", "full")
        detail = _outer_correction_plan_detail(
            _detection("full", source="content"),
            policy,
            explicit_count=True,
        )

        self.assertEqual(detail["eligible_families"], [])
        self.assertEqual(
            set(detail["skipped_reasons"].values()),
            {"requires_separator_assessment"},
        )

    def test_short_axis_requires_hard_separator_evidence_in_candidate_extension(self) -> None:
        policy = get_detection_policy("120-66", "full")
        detail = _outer_correction_plan_detail(
            _detection("full", hard_ok=False),
            policy,
            explicit_count=True,
        )

        self.assertIn("long_axis_geometry", detail["eligible_families"])
        self.assertIn("content_containment", detail["eligible_families"])
        self.assertNotIn("short_axis_geometry", detail["eligible_families"])
        self.assertEqual(
            detail["skipped_reasons"].get("short_axis_geometry"),
            "requires_separator_support",
        )


if __name__ == "__main__":
    unittest.main()
