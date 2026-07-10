from __future__ import annotations

import unittest

import numpy as np

from x5crop.constants import GAP_DETECTED
from x5crop.detection.candidate.assessment.partial_holder import partial_edge_safety_assessment_detail
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.domain import Box, DetectionCandidate, Gap
from x5crop.formats import format_spec
from x5crop.policies.registry import get_detection_policy


def _complete_underfilled_medium_square_detection() -> DetectionCandidate:
    return DetectionCandidate(
        film_format="120-66",
        layout="horizontal",
        strip_mode="partial",
        count=3,
        outer=Box(0, 0, 360, 120),
        frames=[
            Box(30, 0, 130, 120),
            Box(140, 0, 240, 120),
            Box(250, 0, 350, 120),
        ],
        gaps=[
            Gap(1, 135.0, 1.0, GAP_DETECTED, 130.0, 140.0),
            Gap(2, 245.0, 1.0, GAP_DETECTED, 240.0, 250.0),
        ],
        confidence=0.90,
        detail={
            "width_cv": 0.0,
            "width_cv_source": "photo_edges",
            "photo_width_cv": 0.0,
            "photo_width_stability": {"used": True, "unstable": False},
            "outer_area_ratio": 0.80,
            "separator_width_evidence": {
                "used": True,
                "separator_width_gap_count": 0,
                "broad_separator_width_gaps": 0,
            },
        },
    )


class HolderOccupancyTests(unittest.TestCase):
    def test_default_count_partial_medium_square_can_be_complete_underfilled(self) -> None:
        detection = _complete_underfilled_medium_square_detection()
        content_containment = {
            "content_containment_ok": True,
            "content_integrity_failed": False,
        }

        evidence = holder_occupancy_evidence(
            detection,
            format_spec("120-66"),
            content_containment,
        )

        self.assertTrue(evidence["strip_frame_count_complete"])
        self.assertTrue(evidence["frame_sequence_complete"])
        self.assertEqual(evidence["occupancy_status"], "underfilled")
        self.assertTrue(evidence["complete_underfilled_strip"])
        self.assertEqual(
            evidence["holder_fill_ratio_role"],
            "occupancy_detail_not_candidate_gate_blocker",
        )

    def test_complete_underfilled_strip_does_not_require_holder_edge_width(self) -> None:
        detection = _complete_underfilled_medium_square_detection()
        policy = get_detection_policy("120-66", "partial")
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_integrity_failed": False,
            "frame_scores": [
                {"index": 1, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
                {"index": 2, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
                {"index": 3, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
            ],
        }
        occupancy = holder_occupancy_evidence(
            detection,
            format_spec("120-66"),
            content_detail,
        )

        detail = partial_edge_safety_assessment_detail(
            np.zeros((120, 360), dtype=np.uint8),
            detection,
            {"expected_gaps": 2, "hard_gaps": 2, "grid_gaps": 0, "equal_gaps": 0},
            content_detail,
            format_spec("120-66"),
            "separator",
            joint_score=0.90,
            content_score=0.90,
            geometry_score=0.90,
            holder_occupancy=occupancy,
            policy=policy,
        )

        self.assertTrue(detail["complete_underfilled_strip"])
        self.assertNotIn("holder_edge_disambiguation_weak", detail["disqualifiers"])
        self.assertIn(
            "holder_edge_disambiguation_not_required_for_complete_underfilled_strip",
            detail["occupancy_diagnostics"],
        )


if __name__ == "__main__":
    unittest.main()
