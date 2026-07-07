from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from x5crop.constants import CANDIDATE_SOURCE_SAFETY
from x5crop.detection.candidate.assessment.safety import SAFETY_CANDIDATE_AUTO_GATE_BLOCKER
from x5crop.detection.decision.final_decision import _apply_decision_post_check_reasons
from x5crop.detection.decision.pass_review import apply_final_decision_policy
from x5crop.detection.candidate.selection.choose import select_detection_candidate
from x5crop.domain import Box, Detection
from x5crop.formats import format_spec
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.decision.contract import decision_contract_for
from x5crop.runtime.config import RuntimeConfig


class DecisionReasonContractTest(unittest.TestCase):
    def test_decision_contract_report_does_not_expose_unused_candidate_policy(self) -> None:
        detail = decision_contract_for("135", "full").report_detail()

        self.assertNotIn("candidate_policy", detail)
        self.assertIn("risk_policy", detail)
        self.assertIn("decision_policy", detail)

    def test_final_review_reasons_are_owned_by_decision_inputs(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = Detection(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            review_reasons=["content_coverage_weak"],
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": "separator",
                    "auto_gate": False,
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [],
                    "diagnostics": ["content_coverage_weak"],
                },
            },
        )
        config = RuntimeConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            film_format="135",
            layout_auto=False,
            layout="horizontal",
            strip_mode="full",
            count=1,
            count_override=1,
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
            diagnostics=False,
            compression="auto",
            debug=False,
            debug_analysis=False,
            dry_run=True,
            overwrite=True,
            report=True,
            debug_errors=False,
            reuse_analysis=False,
            jobs=1,
        )
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_harm_risk": False,
        }
        outer_alignment = {"used": True, "ok": True}

        decided = apply_final_decision_policy(
            gray,
            detection,
            config,
            format_spec("135"),
            content_detail,
            outer_alignment,
        )

        self.assertEqual(decided.review_reasons, ["evidence_combination_insufficient"])
        self.assertEqual(
            decided.detail["candidate_reason_inputs_before_decision"]["diagnostics"],
            ["content_only_evidence"],
        )
        self.assertNotIn("candidate_review_reasons_before_decision", decided.detail)
        self.assertEqual(
            decided.detail["final_review_reasons"],
            ["evidence_combination_insufficient"],
        )
        self.assertEqual(
            decided.detail["decision_reason_inputs"][0]["signal"],
            "candidate_auto_gate_failed",
        )
        self.assertIn("decision_confidence_caps", decided.detail["decision_summary"])
        self.assertIn("final_review_reasons_added", decided.detail["decision_summary"])
        self.assertNotIn("review_reasons_added", decided.detail["decision_summary"])

    def test_safety_candidate_blocker_is_explained_by_decision_risk(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = Detection(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            review_reasons=[SAFETY_CANDIDATE_AUTO_GATE_BLOCKER],
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": CANDIDATE_SOURCE_SAFETY,
                    "auto_gate": False,
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [SAFETY_CANDIDATE_AUTO_GATE_BLOCKER],
                    "diagnostics": [],
                },
            },
        )
        config = RuntimeConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            film_format="135",
            layout_auto=False,
            layout="horizontal",
            strip_mode="full",
            count=1,
            count_override=1,
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
            diagnostics=False,
            compression="auto",
            debug=False,
            debug_analysis=False,
            dry_run=True,
            overwrite=True,
            report=True,
            debug_errors=False,
            reuse_analysis=False,
            jobs=1,
        )
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_harm_risk": False,
        }
        outer_alignment = {"used": True, "ok": True}

        decided = apply_final_decision_policy(
            gray,
            detection,
            config,
            format_spec("135"),
            content_detail,
            outer_alignment,
        )

        self.assertEqual(
            decided.detail["risk_summary"]["safety_or_review_only"],
            True,
        )
        self.assertEqual(
            decided.detail["candidate_reason_inputs_before_decision"]["blockers"],
            [SAFETY_CANDIDATE_AUTO_GATE_BLOCKER],
        )
        self.assertEqual(
            decided.review_reasons,
            ["evidence_combination_insufficient"],
        )
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["safety_or_review_only", "candidate_auto_gate_failed"],
        )

    def test_close_competition_is_final_decision_reason(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = Detection(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            review_reasons=[],
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": "separator",
                    "auto_gate": True,
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [],
                    "diagnostics": [],
                },
                "candidate_competition": {
                    "margin_to_second": 0.03,
                    "partial_full_conflict": False,
                },
            },
        )
        config = RuntimeConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            film_format="135",
            layout_auto=False,
            layout="horizontal",
            strip_mode="full",
            count=1,
            count_override=1,
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
            diagnostics=False,
            compression="auto",
            debug=False,
            debug_analysis=False,
            dry_run=True,
            overwrite=True,
            report=True,
            debug_errors=False,
            reuse_analysis=False,
            jobs=1,
        )
        content_detail = {
            "used": True,
            "support": "ok",
            "content_containment_ok": True,
            "content_harm_risk": False,
        }
        outer_alignment = {"used": True, "ok": True}

        decided = apply_final_decision_policy(
            gray,
            detection,
            config,
            format_spec("135"),
            content_detail,
            outer_alignment,
        )

        self.assertEqual(decided.review_reasons, ["candidate_competition_close"])
        self.assertEqual(decided.confidence, 0.84)
        self.assertEqual(
            decided.detail["decision_reason_inputs"][0]["signal"],
            "candidate_competition_close",
        )
        self.assertEqual(
            decided.detail["risk_summary"]["candidate_margin_to_second"],
            0.03,
        )

    def test_selection_records_competition_risk_without_candidate_review_reason(self) -> None:
        def candidate(confidence: float) -> Detection:
            return Detection(
                film_format="135",
                layout="horizontal",
                strip_mode="full",
                count=6,
                outer=Box(0, 0, 120, 20),
                frames=[],
                gaps=[],
                confidence=confidence,
                review_reasons=[],
                detail={
                    "candidate_assessment": {
                        "source": "separator",
                        "joint_score": confidence,
                    },
                },
            )

        selected = select_detection_candidate(
            [candidate(0.90), candidate(0.875)],
            format_spec("135"),
            threshold=0.85,
            policy=get_detection_policy("135", "full"),
        )

        self.assertEqual(selected.confidence, 0.90)
        self.assertEqual(selected.review_reasons, [])
        self.assertEqual(
            selected.detail["selection_risk_inputs"][0]["signal"],
            "candidate_competition_close",
        )
        self.assertTrue(
            selected.detail["candidate_competition"]["second_candidate_close"]
        )

    def test_decision_post_check_reasons_update_added_summary(self) -> None:
        detection = Detection(
            film_format="135",
            layout="horizontal",
            strip_mode="partial",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.83,
            review_reasons=["evidence_combination_insufficient"],
            detail={
                "partial_best": True,
                "decision_reason_inputs": [],
                "decision_summary": {
                    "final_review_reasons_added": ["evidence_combination_insufficient"],
                    "final_review_reasons": ["evidence_combination_insufficient"],
                    "decision_reason_inputs": [],
                },
            },
        )
        config = RuntimeConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            film_format="135",
            layout_auto=False,
            layout="horizontal",
            strip_mode="partial",
            count=1,
            count_override=1,
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
            diagnostics=False,
            compression="auto",
            debug=False,
            debug_analysis=False,
            dry_run=True,
            overwrite=True,
            report=True,
            debug_errors=False,
            reuse_analysis=False,
            jobs=1,
        )

        _apply_decision_post_check_reasons(
            detection,
            config,
            get_detection_policy("135", "partial"),
            {},
        )

        self.assertEqual(
            detection.detail["final_review_reasons"],
            ["evidence_combination_insufficient", "partial_edge_uncertain"],
        )
        self.assertEqual(
            detection.detail["decision_summary"]["final_review_reasons_added"],
            ["evidence_combination_insufficient", "partial_edge_uncertain"],
        )
        self.assertEqual(
            detection.detail["decision_summary"]["decision_reason_inputs"][0]["signal"],
            "partial_best",
        )
        self.assertEqual(
            detection.detail["decision_summary"]["decision_reason_inputs"][0]["bucket"],
            "decision_post_check",
        )


if __name__ == "__main__":
    unittest.main()
