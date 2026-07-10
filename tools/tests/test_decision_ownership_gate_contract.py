from __future__ import annotations

from dataclasses import replace
import unittest
from pathlib import Path

import numpy as np

from tools.tests.decision_contract_support import (
    candidate_gate_detail as _candidate_gate_detail,
    content_ok_detail as _content_ok_detail,
    decision_contract as _decision_contract,
    decision_test_config as _decision_test_config,
)
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
from x5crop.domain import Box, DetectionCandidate
from x5crop.formats import format_spec
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.decision.contract import decision_contract_for_policy
from x5crop.run_config import RunConfig
from x5crop.runtime.output_protection import prepare_output_protection


class DecisionOwnershipGateContractTest(unittest.TestCase):
    def test_decision_contract_report_does_not_expose_unused_candidate_policy(self) -> None:
        from x5crop.policies.reporting import decision_contract_report_detail

        detail = decision_contract_report_detail(_decision_contract("135", "full"))

        self.assertNotIn("candidate_policy", detail)
        self.assertNotIn("risk_policy", detail)
        self.assertIn("decision_policy", detail)
        self.assertNotIn("output_policy", detail)
        self.assertNotIn("diagnostics_policy", detail)
        self.assertNotIn(
            "content_evidence_insufficient_reason",
            detail["decision_policy"],
        )

    def test_final_review_reasons_are_owned_by_decision_inputs(self) -> None:
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
            format_id="135",
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
            format_id="135",
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
            format_id="135",
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
            format_id="135-dual",
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
        config = RunConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            format_id="135",
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

    def test_unresolved_exposure_overlap_is_final_decision_signal(self) -> None:
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
                    "widest_overlap_band_px": 140.0,
                    "reason": "exposure_overlap_detected",
                },
                "output_protection_plan": {
                    "exposure_overlap_detected": True,
                    "feasible": False,
                    "reason": "exposure_overlap_exceeds_bleed_capacity",
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

        self.assertEqual(decided.final_review_reasons, ["exposure_overlap_unresolved"])
        self.assertTrue(decided.detail["decision_signals"]["exposure_overlap_unresolved"])
        self.assertEqual(
            [item["signal"] for item in decided.detail["decision_reason_inputs"]],
            ["exposure_overlap_unresolved"],
        )

    def test_final_status_requires_no_final_review_reasons_with_low_threshold(self) -> None:
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
        config = RunConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            format_id="135",
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
        cache = make_analysis_cache(
            gray,
            "horizontal",
            policy.preprocess.content_evidence_image,
        )
        prepare_output_protection(gray, detection, config, cache, policy)
        decision = apply_detection_decision(
            gray,
            detection,
            config,
            cache,
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
                "candidate_competition": {
                    "margin_to_second": 0.03,
                    "partial_full_conflict": False,
                },
            },
        )
        config = RunConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            format_id="135",
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



if __name__ == "__main__":
    unittest.main()
