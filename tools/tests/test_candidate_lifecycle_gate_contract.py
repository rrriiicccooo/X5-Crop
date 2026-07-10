from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from x5crop.detection.candidate.assessment.candidate import apply_candidate_assessment_policy
from x5crop.detection.candidate.assessment.base_scoring import base_detection_assessment
from x5crop.detection.candidate.assessment.candidate_gate import candidate_gate_assessment
from x5crop.detection.candidate.assessment.content_candidate import (
    content_candidate_assessment_from_proposal,
    content_candidate_assessment_from_metrics,
)
from x5crop.detection.candidate.signals import candidate_signals
from x5crop.detection.evidence.frame_topology import frame_topology_evidence
from x5crop.detection.evidence.separator_continuity import separator_cross_axis_continuity_evidence
from x5crop.domain import Box, DetectionCandidate, Gap
from x5crop.formats import format_spec
from x5crop.gap_methods import GAP_DETECTED
from x5crop.geometry.detection_parameters import HardGapTrustParameters
from x5crop.policies.registry import get_detection_policy
from x5crop.run_config import RunConfig


class CandidateLifecycleGateContractTest(unittest.TestCase):
    def test_outer_size_uncertainty_is_candidate_diagnostic_not_gate_blocker(self) -> None:
        gate = candidate_gate_assessment(
            source="separator",
            separator_support_ok=True,
            separator_support_detail={"ok": True},
            partial_edge_safety_candidate_support_ok=False,
            partial_edge_safety_blocks_auto=False,
            partial_edge_safety_disqualifiers=set(),
            content_containment_ok=True,
            content_integrity_failed=False,
            content_support="ok",
            evidence_independence_ok=True,
            evidence_independence_detail={"ok": True, "reason": "ok"},
            signals=["outer_overcontains_holder_area", "outer_scope_uncertain"],
        )

        self.assertTrue(gate.passed)
        self.assertEqual(gate.blockers, [])
        self.assertEqual(gate.diagnostics, ["outer_overcontains_holder_area", "outer_scope_uncertain"])

    def test_content_outside_outer_blocks_candidate_gate(self) -> None:
        gate = candidate_gate_assessment(
            source="separator",
            separator_support_ok=True,
            separator_support_detail={"ok": True},
            partial_edge_safety_candidate_support_ok=False,
            partial_edge_safety_blocks_auto=False,
            partial_edge_safety_disqualifiers=set(),
            content_containment_ok=True,
            content_integrity_failed=False,
            content_support="ok",
            evidence_independence_ok=True,
            evidence_independence_detail={"ok": True, "reason": "ok"},
            signals=["content_outside_outer"],
        )

        self.assertFalse(gate.passed)
        self.assertEqual(gate.blockers, ["content_outside_outer"])

    def test_frame_topology_overlap_blocks_candidate_gate(self) -> None:
        evidence = frame_topology_evidence(
            [Box(0, 0, 120, 100), Box(110, 0, 220, 100)],
            expected_count=2,
        )

        self.assertFalse(evidence["ok"])
        self.assertEqual(evidence["candidate_signals"], ["frame_overlap_detected"])

        gate = candidate_gate_assessment(
            source="separator",
            separator_support_ok=True,
            separator_support_detail={"ok": True},
            partial_edge_safety_candidate_support_ok=False,
            partial_edge_safety_blocks_auto=False,
            partial_edge_safety_disqualifiers=set(),
            content_containment_ok=True,
            content_integrity_failed=False,
            content_support="ok",
            evidence_independence_ok=True,
            evidence_independence_detail={"ok": True, "reason": "ok"},
            signals=evidence["candidate_signals"],
        )

        self.assertFalse(gate.passed)
        self.assertEqual(gate.blockers, ["frame_overlap_detected"])
        self.assertEqual({check.code for check in gate.checks if not check.passed}, {"frame_topology"})

    def test_separator_cross_axis_continuity_blocks_local_content_edges(self) -> None:
        gray = np.full((24, 120), 128, dtype=np.uint8)
        gray[:4, 58:62] = 0
        gray[4:, 58:62] = np.array([0, 255, 0, 255], dtype=np.uint8)
        outer = Box(0, 0, 120, 24)
        gap = Gap(1, 60.0, 1.0, GAP_DETECTED, 58.0, 62.0)

        evidence = separator_cross_axis_continuity_evidence(
            gray,
            outer,
            [gap],
            pitch=60.0,
            parameters=HardGapTrustParameters(),
        )

        self.assertFalse(evidence["ok"])
        self.assertEqual(evidence["weak_gap_indexes"], [1])
        self.assertEqual(evidence["candidate_signals"], ["separator_cross_axis_continuity_weak"])

        gate = candidate_gate_assessment(
            source="separator",
            separator_support_ok=True,
            separator_support_detail={"ok": True},
            partial_edge_safety_candidate_support_ok=False,
            partial_edge_safety_blocks_auto=False,
            partial_edge_safety_disqualifiers=set(),
            content_containment_ok=True,
            content_integrity_failed=False,
            content_support="ok",
            evidence_independence_ok=True,
            evidence_independence_detail={"ok": True, "reason": "ok"},
            signals=evidence["candidate_signals"],
        )

        self.assertFalse(gate.passed)
        self.assertEqual(gate.blockers, ["separator_cross_axis_continuity_weak"])

    def test_separator_cross_axis_continuity_accepts_full_band_separator(self) -> None:
        gray = np.full((24, 120), 128, dtype=np.uint8)
        gray[:, 58:62] = 0
        evidence = separator_cross_axis_continuity_evidence(
            gray,
            Box(0, 0, 120, 24),
            [Gap(1, 60.0, 1.0, GAP_DETECTED, 58.0, 62.0)],
            pitch=60.0,
            parameters=HardGapTrustParameters(),
        )

        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["candidate_signals"], [])

    def test_unknown_candidate_signal_fails_contract(self) -> None:
        with self.assertRaises(ValueError):
            candidate_gate_assessment(
                source="separator",
                separator_support_ok=True,
                separator_support_detail={"ok": True},
                partial_edge_safety_candidate_support_ok=False,
                partial_edge_safety_blocks_auto=False,
                partial_edge_safety_disqualifiers=set(),
                content_containment_ok=True,
                content_integrity_failed=False,
                content_support="ok",
                evidence_independence_ok=True,
                evidence_independence_detail={"ok": True, "reason": "ok"},
                signals=["unowned_signal"],
            )

    def test_content_integrity_gate_combines_containment_and_harm_absence(self) -> None:
        gate = candidate_gate_assessment(
            source="separator",
            separator_support_ok=True,
            separator_support_detail={"ok": True},
            partial_edge_safety_candidate_support_ok=False,
            partial_edge_safety_blocks_auto=False,
            partial_edge_safety_disqualifiers=set(),
            content_containment_ok=False,
            content_integrity_failed=True,
            content_support="aspect_conflict",
            evidence_independence_ok=True,
            evidence_independence_detail={"ok": True, "reason": "ok"},
            signals=[],
        )

        checks = {check.code: check for check in gate.checks}
        self.assertIn("content_integrity", checks)
        self.assertNotIn("content_containment", checks)
        self.assertNotIn("content_harm_absent", checks)
        self.assertFalse(checks["content_integrity"].passed)
        self.assertEqual(checks["content_integrity"].signal, "content_aspect_conflict")
        self.assertEqual(gate.blockers, ["content_aspect_conflict"])

    def test_candidate_gate_result_is_structured_gate_not_candidate_signal(self) -> None:
        gray = np.zeros((100, 300), dtype=np.uint8)
        policy = get_detection_policy("135", "full")
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[
                Box(0, 0, 90, 100),
                Box(105, 0, 195, 100),
                Box(210, 0, 300, 100),
            ],
            gaps=[],
            confidence=0.10,
            detail={
                "outer_candidate_strategy": "base_outer",
                "outer_area_ratio": 0.80,
                "width_cv": 0.0,
                "width_cv_source": "photo_edges",
                "photo_width_cv": 0.0,
            },
        )
        config = RunConfig(
            input_path=Path("synthetic.tif"),
            output_dir=None,
            format_id="135",
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
            format_spec("135"),
            "separator",
            policy=policy,
        )

        assessment = assessed.detail["candidate_assessment"]
        self.assertFalse(assessment["candidate_gate"]["passed"])
        self.assertNotIn("candidate_gate_failed", candidate_signals(assessed))
        self.assertNotIn(
            "candidate_gate_failed",
            assessment["candidate_gate"]["blockers"],
        )

    def test_partial_three_frame_hard_separator_is_not_intrinsically_ambiguous(self) -> None:
        gray = np.zeros((100, 300), dtype=np.uint8)
        gray[:, ::2] = 255
        assessment = base_detection_assessment(
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
            get_detection_policy("135", "partial"),
        )

        self.assertGreater(assessment.confidence, 0.90)
        self.assertNotIn("partial_strip_count_candidate", assessment.candidate_signals)
        self.assertNotIn("partial_count_ambiguous", assessment.candidate_signals)
        self.assertEqual(assessment.detail["partial_count_assessment"]["reason"], "enough_frames_for_physical_assessment")

    def test_partial_single_frame_remains_intrinsically_ambiguous(self) -> None:
        gray = np.zeros((100, 120), dtype=np.uint8)
        gray[:, ::2] = 255
        assessment = base_detection_assessment(
            gray,
            Box(0, 0, 120, 100),
            [],
            [Box(0, 0, 120, 100)],
            1,
            format_spec("135"),
            "partial",
            get_detection_policy("135", "partial"),
        )

        self.assertLessEqual(
            assessment.confidence,
            get_detection_policy("135", "partial").scoring.base_detection.partial_one_cap,
        )
        self.assertIn("partial_count_ambiguous", assessment.candidate_signals)
        self.assertNotIn("partial_strip_count_candidate", assessment.candidate_signals)
        self.assertEqual(assessment.detail["partial_count_assessment"]["reason"], "single_frame_partial")

    def test_content_partial_candidate_diagnostics_do_not_emit_partial_count_reason(self) -> None:
        assessment = content_candidate_assessment_from_metrics(
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

        self.assertNotIn("partial_strip_count_candidate", assessment.diagnostics)
        self.assertEqual(assessment.detail["partial_candidate_role"], "content_guidance_not_count_evidence")

    def test_content_candidate_assessment_uses_candidate_assessment_owner(self) -> None:
        detection = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="partial",
            count=3,
            outer=Box(0, 0, 300, 100),
            frames=[],
            gaps=[],
            confidence=0.0,
            detail={
                "content_primary": {
                    "placement": "content_runs",
                    "usable_run_count": 3,
                    "selected_run_count": 3,
                    "median_mean": 0.20,
                    "median_coverage": 0.40,
                    "max_aspect_error": 0.01,
                }
            },
        )

        assessment = content_candidate_assessment_from_proposal(
            detection,
            SimpleNamespace(confidence_threshold=0.85),
            get_detection_policy("135", "partial").content,
        )

        self.assertEqual(assessment.detail["owner"], "candidate.assessment")



if __name__ == "__main__":
    unittest.main()
