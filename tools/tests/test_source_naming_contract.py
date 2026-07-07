from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SourceNamingContractTest(unittest.TestCase):
    def test_active_source_has_no_late_or_auxiliary_flow_terms(self) -> None:
        banned = (
            "late_outer",
            "auxiliary_outer",
            "late_refinement",
            "pending_late",
            "apply_late",
            "LateSeparator",
            "adjacent_late",
            'phase="late"',
            'phase="auxiliary"',
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

    def test_separator_width_theory_is_not_named_as_a_prior(self) -> None:
        banned = (
            "physical_width_prior",
            "SeparatorPhysicalWidthPrior",
            "separator_physical_width_prior",
            "width_relation_to_prior",
            "width_delta_to_prior",
            "ideal_width",
            "theoretical_frame_width",
            "narrower_than_prior",
            "matches_prior",
            "broader_than_prior",
            "prior_unavailable",
        )
        offenders: list[str] = []
        for root in (PROJECT_ROOT / "x5crop", PROJECT_ROOT / "tools" / "tests"):
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                if path == Path(__file__).resolve():
                    continue
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_physical_layer_does_not_read_candidate_assessment_or_decision_terms(self) -> None:
        banned = (
            "candidate_assessment",
            "auto_gate",
            "PASS",
            "REVIEW",
            "correction_family_available",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "physical"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_physical_layer_does_not_import_candidate_or_decision_packages(self) -> None:
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "physical"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module = node.module or ""
                if (
                    module.startswith("candidate")
                    or module.startswith("decision")
                    or module.startswith("x5crop.detection.candidate")
                    or module.startswith("x5crop.detection.decision")
                ):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {module}")

        self.assertEqual(offenders, [])

    def test_physical_layer_does_not_import_guidance_or_final_packages(self) -> None:
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "physical"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module = node.module or ""
                if (
                    module.startswith("guidance")
                    or module.startswith("final")
                    or module.startswith("x5crop.detection.guidance")
                    or module.startswith("x5crop.detection.final")
                ):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {module}")

        self.assertEqual(offenders, [])

    def test_physical_layer_does_not_keep_candidate_plan_modules(self) -> None:
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "physical"
        self.assertTrue(source_root.is_dir())
        offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for path in source_root.rglob("plan.py")
        ]

        self.assertEqual(offenders, [])

    def test_finalization_policy_does_not_own_decision_caps_or_reasons(self) -> None:
        from x5crop.policies.runtime.final import FinalizationPolicy

        banned = {
            "content_aspect_conflict_cap",
            "content_low_confidence_cap",
            "outer_mismatch_cap",
            "lucky_pass_risk_cap",
            "likely_partial_review_reason",
            "outer_candidate_disagreement_review_reason",
            "deskew_uncertain_review_reason",
        }
        self.assertTrue(banned.isdisjoint(FinalizationPolicy.__dataclass_fields__))

    def test_guidance_layer_does_not_own_final_candidate_scoring(self) -> None:
        banned = (
            "content_candidate_confidence_and_reasons",
            "review_reasons",
            "decision_contract",
            "policy_allows_auto",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "guidance"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_evidence_layer_does_not_name_evidence_as_final_decision_input(self) -> None:
        banned = (
            "used_for_decision",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "evidence"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_candidate_plan_does_not_name_source_contract_as_final_decision(self) -> None:
        banned = (
            "decision_contract",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "plan"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_candidate_assessment_uses_canonical_detail_names(self) -> None:
        banned = (
            "partial_extra_holder_frames",
            "partial_extra_holder_frames_gate_detail",
            "_apply_pre_decision_review_caps",
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

    def test_format_policy_modules_expose_only_unified_build_entry(self) -> None:
        banned = (
            "def full_policy",
            "def partial_policy",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "policies" / "formats"
        self.assertTrue(source_root.is_dir())
        for path in source_root.glob("format_*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
