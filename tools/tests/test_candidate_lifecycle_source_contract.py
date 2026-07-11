from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = PROJECT_ROOT / "x5crop/detection/candidate"
DETECTION_ROOT = PROJECT_ROOT / "x5crop/detection"


def _sources(root: Path):
    return tuple(path for path in root.rglob("*.py"))


class CandidateLifecycleSourceContractTest(unittest.TestCase):
    def test_plan_is_descriptor_only(self) -> None:
        source = "\n".join(path.read_text() for path in _sources(CANDIDATE_ROOT / "plan"))
        for forbidden in ("assess_candidate", "select_candidates", "FinalDetection"):
            self.assertNotIn(forbidden, source)

    def test_guidance_does_not_build_assess_or_decide(self) -> None:
        source = "\n".join(path.read_text() for path in _sources(DETECTION_ROOT / "guidance"))
        for forbidden in (
            "BuiltCandidate(",
            "CandidateGate",
            "DecisionGate",
            "approved_auto",
            "needs_review",
        ):
            self.assertNotIn(forbidden, source)

    def test_build_does_not_assess_or_decide(self) -> None:
        source = "\n".join(path.read_text() for path in _sources(CANDIDATE_ROOT / "build"))
        for forbidden in (
            "candidate_gate_assessment",
            "apply_decision_gate",
            "final_review_reasons",
            "approved_auto",
            "needs_review",
        ):
            self.assertNotIn(forbidden, source)

    def test_assessment_does_not_create_final_state(self) -> None:
        source = "\n".join(path.read_text() for path in _sources(CANDIDATE_ROOT / "assessment"))
        for forbidden in ('status="approved_auto"', 'status="needs_review"', "FinalDetection("):
            self.assertNotIn(forbidden, source)

    def test_selection_has_no_format_branch_or_final_authority(self) -> None:
        source = (CANDIDATE_ROOT / "selection/choose.py").read_text()
        for forbidden in (
            "format_id ==",
            "format_id in",
            "final_review_reasons",
            "approved_auto",
            "needs_review",
        ):
            self.assertNotIn(forbidden, source)

    def test_separator_support_is_independent_of_confidence(self) -> None:
        source = (CANDIDATE_ROOT / "assessment/separator_support.py").read_text()
        self.assertNotIn("confidence", source)
        self.assertNotIn("joint_score", source)

    def test_partial_edge_evidence_has_no_composite_score_gate(self) -> None:
        source = (DETECTION_ROOT / "evidence/partial_edge.py").read_text()
        for forbidden in ("joint_score", "geometry_score", "confidence"):
            self.assertNotIn(forbidden, source)

    def test_detection_stages_have_no_generic_detail_bus(self) -> None:
        offenders = []
        for root in (
            DETECTION_ROOT / "candidate",
            DETECTION_ROOT / "physical",
            DETECTION_ROOT / "guidance",
            DETECTION_ROOT / "evidence",
            DETECTION_ROOT / "decision",
        ):
            for path in _sources(root):
                source = path.read_text()
                if "detail: dict" in source or "DetectionCandidate" in source:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
