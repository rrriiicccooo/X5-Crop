from pathlib import Path
import unittest

import numpy as np

from x5crop.detection.candidate.assessment.candidate import apply_candidate_assessment_policy
from x5crop.detection.candidate.assessment.base_scoring import base_detection_assessment
from x5crop.detection.candidate.assessment.scoring import (
    content_quality_score,
    content_support_score,
    geometry_support_score,
)
from x5crop.detection.decision.evidence_summary import evidence_summary_for
from x5crop.domain import Box, DetectionCandidate, Gap
from x5crop.formats import format_spec
from x5crop.gap_methods import GAP_DETECTED
from x5crop.policies.decision.contract import decision_contract_for_policy
from x5crop.policies.registry import get_detection_policy
from x5crop.run_config import RunConfig


class CandidateLifecycleScoringContractTest(unittest.TestCase):
    def _decision_contract(self, format_id: str, strip_mode: str):
        return decision_contract_for_policy(get_detection_policy(format_id, strip_mode))

    def test_large_outer_area_is_not_a_hard_reason_by_itself(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        gray[:, ::2] = 255
        outer = Box(0, 0, 100, 100)
        gaps = [
            Gap(1, 32.0, 1.0, GAP_DETECTED, 28.0, 36.0),
            Gap(2, 68.0, 1.0, GAP_DETECTED, 64.0, 72.0),
        ]
        boxes = [
            Box(0, 0, 28, 100),
            Box(36, 0, 64, 100),
            Box(72, 0, 100, 100),
        ]

        assessment = base_detection_assessment(
            gray,
            outer,
            gaps,
            boxes,
            3,
            format_spec("120-645"),
            "full",
            get_detection_policy("120-645", "full"),
            origin=0.0,
            pitch=100.0 / 3.0,
        )

        self.assertGreater(assessment.confidence, 0.82)
        self.assertNotIn("outer_overcontains_holder_area", assessment.candidate_signals)
        self.assertNotIn("outer_scope_uncertain", assessment.candidate_signals)
        self.assertEqual(assessment.detail["outer_area_profile"]["status"], "above_profile")
        self.assertEqual(assessment.detail["outer_area_profile"]["role"], "diagnostic_until_final_alignment")

    def test_raw_outer_area_does_not_change_base_confidence(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        gray[:, ::2] = 255
        gaps = [
            Gap(1, 32.0, 1.0, GAP_DETECTED, 28.0, 36.0),
            Gap(2, 68.0, 1.0, GAP_DETECTED, 64.0, 72.0),
        ]
        boxes = [
            Box(0, 0, 28, 100),
            Box(36, 0, 64, 100),
            Box(72, 0, 100, 100),
        ]
        fmt = format_spec("120-645")

        profile_assessment = base_detection_assessment(
            gray,
            Box(0, 0, 90, 100),
            gaps,
            boxes,
            3,
            fmt,
            "full",
            get_detection_policy("120-645", "full"),
            origin=0.0,
            pitch=100.0 / 3.0,
        )
        overcut_assessment = base_detection_assessment(
            gray,
            Box(0, 0, 100, 100),
            gaps,
            boxes,
            3,
            fmt,
            "full",
            get_detection_policy("120-645", "full"),
            origin=0.0,
            pitch=100.0 / 3.0,
        )

        self.assertEqual(profile_assessment.detail["outer_area_profile"]["status"], "ok")
        self.assertEqual(overcut_assessment.detail["outer_area_profile"]["status"], "above_profile")
        self.assertAlmostEqual(profile_assessment.confidence, overcut_assessment.confidence)

    def test_frame_box_width_detail_does_not_act_as_photo_width_evidence(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        gray[:, ::2] = 255
        outer = Box(0, 0, 100, 100)
        gaps = [
            Gap(1, 32.0, 1.0, GAP_DETECTED, 28.0, 36.0),
            Gap(2, 68.0, 1.0, GAP_DETECTED, 64.0, 72.0),
        ]
        boxes = [
            Box(0, 0, 12, 100),
            Box(36, 0, 88, 100),
            Box(92, 0, 100, 100),
        ]

        assessment = base_detection_assessment(
            gray,
            outer,
            gaps,
            boxes,
            3,
            format_spec("120-645"),
            "full",
            get_detection_policy("120-645", "full"),
        )

        self.assertGreater(assessment.confidence, 0.82)
        self.assertEqual(assessment.detail["width_cv_source"], "frame_boxes")
        self.assertFalse(assessment.detail["photo_width_stability"]["used"])
        self.assertEqual(assessment.detail["photo_width_stability"]["role"], "diagnostic_until_photo_edges")
        self.assertNotIn("photo_width_unstable", assessment.candidate_signals)

    def test_low_global_contrast_is_image_quality_detail_not_crop_failure(self) -> None:
        gray = np.full((100, 100), 128, dtype=np.uint8)
        outer = Box(0, 0, 100, 100)
        gaps = [
            Gap(1, 32.0, 1.0, GAP_DETECTED, 28.0, 36.0),
            Gap(2, 68.0, 1.0, GAP_DETECTED, 64.0, 72.0),
        ]
        boxes = [
            Box(0, 0, 28, 100),
            Box(36, 0, 64, 100),
            Box(72, 0, 100, 100),
        ]

        assessment = base_detection_assessment(
            gray,
            outer,
            gaps,
            boxes,
            3,
            format_spec("120-645"),
            "full",
            get_detection_policy("120-645", "full"),
            origin=0.0,
            pitch=100.0 / 3.0,
        )

        self.assertGreater(assessment.confidence, 0.82)
        self.assertNotIn("low_contrast", assessment.candidate_signals)
        self.assertFalse(assessment.detail["image_quality"]["contrast_ok"])
        self.assertEqual(assessment.detail["image_quality"]["role"], "diagnostic_not_crop_boundary")

    def test_content_score_measures_containment_before_content_quality(self) -> None:
        policy = get_detection_policy("120-66", "full").content
        containment = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_integrity_failed": False,
            "median_mean": 0.01,
            "median_coverage": 0.02,
            "max_aspect_error": None,
        }

        self.assertEqual(
            content_support_score(containment),
            1.0,
        )
        self.assertLess(
            content_quality_score(containment, policy),
            0.40,
        )

    def test_content_support_score_uses_containment_instead_of_support_summary(self) -> None:
        policy = get_detection_policy("120-66", "full").content
        containment = {
            "used": True,
            "support": "ok",
            "content_containment_ok": False,
            "content_integrity_failed": True,
            "median_mean": 0.20,
            "median_coverage": 0.40,
            "max_aspect_error": 0.40,
        }

        self.assertEqual(
            content_support_score(containment),
            0.0,
        )

    def test_broad_separator_width_does_not_cap_confidence_by_itself(self) -> None:
        gray = np.zeros((100, 300), dtype=np.uint8)
        gray[:, ::2] = 255
        policy = get_detection_policy("120-66", "full")
        detection = DetectionCandidate(
            film_format="120-66",
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
            confidence=0.99,
            detail={
                "outer_candidate_strategy": "base_outer",
                "outer_area_ratio": 0.80,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "broad_separator_width_gaps": 2,
                "standard_gap_search": {
                    "entries": [
                        {"selected_source": "standard_detected"},
                        {"selected_source": "standard_detected"},
                    ],
                },
            },
        )
        config = RunConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            film_format="120-66",
            layout_auto=False,
            layout="horizontal",
            strip_mode="full",
            requested_count=3,
            page=0,
            bleed_x=0,
            bleed_y=0,
            deskew="off",
            deskew_fallback="off",
            deskew_min_angle=-2.0,
            deskew_max_angle=2.0,
            confidence_threshold=0.85,
            review_dir=None,
            copy_review_files=False,
            export_review=False,
            compression="none",
            debug=False,
            debug_analysis=False,
            dry_run=True,
            diagnostics=False,
            overwrite=True,
            report=False,
            debug_errors=False,
            reuse_analysis=False,
            jobs=1,
        )

        assessed = apply_candidate_assessment_policy(
            gray,
            detection,
            config,
            format_spec("120-66"),
            "separator",
            policy=policy,
        )

        self.assertGreater(assessed.confidence, 0.95)
        assessment = assessed.detail["candidate_assessment"]
        self.assertTrue(assessment["candidate_gate"]["passed"])
        self.assertEqual(
            assessed.detail["candidate_assessment"]["separator_support"][
                "broad_separator_width_gaps"
            ],
            2,
        )

    def test_safe_outer_overcut_and_low_content_quality_do_not_fail_final_evidence(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 100, 100),
            frames=[
                Box(0, 0, 30, 100),
                Box(36, 0, 63, 100),
                Box(69, 0, 100, 100),
            ],
            gaps=[
                Gap(1, 33.0, 1.0, GAP_DETECTED, 30.0, 36.0),
                Gap(2, 66.0, 1.0, GAP_DETECTED, 63.0, 69.0),
            ],
            confidence=0.90,
            detail={
                "outer_area_ratio": 1.0,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "candidate_assessment": {
                    "geometry_score": 0.95,
                    "content_score": 0.10,
                    "source": "separator",
                },
            },
        )
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_integrity_failed": False,
            "content_quality_score": 0.10,
        }
        outer_alignment = {
            "used": True,
            "ok": True,
            "overcontainment_allowed": True,
            "overcontains_long_axis": True,
            "reason": "ok",
        }

        evidence = evidence_summary_for(
            gray,
            detection,
            content_detail,
            outer_alignment,
            self._decision_contract("120-66", "full"),
        )

        self.assertTrue(evidence["outer"]["ok"])
        self.assertTrue(evidence["outer"]["safe_overcut_allowed"])
        self.assertFalse(evidence["outer"]["area_ok"])
        self.assertTrue(evidence["content"]["ok"])
        self.assertFalse(evidence["content"]["quality_ok"])
        self.assertEqual(
            evidence["content"]["content_quality_score_role"],
            "quality_diagnostic_not_boundary_evidence",
        )

    def test_geometry_support_score_does_not_penalize_raw_outer_area(self) -> None:
        frames = [
            Box(0, 0, 95, 100),
            Box(105, 0, 195, 100),
            Box(205, 0, 300, 100),
        ]
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_integrity_failed": False,
            "max_aspect_error": 0.0,
        }
        profile_outer = DetectionCandidate(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=frames,
            gaps=[],
            confidence=0.90,
            detail={
                "outer_area_ratio": 0.80,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            },
        )
        overcut_outer = DetectionCandidate(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=frames,
            gaps=[],
            confidence=0.90,
            detail={
                "outer_area_ratio": 1.0,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            },
        )

        self.assertAlmostEqual(
            geometry_support_score(profile_outer, content_detail, get_detection_policy("120-66", "full")),
            geometry_support_score(overcut_outer, content_detail, get_detection_policy("120-66", "full")),
        )

    def test_geometry_support_score_does_not_penalize_missing_aspect_evidence(self) -> None:
        detection = DetectionCandidate(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[
                Box(0, 0, 95, 100),
                Box(105, 0, 195, 100),
                Box(205, 0, 300, 100),
            ],
            gaps=[],
            confidence=0.90,
            detail={
                "outer_area_ratio": 1.0,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            },
        )

        self.assertEqual(
            geometry_support_score(
                detection,
                {"used": False, "support": "unknown"},
                get_detection_policy("120-66", "full"),
            ),
            1.0,
        )

    def test_final_evidence_does_not_gate_on_frame_box_width_detail(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 100, 100),
            frames=[
                Box(0, 0, 12, 100),
                Box(36, 0, 88, 100),
                Box(92, 0, 100, 100),
            ],
            gaps=[
                Gap(1, 32.0, 1.0, GAP_DETECTED, 28.0, 36.0),
                Gap(2, 68.0, 1.0, GAP_DETECTED, 64.0, 72.0),
            ],
            confidence=0.90,
            detail={
                "outer_area_ratio": 0.80,
                "width_cv": 0.20,
                "width_cv_source": "frame_boxes",
                "candidate_assessment": {
                    "geometry_score": 0.95,
                    "content_score": 0.95,
                    "source": "separator",
                },
            },
        )
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_integrity_failed": False,
            "content_quality_score": 0.95,
        }

        evidence = evidence_summary_for(
            gray,
            detection,
            content_detail,
            {"used": True, "ok": True, "reason": "ok"},
            self._decision_contract("120-66", "full"),
        )

        self.assertTrue(evidence["geometry"]["ok"])
        self.assertFalse(evidence["geometry"]["photo_width_stability"]["used"])
        self.assertEqual(
            evidence["geometry"]["photo_width_stability"]["role"],
            "diagnostic_until_photo_edges",
        )



if __name__ == "__main__":
    unittest.main()
