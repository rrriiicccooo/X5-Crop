from __future__ import annotations

from dataclasses import replace
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from x5crop.cache.analysis import make_analysis_cache
from x5crop.constants import CANDIDATE_SOURCE_SAFETY, REASON_LUCKY_PASS_RISK
from x5crop.detection.candidate.assessment.safety import SAFETY_CANDIDATE_AUTO_GATE_BLOCKER
from x5crop.detection.decision.final_decision import apply_detection_decision
from x5crop.detection.decision.contract_applier import apply_decision_contract
from x5crop.detection.decision.reasons import normalized_final_review_reasons
from x5crop.detection.modes.review_only import review_only_detection
from x5crop.detection.candidate.selection.choose import select_detection_candidate
from x5crop.domain import Box, Detection
from x5crop.formats import format_spec
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.decision.contract import decision_contract_for
from x5crop.runtime.config import RuntimeConfig


def _decision_test_config(*, threshold: float = 0.85) -> RuntimeConfig:
    return RuntimeConfig(
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
        confidence_threshold=threshold,
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


def _content_ok_detail() -> dict[str, bool | str]:
    return {
        "used": True,
        "support": "ok",
        "content_containment_ok": True,
        "content_harm_risk": False,
    }


class DecisionReasonContractTest(unittest.TestCase):
    def test_decision_contract_report_does_not_expose_unused_candidate_policy(self) -> None:
        detail = decision_contract_for("135", "full").report_detail()

        self.assertNotIn("candidate_policy", detail)
        self.assertIn("risk_policy", detail)
        self.assertIn("decision_policy", detail)
        self.assertNotIn("output_policy", detail)
        self.assertNotIn("diagnostics_policy", detail)
        self.assertNotIn(
            "content_only_candidates_review_only",
            detail["risk_policy"],
        )
        self.assertNotIn(
            "safety_candidates_review_only",
            detail["risk_policy"],
        )
        self.assertEqual(
            detail["decision_policy"]["content_evidence_insufficient_reason"],
            "content_evidence_insufficient",
        )

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
            review_reasons=[],
            detail={
                "candidate_reasons": ["content_coverage_weak"],
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
        config = _decision_test_config()
        content_detail = _content_ok_detail()
        outer_alignment = {"used": True, "ok": True}

        decided = apply_decision_contract(
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
            ["content_coverage_weak"],
        )
        self.assertEqual(
            decided.detail["candidate_reason_inputs_before_decision"]["legacy_reduced_candidate_reasons"],
            ["content_evidence_insufficient"],
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
            review_reasons=[],
            detail={
                "candidate_reasons": [SAFETY_CANDIDATE_AUTO_GATE_BLOCKER],
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
        config = _decision_test_config()
        content_detail = _content_ok_detail()
        outer_alignment = {"used": True, "ok": True}

        decided = apply_decision_contract(
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

    def test_review_only_mode_diagnostics_wait_for_final_decision(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        fmt = format_spec("135-dual")
        config = replace(
            _decision_test_config(),
            film_format="135-dual",
            strip_mode="partial",
            count=fmt.default_count,
            count_override=None,
        )
        policy = get_detection_policy("135-dual", "partial")
        detection = review_only_detection(
            gray,
            config,
            fmt,
            policy,
        )

        self.assertEqual(detection.review_reasons, [])
        mode_reasons = [policy.detector.review_only.reason, "needs_manual_review"]
        self.assertEqual(
            detection.detail["candidate_reasons"],
            mode_reasons,
        )
        self.assertEqual(
            detection.detail["mode_diagnostics"],
            mode_reasons,
        )

        decided = apply_decision_contract(
            gray,
            detection,
            config,
            fmt,
            _content_ok_detail(),
            {"used": True, "ok": True},
        )

        self.assertIn("evidence_combination_insufficient", decided.review_reasons)
        self.assertIn("separator_evidence_incomplete", decided.review_reasons)
        self.assertIn(
            "evidence_combination_insufficient",
            decided.detail["candidate_reason_inputs_before_decision"]["legacy_reduced_candidate_reasons"],
        )
        decision_signals = [
            item["signal"] for item in decided.detail["decision_reason_inputs"]
        ]
        self.assertIn("safety_or_review_only", decision_signals)
        self.assertIn("separator_not_ok", decision_signals)

    def test_content_evidence_failure_is_not_content_only_reason(self) -> None:
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
            "support": "low_content",
            "content_containment_ok": False,
            "content_harm_risk": True,
        }
        outer_alignment = {"used": True, "ok": True}

        decided = apply_decision_contract(
            gray,
            detection,
            config,
            format_spec("135"),
            content_detail,
            outer_alignment,
        )

        self.assertEqual(decided.review_reasons, ["content_evidence_insufficient"])
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["content_not_ok"],
        )

    def test_lucky_pass_risk_is_distinct_final_reason(self) -> None:
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
                "lucky_pass_risk_score": {
                    "used": True,
                    "risk": True,
                    "reason": "lucky_pass_risk",
                },
                "candidate_assessment": {
                    "source": "separator",
                    "auto_gate": True,
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

        decided = apply_decision_contract(
            gray,
            detection,
            config,
            format_spec("135"),
            content_detail,
            outer_alignment,
        )

        self.assertEqual(
            normalized_final_review_reasons([REASON_LUCKY_PASS_RISK]),
            ["lucky_pass_risk"],
        )
        self.assertEqual(decided.review_reasons, ["lucky_pass_risk"])
        self.assertFalse(decided.detail["risk_summary"]["overlap_risk"])
        self.assertTrue(decided.detail["risk_summary"]["lucky_pass_risk"])
        self.assertEqual(
            decided.detail["risk_summary"]["lucky_pass_risk_detail"]["reason"],
            "lucky_pass_risk",
        )
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["lucky_pass_risk"],
        )

    def test_overlap_bleed_risk_is_distinct_from_lucky_pass_risk(self) -> None:
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
                "overlap_bleed_risk": {
                    "used": True,
                    "risk": True,
                    "reason": "overlap_bleed_risk",
                },
                "lucky_pass_risk_score": {
                    "used": True,
                    "risk": False,
                    "reason": "ok",
                },
                "candidate_assessment": {
                    "source": "separator",
                    "auto_gate": True,
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

        decided = apply_decision_contract(
            gray,
            detection,
            config,
            format_spec("135"),
            content_detail,
            outer_alignment,
        )

        self.assertEqual(decided.review_reasons, ["overlap_risk"])
        self.assertTrue(decided.detail["risk_summary"]["overlap_risk"])
        self.assertFalse(decided.detail["risk_summary"]["lucky_pass_risk"])
        self.assertEqual(
            decided.detail["risk_summary"]["overlap_bleed_risk"]["reason"],
            "overlap_bleed_risk",
        )
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["overlap_bleed_risk"],
        )

    def test_overlap_bleed_risk_is_attached_before_final_decision(self) -> None:
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
            },
        )
        base_policy = get_detection_policy("135", "full")
        policy = replace(
            base_policy,
            risk=replace(
                base_policy.risk,
                overlap_bleed=replace(
                    base_policy.risk.overlap_bleed,
                    enabled=True,
                ),
            ),
        )

        with (
            patch(
                "x5crop.detection.decision.final_decision.content_evidence_detail",
                return_value={"used": True},
            ),
            patch(
                "x5crop.detection.decision.final_decision.content_containment_detail",
                return_value=_content_ok_detail(),
            ),
            patch(
                "x5crop.detection.decision.final_decision.outer_content_alignment_detail",
                return_value={"used": True, "ok": True},
            ),
            patch(
                "x5crop.detection.decision.final_decision.overlap_bleed_risk_detail",
                return_value={
                    "used": True,
                    "risk": True,
                    "reason": "overlap_bleed_risk",
                },
            ),
            patch(
                "x5crop.detection.decision.final_decision.lucky_pass_risk_score_detail",
                return_value={"used": True, "risk": False, "reason": "ok"},
            ),
        ):
            decision = apply_detection_decision(
                gray,
                detection,
                _decision_test_config(),
                format_spec("135"),
                make_analysis_cache(gray, "horizontal"),
                {},
                policy,
            )

        self.assertEqual(decision.status, "needs_review")
        self.assertEqual(decision.detection.review_reasons, ["overlap_risk"])
        self.assertEqual(
            decision.detection.detail["overlap_bleed_risk"]["reason"],
            "overlap_bleed_risk",
        )
        self.assertEqual(
            [item["signal"] for item in decision.detection.detail["decision_reason_inputs"]],
            ["overlap_bleed_risk"],
        )

    def test_final_status_requires_no_review_reasons_with_low_threshold(self) -> None:
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
                "candidate_reasons": [SAFETY_CANDIDATE_AUTO_GATE_BLOCKER],
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_source": CANDIDATE_SOURCE_SAFETY,
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
            confidence_threshold=0.70,
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

        decision = apply_detection_decision(
            gray,
            detection,
            config,
            format_spec("135"),
            make_analysis_cache(gray, "horizontal"),
            {},
            get_detection_policy("135", "full"),
        )

        self.assertEqual(decision.status, "needs_review")
        self.assertEqual(decision.detection.confidence, 0.84)
        self.assertEqual(
            decision.detection.review_reasons,
            ["content_evidence_insufficient", "evidence_combination_insufficient"],
        )
        self.assertEqual(
            decision.detection.detail["decision_summary"]["status"],
            "needs_review",
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

        decided = apply_decision_contract(
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
        self.assertNotIn(
            "recommended_final_review_reason",
            selected.detail["selection_risk_inputs"][0],
        )
        self.assertTrue(
            selected.detail["candidate_competition"]["second_candidate_close"]
        )

    def test_content_mismatch_selection_uses_candidate_diagnostics(self) -> None:
        fmt = format_spec("half")
        policy = get_detection_policy("half", "full")

        def content_candidate(*, diagnostics: list[str], reasons: list[str]) -> Detection:
            return Detection(
                film_format="half",
                layout="horizontal",
                strip_mode="full",
                count=fmt.default_count,
                outer=Box(0, 0, 1200, 100),
                frames=[],
                gaps=[],
                confidence=0.90,
                review_reasons=reasons,
                detail={
                    "candidate_assessment": {
                        "source": "content",
                        "joint_score": 0.90,
                        "diagnostics": diagnostics,
                        "blockers": [],
                    },
                },
            )

        separator_candidate = Detection(
            film_format="half",
            layout="horizontal",
            strip_mode="full",
            count=fmt.default_count,
            outer=Box(0, 0, 1200, 100),
            frames=[],
            gaps=[],
            confidence=0.84,
            review_reasons=[],
            detail={
                "candidate_assessment": {
                    "source": "separator",
                    "joint_score": 0.84,
                    "content_support": "ok",
                    "diagnostics": [],
                    "blockers": [],
                    "separator_hard_evidence": {
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
                    reasons=["content_run_count_mismatch"],
                ),
                separator_candidate,
            ],
            fmt,
            threshold=0.85,
            policy=policy,
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
                    reasons=[],
                ),
                separator_candidate,
            ],
            fmt,
            threshold=0.85,
            policy=policy,
        )
        self.assertEqual(
            selected_with_diagnostic.detail["candidate_assessment"]["source"],
            "separator",
        )
        self.assertEqual(
            selected_with_diagnostic.detail["content_candidate_mismatch"]["content_candidate_diagnostics"],
            ["content_run_count_mismatch"],
        )
        self.assertNotIn(
            "content_candidate_reasons",
            selected_with_diagnostic.detail["content_candidate_mismatch"],
        )

    def test_low_confidence_context_reasons_update_added_summary(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = Detection(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.83,
            review_reasons=[],
            detail={
                "outer_area_spread_ratio": 0.25,
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
                    "selected_candidate": {
                        "selected": True,
                        "final_confidence": 0.83,
                        "final_review_reasons": ["evidence_combination_insufficient"],
                        "decision_status": "needs_review",
                    },
                    "top_candidates": [
                        {
                            "selected": True,
                            "final_confidence": 0.83,
                            "final_review_reasons": ["evidence_combination_insufficient"],
                            "decision_status": "needs_review",
                        }
                    ],
                },
            },
        )

        decided = apply_decision_contract(
            gray,
            detection,
            _decision_test_config(),
            format_spec("135"),
            _content_ok_detail(),
            {"used": True, "ok": True},
            {},
        )

        self.assertEqual(
            decided.detail["final_review_reasons"],
            ["evidence_combination_insufficient", "outer_candidate_disagreement"],
        )
        self.assertEqual(
            decided.detail["decision_summary"]["final_review_reasons_added"],
            ["evidence_combination_insufficient", "outer_candidate_disagreement"],
        )
        decision_signals = [
            item["signal"] for item in decided.detail["decision_summary"]["decision_reason_inputs"]
        ]
        self.assertEqual(
            decision_signals,
            ["below_threshold", "outer_area_spread"],
        )
        self.assertEqual(
            decided.detail["decision_summary"]["decision_reason_inputs"][1]["bucket"],
            "low_confidence_context",
        )
        selected = decided.detail["candidate_competition"]["selected_candidate"]
        self.assertEqual(
            selected["final_review_reasons"],
            ["evidence_combination_insufficient", "outer_candidate_disagreement"],
        )
        self.assertEqual(selected["decision_status"], "needs_review")
        self.assertEqual(
            decided.detail["candidate_competition"]["top_candidates"][0]["final_review_reasons"],
            ["evidence_combination_insufficient", "outer_candidate_disagreement"],
        )

    def test_low_confidence_context_reasons_do_not_create_high_confidence_review(self) -> None:
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
                "outer_area_spread_ratio": 0.25,
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
            },
        )

        decided = apply_decision_contract(
            gray,
            detection,
            _decision_test_config(),
            format_spec("135"),
            _content_ok_detail(),
            {"used": True, "ok": True},
            {"reason": "no_outer"},
        )

        self.assertEqual(decided.review_reasons, [])
        self.assertEqual(decided.detail["decision_summary"]["final_review_reasons"], [])
        self.assertEqual(decided.detail["decision_summary"]["decision_reason_inputs"], [])


if __name__ == "__main__":
    unittest.main()
