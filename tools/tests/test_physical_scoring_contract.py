from pathlib import Path
import unittest

import numpy as np

from x5crop.detection.candidate.assessment.candidate import apply_candidate_assessment_policy
from x5crop.detection.candidate.assessment.base_scoring import base_detection_assessment
from x5crop.detection.candidate.assessment.evidence_independence import evidence_independence_detail
from x5crop.detection.candidate.assessment.gate_support import (
    hard_full_calibration_floor_applies,
    separator_geometry_support_applies,
)
from x5crop.detection.candidate.assessment.partial_holder import partial_extra_holder_frames_gate_detail
from x5crop.detection.candidate.assessment.scoring import (
    content_quality_score,
    content_support_score,
    geometry_support_score,
)
from x5crop.detection.decision.pass_review import evidence_summary_for
from x5crop.detection.evidence.risk import lucky_photo_width_instability_components
from x5crop.detection.guidance.content_model import content_candidate_confidence_and_reasons
from x5crop.domain import Box, Detection, Gap
from x5crop.formats import format_spec
from x5crop.gap_methods import GAP_DETECTED
from x5crop.policies.decision.contract import decision_contract_for
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.runtime.candidate import EvidenceIndependencePolicy
from x5crop.policies.runtime.diagnostics import LuckyPassRiskPolicy
from x5crop.policies.runtime.separator import SeparatorGeometrySupportModePolicy
from x5crop.runtime.config import RuntimeConfig


