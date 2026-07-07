import unittest

import numpy as np

from x5crop.detection.candidate.assessment.base_scoring import base_detection_assessment
from x5crop.detection.candidate.assessment.evidence_independence import evidence_independence_detail
from x5crop.detection.candidate.assessment.partial_holder import partial_extra_holder_frames_gate_detail
from x5crop.detection.decision.pass_review import evidence_summary_for
from x5crop.detection.evidence.risk import lucky_width_instability_components
from x5crop.domain import Box, Detection, Gap
from x5crop.formats import format_spec
from x5crop.gap_methods import GAP_DETECTED
from x5crop.policies.decision.contract import decision_contract_for
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.runtime.candidate import EvidenceIndependencePolicy
from x5crop.policies.runtime.diagnostics import LuckyPassRiskPolicy


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

    def test_lucky_pass_width_instability_requires_photo_edge_width_source(self) -> None:
        policy = LuckyPassRiskPolicy()

        fallback_components, fallback_detail = lucky_width_instability_components(
            0.020,
            "frame_boxes",
            policy,
        )
        photo_components, photo_detail = lucky_width_instability_components(
            0.020,
            "photo_edges",
            policy,
        )

        self.assertEqual(fallback_components, {})
        self.assertFalse(fallback_detail["used"])
        self.assertEqual(fallback_detail["reason"], "width_source_not_photo_edges")
        self.assertIn("unstable_widths", photo_components)
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


if __name__ == "__main__":
    unittest.main()
