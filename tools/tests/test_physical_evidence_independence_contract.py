from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from x5crop.detection.candidate.assessment.evidence_independence import evidence_independence_detail
from x5crop.detection.candidate.assessment.partial_holder import partial_edge_safety_assessment_detail
from x5crop.detection.candidate.assessment.support_calibration import (
    separator_geometry_support_applies,
)
from x5crop.domain import Box, DetectionCandidate, Gap
from x5crop.formats import format_spec
from x5crop.gap_methods import GAP_DETECTED
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.runtime.candidate import EvidenceIndependencePolicy
from x5crop.policies.runtime.separator import SeparatorGeometrySupportModePolicy


class PhysicalEvidenceIndependenceContractTest(unittest.TestCase):
    def test_nearby_separator_diagnostics_separate_search_from_comparison_parameters(self) -> None:
        from inspect import signature

        from x5crop.detection.evidence.nearby_separator_diagnostics import (
            nearby_separator_diagnostic_detail,
        )

        parameters = signature(nearby_separator_diagnostic_detail).parameters
        self.assertIn("search_parameters", parameters)
        self.assertIn("comparison_parameters", parameters)
        self.assertNotIn("nearby_policy", parameters)

    def test_separator_width_variation_is_not_a_candidate_gate_requirement(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self.assertFalse(
            (
                project_root
                / "x5crop"
                / "detection"
                / "evidence"
                / "separator_width.py"
            ).exists()
        )
        banned = (
            "requires_broad_separator_width_gaps",
            "min_broad_separator_width_gaps",
            "edge_pair_min_score_without_broad_width",
            "edge_pair_min_score_with_broad_width",
            "separator_support_broad_width_support_assessment",
            "holder_edge_disambiguation_gaps",
        )
        offenders: list[str] = []
        for root in (
            project_root / "x5crop" / "detection" / "candidate",
            project_root / "x5crop" / "policies",
        ):
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(project_root)}:{term}")
        self.assertEqual(offenders, [])

    def test_partial_content_safety_checks_are_universal_for_standard_strips(self) -> None:
        from x5crop.formats import FORMATS
        from x5crop.policies.registry import get_detection_policy

        for spec in FORMATS.values():
            if spec.physical_layout != "single_strip":
                continue
            holder = get_detection_policy(
                spec.format_id,
                "partial",
            ).partial_holder
            self.assertTrue(holder.enabled)

    def test_partial_holder_does_not_treat_separator_width_as_edge_safety(self) -> None:
        policy = get_detection_policy("120-66", "partial")
        detection = DetectionCandidate(
            format_id="120-66",
            layout="horizontal",
            strip_mode="partial",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[
                Box(0, 0, 95, 100),
                Box(105, 0, 195, 100),
                Box(205, 0, 300, 100),
            ],
            gaps=[Gap(1, 100.0, 1.0, GAP_DETECTED, 95.0, 105.0)],
            confidence=0.90,
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "outer_area_ratio": 0.80,
            },
        )
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

        detail = partial_edge_safety_assessment_detail(
            np.zeros((100, 300), dtype=np.uint8),
            detection,
            {"expected_gaps": 2, "hard_gaps": 1, "grid_gaps": 1, "equal_gaps": 0},
            content_detail,
            "separator",
            joint_score=0.90,
            content_score=0.10,
            geometry_score=0.90,
            holder_occupancy={"complete_underfilled_strip": False, "strip_completeness": {}},
            cache=None,
            policy=policy,
        )

        self.assertNotIn("holder_edge_disambiguation_weak", detail["disqualifiers"])
        self.assertNotIn("content_score_low", detail["disqualifiers"])
        self.assertNotIn("holder_edge_disambiguation", detail)
        self.assertEqual(
            detail["content_quality"]["role"],
            "quality_diagnostic_not_boundary_evidence",
        )
        self.assertFalse(detail["content_quality"]["quality_ok"])

    def test_evidence_independence_treats_content_score_as_quality_detail(self) -> None:
        detection = DetectionCandidate(
            format_id="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[
                Box(0, 0, 95, 100),
                Box(105, 0, 195, 100),
                Box(205, 0, 300, 100),
            ],
            gaps=[
                Gap(1, 100.0, 1.0, GAP_DETECTED, 95.0, 105.0),
                Gap(2, 200.0, 1.0, GAP_DETECTED, 195.0, 205.0),
            ],
            confidence=0.90,
            detail={
                "outer_candidate_strategy": "separator_outer",
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "standard_gap_search": {
                    "entries": [
                        {"selected_source": "standard_detected"},
                        {"selected_source": "observed_width_profile"},
                    ],
                },
            },
        )

        detail = evidence_independence_detail(
            detection,
            source="separator",
            content_support="ok",
            content_score=0.10,
            geometry_score=0.90,
            policy=EvidenceIndependencePolicy(),
        )

        self.assertTrue(detail["requires_validation"])
        self.assertTrue(detail["content_ok"])
        self.assertFalse(detail["content_quality_ok"])
        self.assertEqual(detail["content_score_role"], "quality_diagnostic_not_boundary_evidence")
        self.assertTrue(detail["ok"])

    def test_frame_box_width_detail_does_not_validate_evidence_independence(self) -> None:
        detection = DetectionCandidate(
            format_id="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[
                Box(0, 0, 80, 100),
                Box(95, 0, 205, 100),
                Box(220, 0, 300, 100),
            ],
            gaps=[
                Gap(1, 100.0, 1.0, GAP_DETECTED, 95.0, 105.0),
                Gap(2, 200.0, 1.0, GAP_DETECTED, 195.0, 205.0),
            ],
            confidence=0.90,
            detail={
                "outer_candidate_strategy": "separator_outer",
                "width_cv": 0.0,
                "width_cv_source": "frame_boxes",
                "standard_gap_search": {
                    "entries": [
                        {"selected_source": "standard_detected"},
                        {"selected_source": "observed_width_profile"},
                    ],
                },
            },
        )

        detail = evidence_independence_detail(
            detection,
            source="separator",
            content_support="ok",
            content_score=0.90,
            geometry_score=0.90,
            policy=EvidenceIndependencePolicy(),
        )

        self.assertTrue(detail["requires_validation"])
        self.assertFalse(detail["ok"])
        self.assertFalse(detail["photo_width_stability"]["used"])
        self.assertEqual(detail["photo_width_stability"]["role"], "diagnostic_until_photo_edges")

    def test_geometry_support_checks_only_photo_edge_width_when_available(self) -> None:
        fmt = format_spec("120-66")
        hard_detail = {"expected_gaps": 2, "hard_gaps": 2, "grid_gaps": 0, "equal_gaps": 0}
        mode_policy = SeparatorGeometrySupportModePolicy(
            min_hard_ratio=0.50,
            max_equal_gaps=0,
            required_content_support="ok",
            min_joint_score=0.70,
            max_photo_width_cv=0.040,
            max_outer_area_ratio=0.99,
        )
        frame_box_detail_candidate = DetectionCandidate(
            format_id="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[
                Box(0, 0, 80, 100),
                Box(95, 0, 205, 100),
                Box(220, 0, 300, 100),
            ],
            gaps=[],
            confidence=0.90,
            detail={
                "width_cv": 0.20,
                "width_cv_source": "frame_boxes",
                "outer_area_ratio": 0.80,
            },
        )
        unstable_photo_candidate = DetectionCandidate(
            format_id="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=frame_box_detail_candidate.frames,
            gaps=[],
            confidence=0.90,
            detail={
                "width_cv": 0.20,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.20,
                "outer_area_ratio": 0.80,
            },
        )

        self.assertTrue(
            separator_geometry_support_applies(
                frame_box_detail_candidate,
                hard_detail,
                fmt,
                "separator",
                "ok",
                0.90,
                mode_policy,
            )
        )
        self.assertFalse(
            separator_geometry_support_applies(
                unstable_photo_candidate,
                hard_detail,
                fmt,
                "separator",
                "ok",
                0.90,
                mode_policy,
            )
        )

    def test_partial_holder_does_not_treat_frame_box_width_as_photo_instability(self) -> None:
        policy = get_detection_policy("120-66", "partial")
        detection = DetectionCandidate(
            format_id="120-66",
            layout="horizontal",
            strip_mode="partial",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[
                Box(0, 0, 80, 100),
                Box(95, 0, 205, 100),
                Box(220, 0, 300, 100),
            ],
            gaps=[
                Gap(1, 87.5, 1.0, GAP_DETECTED, 80.0, 95.0),
                Gap(2, 212.5, 1.0, GAP_DETECTED, 205.0, 220.0),
            ],
            confidence=0.90,
            detail={
                "width_cv": 0.20,
                "width_cv_source": "frame_boxes",
                "outer_area_ratio": 0.80,
            },
        )
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

        detail = partial_edge_safety_assessment_detail(
            np.zeros((100, 300), dtype=np.uint8),
            detection,
            {"expected_gaps": 2, "hard_gaps": 2, "grid_gaps": 0, "equal_gaps": 0},
            content_detail,
            "separator",
            joint_score=0.90,
            content_score=0.90,
            geometry_score=0.90,
            holder_occupancy={"complete_underfilled_strip": False, "strip_completeness": {}},
            cache=None,
            policy=policy,
        )

        self.assertNotIn("photo_width_unstable", detail["disqualifiers"])
        self.assertEqual(detail["photo_width_stability"]["role"], "diagnostic_until_photo_edges")


if __name__ == "__main__":
    unittest.main()
