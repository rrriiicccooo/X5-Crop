from __future__ import annotations

from dataclasses import replace
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from x5crop.cache.analysis import make_analysis_cache
from x5crop.constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_HARD_SAFETY,
    CANDIDATE_SOURCE_SAFETY,
    CANDIDATE_SOURCE_SEPARATOR,
)
from x5crop.detection.candidate.assessment.safety import SAFETY_CANDIDATE_BLOCKER
from x5crop.detection.decision.final_decision import apply_detection_decision
from x5crop.detection.decision.contract_applier import apply_decision_contract
from x5crop.detection.decision.decision_signals import decision_signals_for
from x5crop.detection.modes.review_only import review_only_detection
from x5crop.detection.candidate.selection.choose import select_detection_candidate
from x5crop.domain import Box, DetectionCandidate
from x5crop.formats import format_spec
from x5crop.report.sections import selected_candidate
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.decision.contract import decision_contract_for_policy
from x5crop.runtime.config import RuntimeConfig


def _decision_test_config(*, threshold: float = 0.85) -> RuntimeConfig:
    return RuntimeConfig(
        input_path=Path("synthetic.tif"),
        output_dir=None,
        film_format="135",
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        requested_count=1,
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
        "content_integrity_failed": False,
    }


def _decision_contract(format_id: str = "135", strip_mode: str = "full"):
    return decision_contract_for_policy(get_detection_policy(format_id, strip_mode))


def _candidate_gate_detail(
    passed: bool,
    *,
    blockers: list[str] | None = None,
    diagnostics: list[str] | None = None,
) -> dict:
    return {
        "passed": bool(passed),
        "checks": [],
        "blockers": list(blockers or []),
        "diagnostics": list(diagnostics or []),
        "confidence_caps": [],
    }


