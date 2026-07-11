from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


CANDIDATE_ROOT = PROJECT_ROOT / "x5crop/detection/candidate"
DETECTION_ROOT = PROJECT_ROOT / "x5crop/detection"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class CandidateLifecycleSourceContractTest(unittest.TestCase):
    def test_candidate_plan_is_a_pure_descriptor_layer(self) -> None:
        banned = (
            "DetectionCandidate",
            "build_detection_for_outer",
            "base_detection_assessment",
            "select_detection_candidate",
            ".confidence",
            ".frames",
        )
        offenders: list[str] = []
        for path in (CANDIDATE_ROOT / "plan").glob("*.py"):
            source = _source(path)
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT)}:{term}"
                for term in banned
                if term in source
            )
        self.assertEqual(offenders, [])

    def test_guidance_does_not_build_or_decide_candidates(self) -> None:
        banned = (
            "DetectionCandidate(",
            "CandidateGate",
            "DecisionGate",
            "approved_auto",
            "needs_review",
        )
        offenders: list[str] = []
        for path in (DETECTION_ROOT / "guidance").rglob("*.py"):
            source = _source(path)
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT)}:{term}"
                for term in banned
                if term in source
            )
        self.assertEqual(offenders, [])

    def test_candidate_build_does_not_assess_or_decide(self) -> None:
        banned = (
            "candidate_gate",
            "decision_gate",
            "final_review_reasons",
            "approved_auto",
            "needs_review",
        )
        offenders: list[str] = []
        for path in (CANDIDATE_ROOT / "build").rglob("*.py"):
            source = _source(path)
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT)}:{term}"
                for term in banned
                if term in source
            )
        self.assertEqual(offenders, [])

    def test_selection_is_the_only_geometry_consensus_writer(self) -> None:
        offenders: list[str] = []
        for path in DETECTION_ROOT.rglob("*.py"):
            if "candidate/selection" in path.as_posix():
                continue
            source = _source(path)
            if 'detail["selection_geometry_consensus"] =' in source:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_selection_never_writes_final_decision_fields(self) -> None:
        source = _source(CANDIDATE_ROOT / "selection/choose.py")
        self.assertNotIn("final_review_reasons", source)
        self.assertNotIn("approved_auto", source)
        self.assertNotIn("needs_review", source)

    def test_candidate_assessment_owns_the_only_candidate_gate_builder(self) -> None:
        writers: list[str] = []
        for path in DETECTION_ROOT.rglob("*.py"):
            tree = ast.parse(_source(path), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "candidate_gate_assessment":
                        writers.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertTrue(writers)
        self.assertTrue(
            all(
                "candidate/assessment" in writer or "modes" in writer
                for writer in writers
            )
        )

    def test_mode_candidates_delegate_the_shared_gate_model(self) -> None:
        for name in ("review_only.py", "dual_lane_merge.py"):
            source = _source(DETECTION_ROOT / "modes" / name)
            self.assertIn("apply_mode_candidate_assessment", source)

    def test_base_scoring_returns_score_and_measurements_only(self) -> None:
        source = _source(CANDIDATE_ROOT / "assessment/base_scoring.py")
        self.assertIn("class BaseDetectionAssessment", source)
        for forbidden in (
            "candidate_signals",
            "confidence_caps",
            "final_review_reasons",
            "candidate_gate",
        ):
            self.assertNotIn(forbidden, source)

    def test_separator_support_is_independent_of_candidate_confidence(self) -> None:
        source = _source(CANDIDATE_ROOT / "assessment/separator_support.py")
        self.assertNotIn("confidence", source)
        self.assertNotIn("joint_score", source)
        self.assertNotIn("threshold", source)

    def test_candidate_gate_uses_typed_evidence_and_proof_paths(self) -> None:
        gate_source = _source(CANDIDATE_ROOT / "assessment/candidate_gate.py")
        assessment_source = _source(CANDIDATE_ROOT / "assessment/candidate.py")

        self.assertIn("class CandidateGateInput", gate_source)
        self.assertIn("class BoundaryProofPath", gate_source)
        self.assertIn("candidate_gate_assessment", assessment_source)
        self.assertIn('"candidate_gate": gate.report_detail()', assessment_source)

    def test_old_signal_cap_and_blocker_surfaces_do_not_exist(self) -> None:
        for relative in (
            "signals.py",
            "assessment/confidence_caps.py",
            "assessment/blockers.py",
            "assessment/support_calibration.py",
        ):
            self.assertFalse((CANDIDATE_ROOT / relative).exists())

    def test_candidate_layer_never_writes_final_decision_fields(self) -> None:
        offenders: list[str] = []
        for path in CANDIDATE_ROOT.rglob("*.py"):
            source = _source(path)
            for term in (
                ".final_review_reasons =",
                ".final_review_reasons.append",
                'status="approved_auto"',
                'status="needs_review"',
            ):
                if term in source:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{term}")
        self.assertEqual(offenders, [])

    def test_content_candidate_uses_diagnostics_not_final_reasons(self) -> None:
        source = _source(CANDIDATE_ROOT / "assessment/content_candidate.py")
        self.assertIn("diagnostics", source)
        self.assertNotIn("final_review_reasons", source)
        self.assertNotIn("review_only", source)

    def test_partial_edge_safety_does_not_gate_on_composite_scores(self) -> None:
        source = _source(CANDIDATE_ROOT / "assessment/partial_holder.py")
        for forbidden in (
            "joint_score_low",
            "geometry_score_low",
            "min_joint_score",
            "min_geometry_score",
        ):
            self.assertNotIn(forbidden, source)

    def test_candidate_selection_has_no_format_identity_branch(self) -> None:
        source = _source(CANDIDATE_ROOT / "selection/choose.py")
        self.assertNotIn('format_id ==', source)
        self.assertNotIn('format_id in', source)


if __name__ == "__main__":
    unittest.main()
