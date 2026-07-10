from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.architecture_contracts import PROJECT_ROOT
from tools.tests.decision_contract_support import (
    apply_test_detection_decision as apply_detection_decision,
    candidate_gate_detail as _candidate_gate_detail,
    content_ok_detail as _content_ok_detail,
    decision_contract as _decision_contract,
    decision_test_config as _decision_test_config,
)
from x5crop.cache.analysis import make_analysis_cache
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.candidate.selection.choose import select_detection_candidate
from x5crop.domain import Box, DetectionCandidate
from x5crop.formats import format_spec
from x5crop.report.read_models import selected_candidate
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.decision.contract import decision_contract_for_policy
from x5crop.runtime.output_protection import prepare_output_protection


class DecisionOwnershipOutputContractTest(unittest.TestCase):
    def test_user_docs_describe_feasible_overlap_and_variable_protection_bleed(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("输出长轴 bleed 会提高到 50px", readme)
        self.assertNotIn("long-axis output bleed is raised to 50px", readme)
        self.assertNotIn(
            "possible\n  overlap, or unstable local spacing goes to review",
            readme,
        )
        self.assertIn("按实际所需的保护宽度增加", readme)
        self.assertIn("grows by the required protection width", readme)

    def test_feasible_exposure_overlap_plan_does_not_block_decision(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "exposure_overlap_evidence": {
                    "used": True,
                    "exposure_overlap_detected": True,
                    "widest_overlap_band_px": 40.0,
                    "reason": "exposure_overlap_detected",
                },
                "output_protection_plan": {
                    "exposure_overlap_detected": True,
                    "feasible": True,
                    "reason": "exposure_overlap_protection_planned",
                },
                "candidate_assessment": {
                    "source": "separator",
                    "candidate_gate": _candidate_gate_detail(True),
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [],
                    "diagnostics": [],
                },
            },
        )
        config = _decision_test_config()
        content_detail = _content_ok_detail()
        outer_alignment = {"used": True, "ok": True}

        decided = apply_decision_gate(
            gray,
            detection,
            config,
            content_detail,
            outer_alignment,
            policy=_decision_contract("135", "full"),
            deskew_detail={},
        )

        self.assertEqual(decided.final_review_reasons, [])
        self.assertTrue(decided.detail["decision_signals"]["exposure_overlap_detected"])
        self.assertFalse(decided.detail["decision_signals"]["exposure_overlap_unresolved"])
        self.assertEqual(
            decided.detail["decision_signals"]["output_protection_plan"]["reason"],
            "exposure_overlap_protection_planned",
        )
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            [],
        )

    def test_exposure_overlap_plan_is_attached_before_final_decision(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": "separator",
                    "candidate_gate": _candidate_gate_detail(True),
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [],
                    "diagnostics": [],
                },
            },
        )
        policy = get_detection_policy("135", "full")
        config = _decision_test_config()
        cache = make_analysis_cache(
            gray,
            "horizontal",
            policy.preprocess.content_evidence_image,
        )

        with (
            patch(
                "x5crop.detection.evidence.selected_candidate.content_evidence_detail",
                return_value={"used": True},
            ),
            patch(
                "x5crop.detection.evidence.selected_candidate.content_containment_detail",
                return_value=_content_ok_detail(),
            ),
            patch(
                "x5crop.detection.evidence.selected_candidate.outer_content_alignment_detail",
                return_value={"used": True, "ok": True},
            ),
            patch(
                "x5crop.runtime.output_protection.exposure_overlap_evidence_detail",
                return_value={
                    "used": True,
                    "exposure_overlap_detected": True,
                    "widest_overlap_band_px": 40.0,
                    "reason": "exposure_overlap_detected",
                },
            ),
        ):
            protection_plan = prepare_output_protection(
                gray,
                detection,
                config,
                cache,
                policy,
            )
            decision = apply_detection_decision(
                gray,
                detection,
                config,
                cache,
                {},
                policy,
                decision_contract_for_policy(policy),
            )

        self.assertEqual(decision.status, "approved_auto")
        self.assertEqual(decision.final_review_reasons, [])
        self.assertEqual(
            decision.detail["exposure_overlap_evidence"]["reason"],
            "exposure_overlap_detected",
        )
        self.assertTrue(protection_plan.feasible)
        self.assertEqual(protection_plan.output_bleed.long_axis, 20)
        self.assertEqual(
            [item["signal"] for item in decision.detail["decision_reason_inputs"]],
            [],
        )

    def test_selection_records_competition_signal_without_candidate_review_reason(self) -> None:
        def candidate(confidence: float) -> DetectionCandidate:
            return DetectionCandidate(
                format_id="135",
                layout="horizontal",
                strip_mode="full",
                count=6,
                outer=Box(0, 0, 120, 20),
                frames=[],
                gaps=[],
                confidence=confidence,
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
            selection_policy=get_detection_policy("135", "full").candidate_selection,
        )

        self.assertEqual(selected.confidence, 0.90)
        self.assertFalse(hasattr(selected, "final_review_reasons"))
        self.assertEqual(
            selected.detail["candidate_competition"]["selection_uncertainty_inputs"][0]["signal"],
            "candidate_competition_close",
        )
        self.assertNotIn(
            "recommended_final_review_reason",
            selected.detail["candidate_competition"]["selection_uncertainty_inputs"][0],
        )
        self.assertTrue(
            selected.detail["candidate_competition"]["second_candidate_close"]
        )

    def test_content_mismatch_diagnostics_do_not_override_selection(self) -> None:
        fmt = format_spec("half")
        policy = get_detection_policy("half", "full")

        def content_candidate(*, diagnostics: list[str]) -> DetectionCandidate:
            return DetectionCandidate(
                format_id="half",
                layout="horizontal",
                strip_mode="full",
                count=fmt.default_count,
                outer=Box(0, 0, 1200, 100),
                frames=[],
                gaps=[],
                confidence=0.90,
                detail={
                    "candidate_assessment": {
                        "source": "content",
                        "joint_score": 0.90,
                        "diagnostics": diagnostics,
                        "blockers": [],
                    },
                },
            )

        separator_candidate = DetectionCandidate(
            format_id="half",
            layout="horizontal",
            strip_mode="full",
            count=fmt.default_count,
            outer=Box(0, 0, 1200, 100),
            frames=[],
            gaps=[],
            confidence=0.84,
            detail={
                "candidate_assessment": {
                    "source": "separator",
                    "joint_score": 0.84,
                    "content_support": "ok",
                    "diagnostics": [],
                    "blockers": [],
                    "separator_support": {
                        "expected_gaps": fmt.default_count - 1,
                        "hard_gaps": 6,
                        "equal_gaps": 0,
                    },
                },
            },
        )

        selected_without_diagnostic = select_detection_candidate(
            [
                content_candidate(
                    diagnostics=[],
                ),
                separator_candidate,
            ],
            fmt,
            threshold=0.85,
            selection_policy=policy.candidate_selection,
        )
        self.assertEqual(
            selected_without_diagnostic.detail["candidate_assessment"]["source"],
            "content",
        )
        self.assertNotIn("content_candidate_mismatch", selected_without_diagnostic.detail)

        selected_with_diagnostic = select_detection_candidate(
            [
                content_candidate(
                    diagnostics=["content_run_count_mismatch"],
                ),
                separator_candidate,
            ],
            fmt,
            threshold=0.85,
            selection_policy=policy.candidate_selection,
        )
        self.assertEqual(
            selected_with_diagnostic.detail["candidate_assessment"]["source"],
            "content",
        )
        self.assertNotIn("content_candidate_mismatch", selected_with_diagnostic.detail)

    def test_low_confidence_context_reasons_update_generated_summary(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.83,
            detail={
                "outer_area_spread_ratio": 0.25,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": "separator",
                    "candidate_gate": _candidate_gate_detail(True),
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [],
                    "diagnostics": [],
                },
                "candidate_competition": {
                    "selected_candidate": {
                        "selected": True,
                        "candidate_assessment": {"source": "separator"},
                    },
                    "top_candidates": [
                        {
                            "selected": True,
                            "candidate_assessment": {"source": "separator"},
                        }
                    ],
                },
            },
        )

        decided = apply_decision_gate(
            gray,
            detection,
            _decision_test_config(),
            _content_ok_detail(),
            {"used": True, "ok": True},
            policy=_decision_contract("135", "full"),
            deskew_detail={},
        )

        self.assertNotIn("final_review_reasons", decided.detail)
        self.assertEqual(
            decided.detail["decision_summary"]["final_review_reasons"],
            ["evidence_combination_insufficient", "outer_candidate_disagreement"],
        )
        self.assertNotIn("final_review_reasons_added", decided.detail["decision_summary"])
        decision_signals = [
            item["signal"] for item in decided.detail["decision_summary"]["decision_reason_inputs"]
        ]
        self.assertEqual(
            decision_signals,
        ["confidence_below_threshold", "outer_area_spread"],
        )
        self.assertEqual(
            decided.detail["decision_summary"]["decision_reason_inputs"][1]["bucket"],
            "low_confidence_context",
        )
        selected = decided.detail["candidate_competition"]["selected_candidate"]
        self.assertNotIn("final_review_reasons", selected)
        self.assertNotIn("decision_status", selected)
        report_selected = selected_candidate(decided)
        self.assertEqual(
            decided.final_review_reasons,
            ["evidence_combination_insufficient", "outer_candidate_disagreement"],
        )
        self.assertEqual(decided.status, "needs_review")
        self.assertNotIn("final_review_reasons", report_selected)
        self.assertNotIn("decision_status", report_selected)
        self.assertNotIn(
            "final_review_reasons",
            decided.detail["candidate_competition"]["top_candidates"][0],
        )

    def test_low_confidence_context_reasons_do_not_create_high_confidence_review(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "outer_area_spread_ratio": 0.25,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": "separator",
                    "candidate_gate": _candidate_gate_detail(True),
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [],
                    "diagnostics": [],
                },
            },
        )

        decided = apply_decision_gate(
            gray,
            detection,
            _decision_test_config(),
            _content_ok_detail(),
            {"used": True, "ok": True},
            policy=_decision_contract("135", "full"),
            deskew_detail={"reason": "no_outer"},
        )

        self.assertEqual(decided.final_review_reasons, [])
        self.assertEqual(decided.detail["decision_summary"]["final_review_reasons"], [])
        self.assertEqual(decided.detail["decision_summary"]["decision_reason_inputs"], [])



if __name__ == "__main__":
    unittest.main()
