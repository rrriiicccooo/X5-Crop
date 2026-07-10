from __future__ import annotations

from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


class DecisionOwnershipSourceContractTest(unittest.TestCase):
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

    def test_decision_contract_applier_uses_current_names(self) -> None:
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

    def test_evidence_policy_uses_signal_names_for_candidate_gate_inputs(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "candidate.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("review_reason:", text)
        self.assertNotIn(".review_reason", text)
        self.assertNotIn("candidate_blocker", text)
        self.assertIn("candidate_signal", text)

    def test_decision_gate_uses_explicit_assessment(self) -> None:
        decision_gate_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "decision_gate.py"
        )
        contract_applier_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "contract_applier.py"
        )
        gate_text = decision_gate_path.read_text(encoding="utf-8")
        contract_text = contract_applier_path.read_text(encoding="utf-8")

        self.assertIn("class DecisionGateAssessment", gate_text)
        self.assertIn('"decision_gate": decision_gate.report_detail()', contract_text)
        self.assertNotIn("class DecisionContextReviewAssessment", contract_text)
        self.assertNotIn(") -> tuple[list[str], list[dict[str, Any]]]", contract_text)
        self.assertNotIn("context_reasons, context_reason_inputs", contract_text)

    def test_decision_candidate_signal_inputs_are_current_gate_inputs(self) -> None:
        path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "contract_applier.py"
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
        applier = (source_root / "contract_applier.py").read_text(encoding="utf-8")
        self.assertIn("FinalDetection.from_candidate", applier)

    def test_decision_reason_mutation_helper_does_not_exist(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "reasons.py"
        self.assertFalse(path.exists())

    def test_decision_summary_uses_final_reason_and_signal_fields(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "contract_applier.py"
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
