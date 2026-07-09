from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LowConfidenceContextContractTest(unittest.TestCase):
    def test_low_confidence_context_reasons_do_not_use_tail_or_post_check_names(self) -> None:
        banned = (
            "_apply_decision_" "tail_reasons",
            "decision" "_tail",
            "tail review" " reasons",
            "decision-tail" " reasons",
            "decision_post_check",
            "post-check review",
        )
        offenders: list[str] = []
        for path in (
            PROJECT_ROOT / "x5crop" / "detection" / "decision" / "final_decision.py",
            PROJECT_ROOT / "tools" / "tests" / "test_decision_reason_contract.py",
            PROJECT_ROOT / "ARCHITECTURE.md",
            PROJECT_ROOT / "CHANGELOG.md",
        ):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_low_confidence_context_reasons_belong_to_contract_applier(self) -> None:
        final_decision_text = (
            PROJECT_ROOT / "x5crop" / "detection" / "decision" / "final_decision.py"
        ).read_text(encoding="utf-8")
        contract_text = (
            PROJECT_ROOT / "x5crop" / "detection" / "decision" / "contract_applier.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("_apply_low_confidence_context_reasons", final_decision_text)
        self.assertNotIn("add_final_review_reason", final_decision_text)
        self.assertNotIn("_sync_decision_summary_status", final_decision_text)
        self.assertNotIn("sync_candidate_competition_decision_fields", final_decision_text)
        decision_gate_text = (
            PROJECT_ROOT / "x5crop" / "detection" / "decision" / "decision_gate.py"
        ).read_text(encoding="utf-8")
        self.assertIn("low_confidence_context", decision_gate_text)
        self.assertNotIn("_low_confidence_context_reason_inputs", contract_text)


if __name__ == "__main__":
    unittest.main()
