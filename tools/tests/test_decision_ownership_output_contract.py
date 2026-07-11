from __future__ import annotations

from pathlib import Path
import inspect
import unittest

from tools.tests.physical_gate_support import candidate_fixture, decide_candidate
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.report.read_models import candidate_gate_detail, decision_gate_detail


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DecisionOwnershipOutputContractTest(unittest.TestCase):
    def test_decision_requires_typed_output_protection_plan(self) -> None:
        annotation = inspect.signature(apply_decision_gate).parameters[
            "output_protection_plan"
        ].annotation
        self.assertEqual(annotation, "OutputProtectionPlan")

    def test_final_fields_exist_only_on_final_detection(self) -> None:
        candidate = candidate_fixture()
        self.assertFalse(hasattr(candidate, "status"))
        self.assertFalse(hasattr(candidate, "final_review_reasons"))

        decided = decide_candidate(candidate)
        self.assertEqual(decided.status, "approved_auto")
        self.assertEqual(decided.final_review_reasons, [])

    def test_report_read_models_project_current_gate_sections(self) -> None:
        decided = decide_candidate()

        self.assertTrue(candidate_gate_detail(decided)["passed"])
        self.assertTrue(decision_gate_detail(decided)["passed"])

    def test_decision_summary_does_not_duplicate_final_fields(self) -> None:
        decided = decide_candidate()
        summary = decided.detail["decision_summary"]

        self.assertEqual(set(summary), {"decision_gate"})
        self.assertNotIn("status", summary)
        self.assertNotIn("final_review_reasons", summary)

    def test_workflow_builds_output_protection_before_decision(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/runtime/workflow.py"
        ).read_text(encoding="utf-8")

        self.assertLess(
            source.index("prepare_output_protection("),
            source.index("apply_decision_gate("),
        )

    def test_decision_source_has_no_signal_cap_or_threshold_compatibility(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/detection/decision/decision_gate.py"
        ).read_text(encoding="utf-8")

        for legacy in (
            "decision_signals",
            "confidence_cap",
            "confidence_floor",
            "candidate_competition",
            "candidate_gate_failed",
            "evidence_combination_insufficient",
        ):
            self.assertNotIn(legacy, source)

    def test_debug_status_has_no_confidence_threshold(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/debug/status.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("threshold", source)


if __name__ == "__main__":
    unittest.main()
