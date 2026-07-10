from __future__ import annotations

import ast
from inspect import Parameter, signature
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


class DecisionOwnershipSourceContractTest(unittest.TestCase):
    def test_decision_gate_requires_explicit_deskew_detail(self) -> None:
        from x5crop.detection.decision.decision_gate import apply_decision_gate

        self.assertIs(
            signature(apply_decision_gate).parameters["deskew_detail"].default,
            Parameter.empty,
        )
        source = (
            PROJECT_ROOT / "x5crop" / "detection" / "decision" / "decision_gate.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("deskew_detail or {}", source)

    def test_decision_consumes_evidence_without_building_it(self) -> None:
        decision_root = PROJECT_ROOT / "x5crop" / "detection" / "decision"
        offenders = []
        for path in decision_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in (
                "content_evidence_detail",
                "content_containment_detail",
                "outer_content_alignment_detail",
                "DetectionPolicy",
            ):
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{term}")
        self.assertEqual(offenders, [])

    def test_decision_gate_is_only_final_detection_factory_repo_wide(self) -> None:
        offenders = []
        for root in (PROJECT_ROOT / "x5crop", PROJECT_ROOT / "tools" / "tests"):
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    direct_constructor = (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "FinalDetection"
                    )
                    candidate_factory = (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "from_candidate"
                    )
                    if (direct_constructor or candidate_factory) and path.name != "decision_gate.py":
                        offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(sorted(set(offenders)), [])

    def test_decision_gate_is_only_final_detection_factory(self) -> None:
        decision_root = PROJECT_ROOT / "x5crop" / "detection" / "decision"
        final_factories = []
        status_owners = []
        for path in decision_root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "FinalDetection.from_candidate" in source:
                final_factories.append(path.name)
            if '"approved_auto"' in source or '"needs_review"' in source:
                status_owners.append(path.name)

        self.assertEqual(final_factories, ["decision_gate.py"])
        self.assertEqual(status_owners, ["decision_gate.py"])
        self.assertFalse((decision_root / "contract_applier.py").exists())

    def test_decision_contract_does_not_own_report_schema_identity(self) -> None:
        from x5crop.policies.decision.contract import DetectionDecisionContract

        self.assertNotIn("schema_id", DetectionDecisionContract.__dataclass_fields__)
        self.assertNotIn("schema_revision", DetectionDecisionContract.__dataclass_fields__)

    def test_active_gate_names_use_candidate_and_decision_contract_terms(self) -> None:
        banned = (
            "hard_review_reason_gate",
            "hard_final_review_reasons_block_auto",
            "auto_pass_gate",
            "finalization_gate",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_decision_contract_does_not_keep_runtime_signal_policy(self) -> None:
        from x5crop.policies.decision.contract import DetectionDecisionContract

        self.assertNotIn("risk", DetectionDecisionContract.__dataclass_fields__)

    def test_decision_gate_uses_current_names(self) -> None:
        banned = (
            "apply_final_decision_policy",
            "from .pass_review",
            "from x5crop.detection.decision.pass_review",
        )
        offenders: list[str] = []
        for root in (PROJECT_ROOT / "x5crop",):
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                if path == Path(__file__).resolve():
                    continue
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_evidence_policy_does_not_own_candidate_signal_labels(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "candidate.py"
        text = path.read_text(encoding="utf-8")
        signal_text = (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "signals.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("review_reason:", text)
        self.assertNotIn(".review_reason", text)
        self.assertNotIn("candidate_blocker", text)
        self.assertNotIn("candidate_signal", text)
        self.assertIn("SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_DETECTED", signal_text)

    def test_decision_gate_uses_explicit_assessment(self) -> None:
        decision_gate_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "decision_gate.py"
        )
        gate_text = decision_gate_path.read_text(encoding="utf-8")

        self.assertIn("class DecisionGateAssessment", gate_text)
        self.assertIn('"decision_gate": decision_gate.report_detail()', gate_text)
        self.assertNotIn("class DecisionContextReviewAssessment", gate_text)
        self.assertNotIn(") -> tuple[list[str], list[dict[str, Any]]]", gate_text)
        self.assertNotIn("context_reasons, context_reason_inputs", gate_text)

    def test_decision_candidate_signal_inputs_are_current_gate_inputs(self) -> None:
        path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "decision_gate.py"
        )
        text = path.read_text(encoding="utf-8")

        self.assertNotIn('"normalized_candidate_signals"', text)
        self.assertIn('"candidate_gate_input"', text)

    def test_decision_layer_constructs_final_reasons_once(self) -> None:
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "decision"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if ".final_review_reasons.append" in text or ".final_review_reasons =" in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])
        gate = (source_root / "decision_gate.py").read_text(encoding="utf-8")
        self.assertIn("FinalDetection.from_candidate", gate)

    def test_decision_reason_mutation_helper_does_not_exist(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "reasons.py"
        self.assertFalse(path.exists())

    def test_decision_summary_uses_final_reason_and_signal_fields(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "decision_gate.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn('"final_review_reasons"', text)
        self.assertIn('"decision_signals"', text)
        self.assertNotIn("decision_generated_final_review_reasons", text)
        self.assertNotIn("final_review_reasons_added", text)
        self.assertNotIn("final_review_reasons_added", text)
        self.assertNotIn("candidate_blockers_before_decision", text)
        self.assertNotIn("candidate_diagnostics_before_decision", text)

    def test_decision_content_quality_score_role_is_not_generic_score_role(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "evidence_summary.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn('"content_quality_score_role"', text)
        self.assertNotIn('"score_role": "quality_diagnostic_not_boundary_evidence"', text)



if __name__ == "__main__":
    unittest.main()
