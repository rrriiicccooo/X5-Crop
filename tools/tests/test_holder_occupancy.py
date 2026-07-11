from __future__ import annotations

import unittest

import numpy as np

from x5crop.constants import GAP_DETECTED
from x5crop.detection.candidate.assessment.partial_holder import partial_edge_safety_assessment_detail
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.state import EvidenceState
from x5crop.domain import Box, DetectionCandidate, Gap
from x5crop.formats import format_spec
from x5crop.policies.registry import get_detection_policy


def _complete_underfilled_medium_square_detection() -> DetectionCandidate:
    return DetectionCandidate(
        format_id="120-66",
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
        },
    )


def _complete_frame_coverage() -> FrameCoverageEvidence:
    return FrameCoverageEvidence(
        state=EvidenceState.SUPPORTED,
        reason="content_runs_covered",
        holder_interval=(0, 360),
        film_interval=(30, 350),
        frame_intervals=((30, 130), (140, 240), (250, 350)),
        content_runs=((30, 350),),
        uncovered_content=(),
    )


class HolderOccupancyTests(unittest.TestCase):
    def test_default_count_partial_medium_square_can_be_complete_underfilled(self) -> None:
        detection = _complete_underfilled_medium_square_detection()
        frame_content_support = {
            "frame_content_support_available": True,
        }

        evidence = holder_occupancy_evidence(
            detection,
            format_spec("120-66"),
            frame_content_support,
            frame_coverage=_complete_frame_coverage(),
        )

        self.assertTrue(evidence["strip_frame_count_complete"])
        self.assertTrue(evidence["frame_sequence_complete"])
        self.assertEqual(evidence["occupancy_status"], "underfilled")
        self.assertTrue(evidence["complete_underfilled_strip"])

    def test_complete_underfilled_strip_uses_the_same_partial_safety_contract(self) -> None:
        detection = _complete_underfilled_medium_square_detection()
        policy = get_detection_policy("120-66", "partial")
        content_detail = {
            "used": True,
            "support": "ok",
            "frame_content_support_available": True,
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
            frame_coverage=_complete_frame_coverage(),
        )

        detail = partial_edge_safety_assessment_detail(
            np.zeros((120, 360), dtype=np.uint8),
            detection,
            {"expected_gaps": 2, "hard_gaps": 2, "grid_gaps": 0, "equal_gaps": 0},
            content_detail,
            "separator",
            holder_occupancy=occupancy,
            cache=None,
            policy=policy,
        )

        self.assertTrue(detail["complete_underfilled_strip"])
        self.assertEqual(detail["state"], "supported")
        self.assertEqual(detail["preservation_failures"], [])

    def test_low_content_and_empty_frames_do_not_create_content_harm(self) -> None:
        detection = _complete_underfilled_medium_square_detection()
        policy = get_detection_policy("120-66", "partial")

        detail = partial_edge_safety_assessment_detail(
            np.zeros((120, 360), dtype=np.uint8),
            detection,
            {"expected_gaps": 2, "hard_gaps": 2, "grid_gaps": 0, "equal_gaps": 0},
            {
                "used": True,
                "support": "low_content",
                "frame_content_support_available": False,
                "frame_scores": [],
            },
            "separator",
            holder_occupancy={},
            cache=None,
            policy=policy,
        )

        self.assertEqual(detail["state"], "supported")
        self.assertEqual(detail["preservation_failures"], [])
        self.assertIn(
            "partial_frame_content_measurement_unavailable",
            detail["occupancy_diagnostics"],
        )


if __name__ == "__main__":
    unittest.main()
