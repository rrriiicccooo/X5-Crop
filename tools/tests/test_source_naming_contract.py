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

    def test_candidate_and_report_detail_use_gap_search_profile_not_separator_width_profile(self) -> None:
        banned = (
            'detail["separator_width_profile"]',
            '.get("separator_width_profile"',
            '"separator_width_profile":',
            '"separator_width_profile_gap_search"',
            "separator_width_profile_gap_search_detail",
            "skipped_separator_width_profile_gap_search_detail",
            "separator_width_profile_merged",
            "preserve_separator_width_profile",
        )
        offenders: list[str] = []
        paths = (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate",
            PROJECT_ROOT / "x5crop" / "detection" / "physical" / "outer" / "correction",
            PROJECT_ROOT / "x5crop" / "report",
        )
        for root in paths:
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
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
            "apply_output_bleed",
            "content_aspect_conflict_cap",
            "content_low_confidence_cap",
            "outer_mismatch_cap",
            "outer_candidate_disagreement_review_reason",
            "deskew_uncertain_review_reason",
        }
        self.assertTrue(banned.isdisjoint(FinalizationPolicy.__dataclass_fields__))

    def test_finalization_runtime_module_does_not_own_output_policy(self) -> None:
        from x5crop.policies.runtime import final

        banned = {
            "EdgeBleedProtectionPolicy",
            "OutputPolicy",
        }

        for name in banned:
            self.assertFalse(hasattr(final, name))
        self.assertEqual(
            tuple(final.__all__),
            ("ApprovedGeometryAdjustmentPolicy", "FinalizationPolicy"),
        )

    def test_output_policy_is_owned_by_runtime_output_module(self) -> None:
        from x5crop.policies.runtime.output import (
            EdgeBleedProtectionPolicy,
            OutputPolicy,
        )

        self.assertIn("edge_bleed_protection", OutputPolicy.__dataclass_fields__)
        self.assertIn("apply_output_bleed", OutputPolicy.__dataclass_fields__)
        self.assertIn("guard_ratio", EdgeBleedProtectionPolicy.__dataclass_fields__)

    def test_finalization_assembly_does_not_own_diagnostics_policy(self) -> None:
        from x5crop.policies.assembly import finalization

        self.assertFalse(hasattr(finalization, "diagnostics_policy"))
        self.assertEqual(tuple(finalization.__all__), ("finalization_policy",))

    def test_report_policy_is_not_owned_by_diagnostics_modules(self) -> None:
        from x5crop.policies.assembly import common
        from x5crop.policies.runtime import diagnostics

        self.assertFalse(hasattr(diagnostics, "ReportPolicy"))
        self.assertFalse(hasattr(common, "report_policy"))

    def test_report_schema_identity_is_not_version_named(self) -> None:
        banned = (
            "REPORT_SCHEMA_VERSION",
            "v4_9_policy_schema",
            "schema_version",
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

    def test_output_evidence_policy_is_not_owned_by_diagnostics_modules(self) -> None:
        from x5crop.policies.assembly import diagnostics
        from x5crop.policies.runtime import diagnostics as runtime_diagnostics

        banned = (
            "OutputOverlapEvidencePolicy",
            "RuntimeOutputEvidencePolicy",
            "output_overlap_evidence",
        )
        for name in banned:
            self.assertFalse(hasattr(runtime_diagnostics, name))
            self.assertNotIn(name, tuple(diagnostics.__all__))

    def test_output_overlap_evidence_does_not_use_diagnostic_ownership_name(self) -> None:
        offenders: list[str] = []
        banned = ("diagnostic_" + "overlap", "Diagnostic" + "Overlap")
        for root in (PROJECT_ROOT / "x5crop", PROJECT_ROOT / "tools" / "tests"):
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if any(term in text for term in banned):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

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

    def test_content_candidate_policy_does_not_use_final_review_only_terms(self) -> None:
        offenders: list[str] = []
        banned = (
            "review_only",
            '"review_only"',
            '"assessment_required"',
        )
        for path in (
            PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "content.py",
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "content.py",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance" / "content_model.py",
        ):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_decision_contract_does_not_own_output_or_diagnostics_policy(self) -> None:
        from x5crop.policies.decision.contract import DetectionDecisionContract

        banned = {
            "output",
            "diagnostics",
        }

        self.assertTrue(banned.isdisjoint(DetectionDecisionContract.__dataclass_fields__))

    def test_decision_contract_applier_uses_current_names(self) -> None:
        banned = (
            "apply_final_decision_policy",
            "from .pass_review",
            "from x5crop.detection.decision.pass_review",
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

    def test_guidance_layer_does_not_own_final_candidate_scoring(self) -> None:
        banned = (
            "content_candidate_confidence_and_reasons",
            "final_review_reasons",
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

    def test_content_candidate_assessment_uses_diagnostic_naming(self) -> None:
        banned = (
            "content_candidate_confidence_and_reasons",
            "proposal_reasons",
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
            '"final_review_reasons"',
            "final_review_reasons_ok",
            "requires_no_final_review_reasons",
            "review_reason:",
            ".review_reason",
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

    def test_candidate_plan_uses_gap_search_profiles_detail_name(self) -> None:
        banned = (
            '"gap_profiles":',
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

    def test_evidence_policy_uses_signal_names_for_candidate_gate_inputs(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "candidate.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("review_reason:", text)
        self.assertNotIn(".review_reason", text)
        self.assertNotIn("candidate_blocker", text)
        self.assertIn("candidate_signal", text)

    def test_candidate_assessment_uses_canonical_detail_names(self) -> None:
        banned = (
            "partial_extra_holder_frames",
            "partial_extra_holder_frames_gate_detail",
            "_apply_pre_decision_review_caps",
            "HARD_REVIEW_REASONS",
            "hard_review_reason_present",
            '"hard_reasons"',
            '"owner": "candidate_assessment"',
            '"owner": "candidate"',
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

    def test_selection_uncertainty_is_not_named_as_candidate_review_reason(self) -> None:
        banned = (
            "candidate_final_review_reasons_before_decision",
            "candidate_competition_uncertain",
            "content_candidate_final_review_reasons",
            "recommended_final_review_reason",
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

    def test_candidate_selection_summary_uses_candidate_signal_names(self) -> None:
        path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "selection"
            / "choose.py"
        )
        text = path.read_text(encoding="utf-8")

        self.assertNotIn('"final_review_reasons"', text)
        self.assertIn('"candidate_signals"', text)

    def test_candidate_build_detail_does_not_carry_assessment_state(self) -> None:
        banned = (
            "base_scoring_applied",
            "base_scoring_owner",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "candidate"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_base_scoring_uses_candidate_signal_code_names(self) -> None:
        base_scoring_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "base_scoring.py"
        )
        architecture_text = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
        base_scoring_text = base_scoring_path.read_text(encoding="utf-8")

        self.assertIn("candidate_signals", base_scoring_text)
        self.assertIn("class BaseDetectionAssessment", base_scoring_text)
        self.assertNotIn("base review reasons", architecture_text)
        self.assertNotIn("confidence, reasons", base_scoring_text)
        self.assertNotIn("_pre_nearby_reasons", base_scoring_text)
        self.assertNotIn("_geometry_reasons", base_scoring_text)

    def test_base_scoring_contract_uses_explicit_assessment_result(self) -> None:
        banned = (
            "confidence, candidate_signals, detail = base_detection_assessment",
            "_confidence, candidate_signals, detail = base_detection_assessment",
            "confidence, candidate_signals, base_detail = base_detection_assessment",
            "pre_nearby_confidence,",
            "geometry_confidence,",
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

    def test_content_candidate_contract_uses_explicit_assessment_result(self) -> None:
        content_candidate_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "content_candidate.py"
        )
        content_candidate_text = content_candidate_path.read_text(encoding="utf-8")
        self.assertIn("class ContentCandidateAssessment", content_candidate_text)

        banned = (
            "content_candidate_confidence_and_diagnostics",
            "proposal_confidence, proposal_diagnostics, proposal_detail",
            "confidence, diagnostics, detail = content_candidate_confidence_and_diagnostics",
            "_confidence, diagnostics, detail = content_candidate_confidence_and_diagnostics",
            "_confidence, _diagnostics, detail = content_candidate_assessment_from_proposal",
            "tuple[float, list[str], dict[str, Any]]",
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

    def test_separator_support_contract_uses_explicit_result(self) -> None:
        support_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "separator_support.py"
        )
        support_text = support_path.read_text(encoding="utf-8")
        self.assertIn("class SeparatorSupportResult", support_text)
        self.assertIn("class SeparatorSupportCheck", support_text)

        banned = (
            "separator_" "score_ok",
            "separator_" "gate_detail",
            ") -> tuple[bool, dict[str, Any]]",
            ") -> tuple[bool, str]",
            "ok, reason = separator_support_",
            "broad_ok, broad_reason",
            "edge_ok, edge_reason",
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

    def test_candidate_gate_assessment_uses_explicit_result(self) -> None:
        candidate_gate_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "candidate_gate.py"
        )
        candidate_assessment_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "candidate.py"
        )
        self.assertFalse(
            (
                PROJECT_ROOT
                / "x5crop"
                / "detection"
                / "candidate"
                / "assessment"
                / "blockers.py"
            ).exists()
        )
        gate_text = candidate_gate_path.read_text(encoding="utf-8")
        assessment_text = candidate_assessment_path.read_text(encoding="utf-8")

        self.assertIn("class CandidateGateAssessment", gate_text)
        self.assertIn("candidate_gate_assessment", assessment_text)
        self.assertIn('"candidate_gate": candidate_gate.report_detail()', assessment_text)
        self.assertNotIn("class CandidateReasonBuckets", assessment_text)
        self.assertNotIn("CANDIDATE_AUTO_GATE_BLOCKING_REASONS", gate_text)
        self.assertNotIn("CANDIDATE_AUTO_GATE_BLOCKING_REASONS", assessment_text)
        self.assertNotIn("auto_gate_inputs", assessment_text)
        self.assertNotIn(
            "candidate_blockers, candidate_diagnostics = _candidate_signal_buckets",
            assessment_text,
        )

    def test_candidate_signals_are_failure_or_diagnostic_not_success_states(self) -> None:
        from x5crop.detection.candidate.signals import CANDIDATE_SIGNAL_TAXONOMY

        offenders = [
            signal
            for signal in CANDIDATE_SIGNAL_TAXONOMY
            if signal.endswith("_ok")
            or signal.endswith("_stable")
            or signal.endswith("_passed")
        ]

        self.assertEqual(offenders, [])

    def test_old_candidate_signal_group_names_are_removed(self) -> None:
        banned = (
            "separator_family_support_incomplete",
            "SIGNAL_SEPARATOR_FAMILY_SUPPORT_INCOMPLETE",
            "PHOTO_GEOMETRY_BLOCKER_SIGNALS",
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

    def test_candidate_layer_routes_signal_mutation_through_candidate_helper(self) -> None:
        banned = (
            ".final_review_reasons.append",
            ".final_review_reasons =",
            "final_review_reasons=candidate_signals",
            "final_review_reasons=merged_candidate_signals",
            "final_review_reasons=normalized_candidate_signals",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "candidate"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_candidate_signal_helper_does_not_write_final_reason_field(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "reasons.py").exists()
        )
        path = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "signals.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("detection.final_review_reasons =", text)
        self.assertIn('detection.detail[CANDIDATE_SIGNALS]', text)

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

    def test_candidate_signal_taxonomy_uses_physical_signal_names(self) -> None:
        banned = (
            "candidate_" "reason_signal",
            "candidate_signal_" "signal",
            "weak_" "separators",
            "mostly_" "equal_split",
            "too_few_" "detected_separators",
            "partial_too_" "ambiguous",
            "partial_outer_" "leading_content",
            "outer_box_" "too_large",
            "outer_box_" "uncertain",
            "unstable_" "frame_width",
            "outer_content_" "bbox_mismatch",
            '"low_' '"confidence"',
        )
        offenders: list[str] = []
        for root in (PROJECT_ROOT / "x5crop", PROJECT_ROOT / "tools" / "tests"):
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_content_mismatch_selector_override_is_removed(self) -> None:
        banned = (
            "ContentMismatchReviewSelectionPolicy",
            "ContentMismatchCandidateSelectionPolicy",
            "content_mismatch_review",
            "content_mismatch_candidate",
            "required_review_reason",
            "required_candidate_signal",
            "content_candidate_signals",
            "content_candidate_mismatch",
            "select_separator_review_candidate_on_content_mismatch",
            "select_separator_candidate_for_content_mismatch",
            "separator_" "review" "_on_mismatch",
        )
        offenders: list[str] = []
        for path in (
            PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "candidate.py",
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "candidate.py",
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "presets.py",
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "format_presets.py",
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "selection" / "choose.py",
        ):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_mode_details_use_mode_or_candidate_signal_names(self) -> None:
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "modes"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if '"final_review_reasons"' in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

    def test_mode_layer_routes_reason_mutation_through_candidate_helper(self) -> None:
        banned = (
            ".final_review_reasons.append",
            ".final_review_reasons =",
            "final_review_reasons=normalized_candidate_signals",
            "final_review_reasons=candidate_signals",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "modes"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_dual_lane_plan_delegates_content_assessment(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "modes" / "dual_lane_candidate.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("content_evidence_detail", text)
        self.assertNotIn("outer_content_alignment_detail", text)
        self.assertNotIn("REASON_CONTENT_ASPECT_CONFLICT", text)
        self.assertIn("apply_dual_lane_content_assessment", text)

    def test_candidate_plan_delegates_safety_candidate_assessment(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "lifecycle.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("safety_candidate.confidence = min", text)
        self.assertNotIn("safety_candidate.final_review_reasons.append", text)
        self.assertNotIn('"safety_candidate_review_only"', text)
        self.assertNotIn('assessment["auto_gate"] = False', text)
        self.assertIn("apply_safety_candidate_assessment", text)

    def test_safety_candidate_detail_uses_candidate_and_decision_names(self) -> None:
        banned = (
            "SAFETY_CANDIDATE_REVIEW_ONLY_REASON",
            "safety_candidate_review_only",
            "review_only_safety_equal_split",
            "changes_pass_review",
            '"review_only": True',
            "auto_pass_eligible",
            "changes_final_decision",
        )
        offenders: list[str] = []
        for path in (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "assessment" / "safety.py",
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "proposal" / "safety.py",
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "execution" / "source_candidates.py",
            PROJECT_ROOT / "x5crop" / "detection" / "evidence" / "read_only.py",
        ):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_read_only_diagnostics_use_effects_detail(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "evidence" / "read_only.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn('"effects"', text)
        self.assertIn('"output": False', text)
        self.assertIn('"confidence": False', text)
        self.assertIn('"decision": False', text)
        self.assertIn("output_overlap_counts", text)
        self.assertNotIn("changes_output", text)
        self.assertNotIn("changes_confidence", text)
        self.assertNotIn("changes_final_decision", text)

    def test_decision_package_marker_does_not_reexport_runtime_helpers(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "__init__.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        import_from_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]

        self.assertEqual(import_from_nodes, [])

    def test_decision_layer_routes_final_reason_mutation_through_reason_helper(self) -> None:
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "decision"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            if path.name == "reasons.py":
                continue
            text = path.read_text(encoding="utf-8")
            if ".final_review_reasons.append" in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

    def test_decision_reason_helper_does_not_expose_append_mutation(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "reasons.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn("set_final_review_reasons", text)
        self.assertNotIn("add_final_review_reason", text)
        self.assertNotIn("final_review_reasons.append", text)

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

    def test_finalization_does_not_generate_decision_output_evidence(self) -> None:
        banned = (
            "output_overlap_evidence_detail",
            "get_detection_policy",
            "policies.registry",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "final"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_outer_alignment_evidence_does_not_own_correction_policy(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "evidence" / "outer_alignment.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn("OuterAlignmentEvidencePolicy", text)
        self.assertNotIn("ContentContainmentCorrectionPolicy", text)
        self.assertNotIn("corrected_outer_from_alignment", text)

    def test_runtime_policy_lookup_stays_out_of_output_and_detection_layers(self) -> None:
        banned = ("get_detection_policy", "policies.registry")
        checked_paths = [
            PROJECT_ROOT / "x5crop" / "detection",
            PROJECT_ROOT / "x5crop" / "debug",
            PROJECT_ROOT / "x5crop" / "report",
            PROJECT_ROOT / "x5crop" / "runtime" / "analysis_reuse.py",
        ]
        offenders: list[str] = []
        for root in checked_paths:
            paths = [root] if root.is_file() else list(root.rglob("*.py"))
            for path in paths:
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_output_bleed_helpers_live_in_output_layer(self) -> None:
        offenders: list[str] = []
        banned = (
            "detection.final.output_bleed",
            "from .output_bleed",
            "final.output_bleed",
        )
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

        self.assertTrue((PROJECT_ROOT / "x5crop" / "output" / "bleed.py").is_file())

if __name__ == "__main__":
    unittest.main()