class PhysicalScoringContractTest(unittest.TestCase):
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

        confidence, reasons, detail = base_detection_assessment(
            gray,
            outer,
            gaps,
            boxes,
            3,
            format_spec("120-645"),
            "full",
            origin=0.0,
            pitch=100.0 / 3.0,
        )

        self.assertGreater(confidence, 0.82)
        self.assertNotIn("outer_box_too_large", reasons)
        self.assertNotIn("outer_box_uncertain", reasons)
        self.assertEqual(detail["outer_area_profile"]["status"], "above_profile")
        self.assertEqual(detail["outer_area_profile"]["role"], "diagnostic_until_final_alignment")

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

        profile_confidence, _, profile_detail = base_detection_assessment(
            gray,
            Box(0, 0, 90, 100),
            gaps,
            boxes,
            3,
            fmt,
            "full",
            origin=0.0,
            pitch=100.0 / 3.0,
        )
        overcut_confidence, _, overcut_detail = base_detection_assessment(
            gray,
            Box(0, 0, 100, 100),
            gaps,
            boxes,
            3,
            fmt,
            "full",
            origin=0.0,
            pitch=100.0 / 3.0,
        )

        self.assertEqual(profile_detail["outer_area_profile"]["status"], "ok")
        self.assertEqual(overcut_detail["outer_area_profile"]["status"], "above_profile")
        self.assertAlmostEqual(profile_confidence, overcut_confidence)

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

        confidence, reasons, detail = base_detection_assessment(
            gray,
            outer,
            gaps,
            boxes,
            3,
            format_spec("120-645"),
            "full",
        )

        self.assertGreater(confidence, 0.82)
        self.assertEqual(detail["width_cv_source"], "frame_boxes")
        self.assertFalse(detail["photo_width_stability"]["used"])
        self.assertEqual(detail["photo_width_stability"]["role"], "diagnostic_until_photo_edges")
        self.assertNotIn("photo_width_unstable", reasons)

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

        confidence, reasons, detail = base_detection_assessment(
            gray,
            outer,
            gaps,
            boxes,
            3,
            format_spec("120-645"),
            "full",
            origin=0.0,
            pitch=100.0 / 3.0,
        )

        self.assertGreater(confidence, 0.82)
        self.assertNotIn("low_contrast", reasons)
        self.assertFalse(detail["image_quality"]["contrast_ok"])
        self.assertEqual(detail["image_quality"]["role"], "diagnostic_not_crop_gate")

    def test_content_score_measures_containment_before_content_quality(self) -> None:
        policy = get_detection_policy("120-66", "full").content
        containment = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_harm_risk": False,
            "median_mean": 0.01,
            "median_coverage": 0.02,
            "max_aspect_error": None,
        }

        self.assertEqual(
            content_support_score(containment, "120-66", policy),
            1.0,
        )
        self.assertLess(
            content_quality_score(containment, "120-66", policy),
            0.40,
        )

    def test_content_support_score_uses_containment_instead_of_support_summary(self) -> None:
        policy = get_detection_policy("120-66", "full").content
        containment = {
            "used": True,
            "support": "ok",
            "content_containment_ok": False,
            "content_harm_risk": True,
            "median_mean": 0.20,
            "median_coverage": 0.40,
            "max_aspect_error": 0.40,
        }

        self.assertEqual(
            content_support_score(containment, "120-66", policy),
            0.0,
        )

    def test_broad_separator_width_does_not_cap_confidence_by_itself(self) -> None:
        gray = np.zeros((100, 300), dtype=np.uint8)
        gray[:, ::2] = 255
        policy = get_detection_policy("120-66", "full")
        detection = Detection(
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
            review_reasons=[],
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
        config = RuntimeConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            film_format="120-66",
            layout_auto=False,
            layout="horizontal",
            strip_mode="full",
            count=3,
            count_override=3,
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
        self.assertTrue(assessed.detail["candidate_assessment"]["auto_gate"])
        self.assertEqual(
            assessed.detail["candidate_assessment"]["separator_hard_evidence"][
                "broad_separator_width_gaps"
            ],
            2,
        )

    def test_partial_three_frame_hard_separator_is_not_intrinsically_ambiguous(self) -> None:
        gray = np.zeros((100, 300), dtype=np.uint8)
        gray[:, ::2] = 255
        confidence, reasons, detail = base_detection_assessment(
            gray,
            Box(0, 0, 300, 100),
            [
                Gap(1, 100.0, 1.0, GAP_DETECTED, 95.0, 105.0),
                Gap(2, 200.0, 1.0, GAP_DETECTED, 195.0, 205.0),
            ],
            [
                Box(0, 0, 95, 100),
                Box(105, 0, 195, 100),
                Box(205, 0, 300, 100),
            ],
            3,
            format_spec("135"),
            "partial",
        )

        self.assertGreater(confidence, 0.90)
        self.assertNotIn("partial_strip_count_candidate", reasons)
        self.assertNotIn("partial_too_ambiguous", reasons)
        self.assertEqual(detail["partial_count_assessment"]["reason"], "enough_frames_for_physical_assessment")

    def test_partial_single_frame_remains_intrinsically_ambiguous(self) -> None:
        gray = np.zeros((100, 120), dtype=np.uint8)
        gray[:, ::2] = 255
        confidence, reasons, detail = base_detection_assessment(
            gray,
            Box(0, 0, 120, 100),
            [],
            [Box(0, 0, 120, 100)],
            1,
            format_spec("135"),
            "partial",
        )

        self.assertLessEqual(
            confidence,
            get_detection_policy("135", "partial").scoring.base_detection.partial_one_cap,
        )
        self.assertIn("partial_too_ambiguous", reasons)
        self.assertNotIn("partial_strip_count_candidate", reasons)
        self.assertEqual(detail["partial_count_assessment"]["reason"], "single_frame_partial")

    def test_content_partial_candidate_does_not_emit_partial_count_reason(self) -> None:
        _confidence, reasons, detail = content_candidate_confidence_and_reasons(
            placement="content_runs",
            runs_count=3,
            selected_run_count=3,
            count=3,
            strip_mode="partial",
            median_mean=0.20,
            median_coverage=0.40,
            max_aspect_error=0.01,
            confidence_threshold=0.85,
            candidate_policy=get_detection_policy("135", "partial").content.candidate,
        )

        self.assertNotIn("partial_strip_count_candidate", reasons)
        self.assertEqual(detail["partial_candidate_role"], "content_guidance_not_count_risk")

    def test_safe_outer_overcut_and_low_content_quality_do_not_fail_final_evidence(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = Detection(
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
            review_reasons=[],
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
            "content_harm_risk": False,
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
            decision_contract_for("120-66", "full"),
        )

        self.assertTrue(evidence["outer"]["ok"])
        self.assertTrue(evidence["outer"]["safe_overcut_allowed"])
        self.assertFalse(evidence["outer"]["area_ok"])
        self.assertTrue(evidence["content"]["ok"])
        self.assertFalse(evidence["content"]["quality_ok"])
        self.assertEqual(evidence["content"]["score_role"], "quality_diagnostic_not_hard_gate")

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
            "content_harm_risk": False,
            "max_aspect_error": 0.0,
        }
        profile_outer = Detection(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=frames,
            gaps=[],
            confidence=0.90,
            review_reasons=[],
            detail={
                "outer_area_ratio": 0.80,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            },
        )
        overcut_outer = Detection(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=frames,
            gaps=[],
            confidence=0.90,
            review_reasons=[],
            detail={
                "outer_area_ratio": 1.0,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            },
        )

        self.assertAlmostEqual(
            geometry_support_score(profile_outer, content_detail),
            geometry_support_score(overcut_outer, content_detail),
        )

    def test_geometry_support_score_does_not_penalize_missing_aspect_evidence(self) -> None:
        detection = Detection(
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
            review_reasons=[],
            detail={
                "outer_area_ratio": 1.0,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            },
        )

        self.assertEqual(
            geometry_support_score(detection, {"used": False, "support": "unknown"}),
            1.0,
        )

    def test_final_evidence_does_not_gate_on_frame_box_width_detail(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = Detection(
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
            review_reasons=[],
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
            "content_harm_risk": False,
            "content_quality_score": 0.95,
        }

        evidence = evidence_summary_for(
            gray,
            detection,
            content_detail,
            {"used": True, "ok": True, "reason": "ok"},
            decision_contract_for("120-66", "full"),
        )

        self.assertTrue(evidence["geometry"]["ok"])
        self.assertFalse(evidence["geometry"]["photo_width_stability"]["used"])
        self.assertEqual(
            evidence["geometry"]["photo_width_stability"]["role"],
            "diagnostic_until_photo_edges",
        )

    def test_lucky_pass_photo_width_instability_requires_photo_edge_width_source(self) -> None:
        policy = LuckyPassRiskPolicy()

        frame_box_components, frame_box_detail = lucky_photo_width_instability_components(
            0.020,
            "frame_boxes",
            policy,
        )
        photo_components, photo_detail = lucky_photo_width_instability_components(
            0.020,
            "photo_edges",
            policy,
        )

        self.assertEqual(frame_box_components, {})
        self.assertFalse(frame_box_detail["used"])
        self.assertEqual(frame_box_detail["reason"], "photo_width_source_not_photo_edges")
        self.assertIn("unstable_photo_widths", photo_components)
        self.assertTrue(photo_detail["used"])

    def test_partial_holder_uses_holder_edge_disambiguation_reason(self) -> None:
        policy = get_detection_policy("120-66", "partial")
        detection = Detection(
            film_format="120-66",
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
            review_reasons=[],
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "outer_area_ratio": 0.80,
                "separator_width_evidence": {
                    "used": True,
                    "separator_width_gap_count": 0,
                    "broad_separator_width_gaps": 0,
                },
            },
        )
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_harm_risk": False,
            "frame_scores": [
                {"index": 1, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
                {"index": 2, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
                {"index": 3, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
            ],
        }

        detail = partial_extra_holder_frames_gate_detail(
            np.zeros((100, 300), dtype=np.uint8),
            detection,
            {"expected_gaps": 2, "hard_gaps": 1, "grid_gaps": 1, "equal_gaps": 0},
            content_detail,
            format_spec("120-66"),
            "separator",
            joint_score=0.90,
            content_score=0.10,
            geometry_score=0.90,
            policy=policy,
        )

        self.assertIn("holder_edge_disambiguation_weak", detail["disqualifiers"])
        self.assertNotIn("too_few_broad_separator_width_gaps", detail["disqualifiers"])
        self.assertNotIn("content_score_low", detail["disqualifiers"])
        self.assertIn("holder_edge_disambiguation", detail)
        self.assertEqual(
            detail["holder_edge_disambiguation"]["reason"],
            "holder_edge_disambiguation_weak",
        )
        self.assertEqual(
            detail["content_quality"]["role"],
            "quality_diagnostic_not_hard_gate",
        )
        self.assertFalse(detail["content_quality"]["quality_ok"])

    def test_evidence_independence_treats_content_score_as_quality_detail(self) -> None:
        detection = Detection(
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
            confidence=0.90,
            review_reasons=[],
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
        self.assertEqual(detail["content_score_role"], "quality_diagnostic_not_hard_gate")
        self.assertTrue(detail["ok"])

    def test_frame_box_width_detail_does_not_validate_evidence_independence(self) -> None:
        detection = Detection(
            film_format="120-66",
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
            review_reasons=[],
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

    def test_gate_support_checks_only_photo_edge_width_when_available(self) -> None:
        fmt = format_spec("120-66")
        policy = get_detection_policy("120-66", "full")
        hard_detail = {"expected_gaps": 2, "hard_gaps": 2, "grid_gaps": 0, "equal_gaps": 0}
        mode_policy = SeparatorGeometrySupportModePolicy(
            enabled=True,
            min_hard_ratio=0.50,
            allow_grid=True,
            max_equal_gaps=0,
            required_content_support="ok",
            min_joint_score=0.70,
            max_photo_width_cv=0.040,
            max_outer_area_ratio=0.99,
        )
        frame_box_detail_candidate = Detection(
            film_format="120-66",
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
            review_reasons=[],
            detail={
                "width_cv": 0.20,
                "width_cv_source": "frame_boxes",
                "outer_area_ratio": 0.80,
            },
        )
        unstable_photo_candidate = Detection(
            film_format="120-66",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=frame_box_detail_candidate.frames,
            gaps=[],
            confidence=0.90,
            review_reasons=[],
            detail={
                "width_cv": 0.20,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.20,
                "outer_area_ratio": 0.80,
            },
        )

        self.assertTrue(
            hard_full_calibration_floor_applies(
                frame_box_detail_candidate,
                hard_detail,
                fmt,
                "separator",
                policy,
            )
        )
        self.assertFalse(
            hard_full_calibration_floor_applies(
                unstable_photo_candidate,
                hard_detail,
                fmt,
                "separator",
                policy,
            )
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
        detection = Detection(
            film_format="120-66",
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
            review_reasons=[],
            detail={
                "width_cv": 0.20,
                "width_cv_source": "frame_boxes",
                "outer_area_ratio": 0.80,
                "separator_width_evidence": {
                    "used": True,
                    "separator_width_gap_count": 2,
                    "broad_separator_width_gaps": 2,
                },
            },
        )
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_harm_risk": False,
            "frame_scores": [
                {"index": 1, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
                {"index": 2, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
                {"index": 3, "mean": 0.20, "coverage": 0.30, "content_present": True, "aspect_error": 0.01},
            ],
        }

        detail = partial_extra_holder_frames_gate_detail(
            np.zeros((100, 300), dtype=np.uint8),
            detection,
            {"expected_gaps": 2, "hard_gaps": 2, "grid_gaps": 0, "equal_gaps": 0},
            content_detail,
            format_spec("120-66"),
            "separator",
            joint_score=0.90,
            content_score=0.90,
            geometry_score=0.90,
            policy=policy,
        )

        self.assertNotIn("photo_width_unstable", detail["disqualifiers"])
        self.assertEqual(detail["photo_width_stability"]["role"], "diagnostic_until_photo_edges")


if __name__ == "__main__":
    unittest.main()
