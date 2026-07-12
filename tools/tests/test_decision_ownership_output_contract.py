from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_fixture, decide_candidate
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.report.read_models import candidate_gate_read_model, decision_gate_detail


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DecisionOwnershipOutputContractTest(unittest.TestCase):
    def test_decision_requires_typed_final_stage_inputs(self) -> None:
        parameters = inspect.signature(apply_decision_gate).parameters
        self.assertEqual(parameters["selection"].annotation, "SelectionResult")
        self.assertEqual(
            parameters["frame_bleed_plan"].annotation,
            "FrameBleedPlan",
        )
        self.assertEqual(
            parameters["transform_geometry"].annotation,
            "TransformGeometryEvidence",
        )

    def test_final_fields_exist_only_on_final_detection(self) -> None:
        candidate = candidate_fixture()
        self.assertFalse(hasattr(candidate, "status"))
        self.assertFalse(hasattr(candidate, "final_review_reasons"))
        decided = decide_candidate(candidate)
        self.assertEqual(decided.status, "approved_auto")

    def test_report_read_models_are_passive_projections(self) -> None:
        decided = decide_candidate()
        selected = decided.require_selection().selected
        self.assertTrue(candidate_gate_read_model(selected)["passed"])
        self.assertTrue(decision_gate_detail(decided)["passed"])

    def test_workflow_prepares_frame_bleed_before_decision(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/workflow.py").read_text()
        self.assertLess(
            source.index("prepare_frame_bleed("),
            source.index("apply_decision_gate("),
        )

    def test_decision_has_no_confidence_or_compatibility_gate(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/detection/decision/decision_gate.py"
        ).read_text()
        for legacy in (
            "confidence_cap",
            "confidence_floor",
            "candidate_gate_failed",
            "evidence_combination_insufficient",
        ):
            self.assertNotIn(legacy, source)
        self.assertNotIn('"review_reasons"', source)


if __name__ == "__main__":
    unittest.main()