class DecisionReasonContractTest(unittest.TestCase):
    def test_decision_contract_report_does_not_expose_unused_candidate_policy(self) -> None:
        detail = _decision_contract("135", "full").report_detail()

        self.assertNotIn("candidate_policy", detail)
        self.assertNotIn("risk_policy", detail)
        self.assertIn("decision_policy", detail)
        self.assertNotIn("output_policy", detail)
        self.assertNotIn("diagnostics_policy", detail)
        self.assertEqual(
            detail["decision_policy"]["content_evidence_insufficient_reason"],
            "content_evidence_insufficient",
        )

    def test_final_review_reasons_are_owned_by_decision_inputs(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "candidate_signals": ["content_coverage_weak"],
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": "separator",
                    "candidate_gate": _candidate_gate_detail(False),
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
            content_detail,
            outer_alignment,
            policy=_decision_contract("135", "full"),
        )

        self.assertEqual(decided.final_review_reasons, ["evidence_combination_insufficient"])
        self.assertEqual(
            decided.detail["candidate_gate_input"]["diagnostics"],
            ["content_coverage_weak"],
        )
        self.assertNotIn("candidate_final_review_reasons_before_decision", decided.detail)
        self.assertNotIn("final_review_reasons", decided.detail)
        self.assertEqual(
            decided.detail["decision_reason_inputs"][0]["signal"],
            "candidate_gate_failed",
        )
        self.assertIn("decision_confidence_caps", decided.detail["decision_summary"])
        self.assertIn("final_review_reasons", decided.detail["decision_summary"])
        self.assertNotIn("final_review_reasons_added", decided.detail["decision_summary"])
        self.assertNotIn("final_review_reasons_added", decided.detail["decision_summary"])
        self.assertNotIn("candidate_blockers_before_decision", decided.detail)
        self.assertNotIn("candidate_diagnostics_before_decision", decided.detail)

    def test_safety_candidate_blocker_is_explained_by_decision_signal(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "candidate_signals": [SAFETY_CANDIDATE_BLOCKER],
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_assessment": {
                    "source": CANDIDATE_SOURCE_SAFETY,
                    "candidate_gate": _candidate_gate_detail(False),
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [SAFETY_CANDIDATE_BLOCKER],
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
            content_detail,
            outer_alignment,
            policy=_decision_contract("135", "full"),
        )

        self.assertEqual(
            decided.detail["decision_signals"]["safety_or_review_only"],
            True,
        )
        self.assertEqual(
            decided.detail["candidate_gate_input"]["blockers"],
            [SAFETY_CANDIDATE_BLOCKER],
        )
        self.assertEqual(
            decided.final_review_reasons,
            ["evidence_combination_insufficient"],
        )
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["safety_or_review_only", "candidate_gate_failed"],
        )

    def test_decision_signals_separate_assessment_source_from_candidate_source(self) -> None:
        policy = _decision_contract("135", "full")
        evidence = {
            "outer": {"ok": True},
            "separator": {"ok": True},
            "geometry": {"ok": True},
            "content": {"ok": True},
            "partial_edge": {"ok": True},
        }

        content_detection = DetectionCandidate(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "candidate_source": CANDIDATE_SOURCE_SEPARATOR,
                "candidate_assessment": {
                    "source": CANDIDATE_SOURCE_CONTENT,
                    "candidate_gate": _candidate_gate_detail(False),
                },
            },
        )

        content_signals = decision_signals_for(content_detection, evidence, policy)

        self.assertTrue(content_signals["content_only_evidence"])
        self.assertFalse(content_signals["safety_or_review_only"])
        self.assertEqual(
            content_signals["candidate_source_detail"],
            {
                "assessment_source": CANDIDATE_SOURCE_CONTENT,
                "candidate_source": CANDIDATE_SOURCE_SEPARATOR,
                "content_only_evidence_source": CANDIDATE_SOURCE_CONTENT,
                "safety_or_review_only_source": "",
            },
        )

        hard_safety_detection = DetectionCandidate(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "candidate_source": CANDIDATE_SOURCE_HARD_SAFETY,
                "candidate_assessment": {
                    "source": "separator",
                    "candidate_gate": _candidate_gate_detail(False),
                },
            },
        )

        hard_safety_signals = decision_signals_for(hard_safety_detection, evidence, policy)

        self.assertFalse(hard_safety_signals["content_only_evidence"])
        self.assertTrue(hard_safety_signals["safety_or_review_only"])
        self.assertEqual(
            hard_safety_signals["candidate_source_detail"]["content_only_evidence_source"],
            "",
        )
        self.assertEqual(
            hard_safety_signals["candidate_source_detail"]["safety_or_review_only_source"],
            CANDIDATE_SOURCE_HARD_SAFETY,
        )

    def test_review_only_mode_diagnostics_wait_for_final_decision(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        fmt = format_spec("135-dual")
        config = replace(
            _decision_test_config(),
            film_format="135-dual",
            strip_mode="partial",
            requested_count=None,
        )
        policy = get_detection_policy("135-dual", "partial")
        detection = review_only_detection(
            gray,
            config,
            fmt,
            policy,
        )

        self.assertFalse(hasattr(detection, "final_review_reasons"))
        mode_reasons = [policy.detector.review_only.reason, "needs_manual_review"]
        self.assertEqual(
            detection.detail["candidate_signals"],
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
            _content_ok_detail(),
            {"used": True, "ok": True},
            policy=_decision_contract("135-dual", "partial"),
        )

        self.assertIn("evidence_combination_insufficient", decided.final_review_reasons)
        self.assertIn("separator_evidence_incomplete", decided.final_review_reasons)
        decision_signals = [
            item["signal"] for item in decided.detail["decision_reason_inputs"]
        ]
        self.assertIn("safety_or_review_only", decision_signals)
        self.assertIn("separator_support_incomplete", decision_signals)

    def test_content_evidence_failure_is_not_content_only_reason(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
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
        config = RuntimeConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            film_format="135",
            layout_auto=False,
            layout="horizontal",
            strip_mode="full",
            requested_count=1,
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
            "content_integrity_failed": True,
        }
        outer_alignment = {"used": True, "ok": True}

        decided = apply_decision_contract(
            gray,
            detection,
            config,
            content_detail,
            outer_alignment,
            policy=_decision_contract("135", "full"),
        )

        self.assertEqual(decided.final_review_reasons, ["content_evidence_insufficient"])
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["content_integrity_failed"],
        )

    def test_output_overlap_evidence_is_output_protection_signal(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
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
                "output_overlap_evidence": {
                    "used": True,
                    "output_overlap_detected": True,
                    "output_overlap_protected_by_bleed": True,
                    "output_overlap_unresolved": False,
                    "reason": "output_overlap_protected_by_bleed",
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

        decided = apply_decision_contract(
            gray,
            detection,
            config,
            content_detail,
            outer_alignment,
            policy=_decision_contract("135", "full"),
        )

        self.assertEqual(decided.final_review_reasons, [])
        self.assertTrue(decided.detail["decision_signals"]["output_overlap_detected"])
        self.assertTrue(
            decided.detail["decision_signals"]["output_overlap_protected_by_bleed"]
        )
        self.assertFalse(decided.detail["decision_signals"]["output_overlap_unresolved"])
        self.assertEqual(
            decided.detail["decision_signals"]["output_overlap_evidence"]["reason"],
            "output_overlap_protected_by_bleed",
        )
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            [],
        )

    def test_unresolved_output_overlap_is_final_decision_signal(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
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
                "output_overlap_evidence": {
                    "used": True,
                    "output_overlap_detected": True,
                    "output_overlap_protected_by_bleed": False,
                    "output_overlap_unresolved": True,
                    "reason": "output_overlap_unresolved",
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
        decided = apply_decision_contract(
            gray,
            detection,
            _decision_test_config(),
            _content_ok_detail(),
            {"used": True, "ok": True},
            policy=_decision_contract("135", "full"),
        )

        self.assertEqual(decided.final_review_reasons, ["output_overlap_unresolved"])
        self.assertTrue(decided.detail["decision_signals"]["output_overlap_unresolved"])
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["output_overlap_unresolved"],
        )

    def test_output_overlap_evidence_is_attached_before_final_decision(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
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
        base_policy = get_detection_policy("135", "full")
        policy = replace(
            base_policy,
            output_evidence=replace(
                base_policy.output_evidence,
                output_overlap=replace(
                    base_policy.output_evidence.output_overlap,
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
                "x5crop.detection.decision.final_decision.output_overlap_evidence_detail",
                return_value={
                    "used": True,
                    "output_overlap_detected": True,
                    "output_overlap_protected_by_bleed": True,
                    "output_overlap_unresolved": False,
                    "reason": "output_overlap_protected_by_bleed",
                },
            ),
        ):
            decision = apply_detection_decision(
                gray,
                detection,
                _decision_test_config(),
                make_analysis_cache(gray, "horizontal", policy.preprocess.content_evidence_image),
                {},
                policy,
                decision_contract_for_policy(policy),
            )

        self.assertEqual(decision.status, "approved_auto")
        self.assertEqual(decision.final_review_reasons, [])
        self.assertEqual(
            decision.detail["output_overlap_evidence"]["reason"],
            "output_overlap_protected_by_bleed",
        )
        self.assertEqual(
            [item["signal"] for item in decision.detail["decision_reason_inputs"]],
            [],
        )

    def test_final_status_requires_no_final_review_reasons_with_low_threshold(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
            layout="horizontal",
            strip_mode="full",
            count=1,
            outer=Box(10, 10, 90, 90),
            frames=[Box(10, 10, 90, 90)],
            gaps=[],
            confidence=0.90,
            detail={
                "candidate_signals": [SAFETY_CANDIDATE_BLOCKER],
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
                "candidate_source": CANDIDATE_SOURCE_SAFETY,
                "candidate_assessment": {
                    "source": CANDIDATE_SOURCE_SAFETY,
                    "candidate_gate": _candidate_gate_detail(False),
                    "geometry_score": 1.0,
                    "content_score": 1.0,
                    "content_quality_score": 1.0,
                    "blockers": [SAFETY_CANDIDATE_BLOCKER],
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
            requested_count=1,
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

        policy = get_detection_policy("135", "full")
        decision = apply_detection_decision(
            gray,
            detection,
            config,
            make_analysis_cache(gray, "horizontal", policy.preprocess.content_evidence_image),
            {},
            policy,
            decision_contract_for_policy(policy),
        )

        self.assertEqual(decision.status, "needs_review")
        self.assertEqual(decision.confidence, 0.84)
        self.assertEqual(
            decision.final_review_reasons,
            ["evidence_combination_insufficient", "content_evidence_insufficient"],
        )
        self.assertEqual(
            decision.detail["decision_summary"]["status"],
            "needs_review",
        )

    def test_close_competition_is_final_decision_reason(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
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
            requested_count=1,
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
            "content_integrity_failed": False,
        }
        outer_alignment = {"used": True, "ok": True}

        decided = apply_decision_contract(
            gray,
            detection,
            config,
            content_detail,
            outer_alignment,
            policy=_decision_contract("135", "full"),
        )

        self.assertEqual(decided.final_review_reasons, ["candidate_competition_close"])
        self.assertEqual(decided.confidence, 0.84)
        self.assertEqual(
            decided.detail["decision_reason_inputs"][0]["signal"],
            "candidate_competition_close",
        )
        self.assertEqual(
            decided.detail["decision_signals"]["candidate_margin_to_second"],
            0.03,
        )

    def test_selection_records_competition_signal_without_candidate_review_reason(self) -> None:
        def candidate(confidence: float) -> DetectionCandidate:
            return DetectionCandidate(
                film_format="135",
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
                film_format="half",
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
            film_format="half",
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
            film_format="135",
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

        decided = apply_decision_contract(
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
            report_selected["final_review_reasons"],
            ["evidence_combination_insufficient", "outer_candidate_disagreement"],
        )
        self.assertEqual(report_selected["decision_status"], "needs_review")
        self.assertNotIn(
            "final_review_reasons",
            decided.detail["candidate_competition"]["top_candidates"][0],
        )

    def test_low_confidence_context_reasons_do_not_create_high_confidence_review(self) -> None:
        gray = np.zeros((100, 100), dtype=np.uint8)
        detection = DetectionCandidate(
            film_format="135",
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

        decided = apply_decision_contract(
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
