from __future__ import annotations

import ast
from inspect import Parameter, signature
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


DECISION_ROOT = PROJECT_ROOT / "x5crop/detection/decision"


class DecisionOwnershipSourceContractTest(unittest.TestCase):
    def test_decision_gate_assessment_is_the_decision_result(self) -> None:
        import x5crop.detection.decision.model as decision_model

        self.assertFalse(hasattr(decision_model, "DecisionResult"))
        self.assertTrue(hasattr(decision_model.DecisionGateAssessment, "status"))

    def test_decision_gate_requires_explicit_final_stage_inputs(self) -> None:
        from x5crop.detection.decision.decision_gate import apply_decision_gate

        parameters = signature(apply_decision_gate).parameters
        for name in (
            "selection",
            "frame_bleed_plan",
            "transform_geometry",
        ):
            self.assertIs(parameters[name].default, Parameter.empty)
        self.assertEqual(
            tuple(parameters),
            ("selection", "frame_bleed_plan", "transform_geometry"),
        )

    def test_decision_consumes_evidence_without_generating_candidates(self) -> None:
        banned = (
            "build_detection_for_outer",
            "select_detection_candidate",
            "DetectionConfiguration",
            "get_detection_configuration",
        )
        offenders: list[str] = []
        for path in DECISION_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT)}:{term}"
                for term in banned
                if term in source
            )
        self.assertEqual(offenders, [])

    def test_decision_and_finalization_have_single_factories(self) -> None:
        final_factories: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name):
                    if node.func.id == "FinalDetection":
                        final_factories.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(
            sorted(set(final_factories)),
            ["x5crop/detection/final/finalize.py"],
        )

    def test_decision_gate_owns_status_and_final_reason_creation(self) -> None:
        status_owners: list[str] = []
        for path in DECISION_ROOT.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            if '"approved_auto"' in source or '"needs_review"' in source:
                status_owners.append(path.name)
        self.assertEqual(status_owners, ["model.py"])

    def test_only_candidate_and_decision_gate_types_exist(self) -> None:
        gate_classes: set[str] = set()
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            gate_classes.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef) and node.name.endswith("GateAssessment")
            )
        self.assertEqual(
            gate_classes,
            {"CandidateGateAssessment", "DecisionGateAssessment"},
        )

    def test_decision_gate_uses_typed_assessment_and_specific_projection(self) -> None:
        gate_source = (DECISION_ROOT / "decision_gate.py").read_text(encoding="utf-8")
        model_source = (DECISION_ROOT / "model.py").read_text(encoding="utf-8")
        final_model_source = (
            PROJECT_ROOT / "x5crop/detection/final/model.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class DecisionGateAssessment", model_source)
        self.assertNotIn("class DecisionResult", model_source)
        self.assertNotIn("class FinalDetection", model_source)
        self.assertIn("class FinalDetection", final_model_source)
        self.assertIn("DECISION_GATE_REASON_BY_CODE", model_source)
        self.assertIn(
            "from .model import DECISION_GATE_REASON_BY_CODE",
            gate_source,
        )
        self.assertNotIn("_CANDIDATE_REASON_BY_CHECK", gate_source)
        self.assertNotIn("report_detail", gate_source)
        self.assertNotIn(".detail", gate_source)

    def test_decision_has_no_legacy_signal_cap_or_reducer_surface(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(DECISION_ROOT.rglob("*.py"))
        )
        for forbidden in (
            "decision_signals",
            "confidence_cap",
            "confidence_floor",
            "risk_summary",
            "lucky_pass",
            "normalized_review_reasons",
            "evidence_combination_insufficient",
        ):
            self.assertNotIn(forbidden, source)

    def test_decision_does_not_serialize_report_schema(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(DECISION_ROOT.rglob("*.py"))
        )
        self.assertNotIn("decision_summary", source)
        self.assertNotIn("schema_revision", source)
        self.assertNotIn("typed_read_model", source)

    def test_final_reason_mutation_helper_does_not_exist(self) -> None:
        self.assertFalse((DECISION_ROOT / "reasons.py").exists())
        self.assertFalse((DECISION_ROOT / "decision_signals.py").exists())


if __name__ == "__main__":
    unittest.main()
