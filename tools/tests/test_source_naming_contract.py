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
            "lucky_pass_risk_cap",
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

    def test_runtime_risk_policy_is_not_owned_by_diagnostics_modules(self) -> None:
        from x5crop.policies.assembly import diagnostics
        from x5crop.policies.runtime import diagnostics as runtime_diagnostics

        banned = (
            "OverlapBleedRiskPolicy",
            "LuckyPassRiskPolicy",
            "overlap_bleed_risk",
            "lucky_pass_risk",
        )
        for name in banned:
            self.assertFalse(hasattr(runtime_diagnostics, name))
            self.assertNotIn(name, tuple(diagnostics.__all__))

    def test_overlap_bleed_risk_does_not_use_diagnostic_ownership_name(self) -> None:
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
            "hard_review_reasons_block_auto",
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

    def test_decision_contract_does_not_keep_unused_review_only_flags(self) -> None:
        from x5crop.policies.decision.contract import RiskPolicy

        banned = {
            "content_only_candidates_review_only",
            "safety_candidates_review_only",
        }

        self.assertTrue(banned.isdisjoint(RiskPolicy.__dataclass_fields__))

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
            '"review_reasons"',
            "review_reasons_ok",
            "requires_no_review_reasons",
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

    def test_candidate_policy_uses_blocker_names_for_candidate_gate_inputs(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "candidate.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("review_reason:", text)
        self.assertNotIn(".review_reason", text)
        self.assertIn("candidate_blocker", text)

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

    def test_selection_risk_is_not_named_as_candidate_review_reason(self) -> None:
        banned = (
            "candidate_review_reasons_before_decision",
            "candidate_competition_uncertain",
            "content_candidate_review_reasons",
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

    def test_candidate_selection_summary_uses_candidate_reason_names(self) -> None:
        path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "selection"
            / "choose.py"
        )
        text = path.read_text(encoding="utf-8")

        self.assertNotIn('"review_reasons"', text)
        self.assertIn('"candidate_reasons"', text)

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

    def test_candidate_layer_routes_reason_mutation_through_candidate_helper(self) -> None:
        banned = (
            ".review_reasons.append",
            ".review_reasons =",
            "review_reasons=candidate_reasons",
            "review_reasons=merged_candidate_reasons",
            "review_reasons=normalized_candidate_reasons",
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

    def test_candidate_reason_helper_does_not_write_final_reason_field(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "reasons.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("detection.review_reasons =", text)
        self.assertIn('detection.detail[CANDIDATE_REASONS]', text)

    def test_decision_candidate_reason_inputs_name_legacy_reducer_explicitly(self) -> None:
        path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "contract_applier.py"
        )
        text = path.read_text(encoding="utf-8")

        self.assertNotIn('"normalized_candidate_reasons"', text)
        self.assertIn('"legacy_reduced_candidate_reasons"', text)

    def test_content_mismatch_selector_uses_candidate_selection_names(self) -> None:
        banned = (
            "ContentMismatchReviewSelectionPolicy",
            "content_mismatch_review",
            "required_review_reason",
            "required_candidate_reason",
            "content_candidate_reasons",
            "select_separator_review_candidate_on_content_mismatch",
            "separator_review_on_mismatch",
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

    def test_mode_details_use_mode_or_candidate_reason_names(self) -> None:
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "modes"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if '"review_reasons"' in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

    def test_mode_layer_routes_reason_mutation_through_candidate_helper(self) -> None:
        banned = (
            ".review_reasons.append",
            ".review_reasons =",
            "review_reasons=normalized_candidate_reasons",
            "review_reasons=candidate_reasons",
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
        path = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "plan" / "dual_lane.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("content_evidence_detail", text)
        self.assertNotIn("outer_content_alignment_detail", text)
        self.assertNotIn("REASON_CONTENT_ASPECT_CONFLICT", text)
        self.assertIn("apply_dual_lane_content_assessment", text)

    def test_candidate_plan_delegates_safety_candidate_assessment(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "plan" / "run.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("safety_candidate.confidence = min", text)
        self.assertNotIn("safety_candidate.review_reasons.append", text)
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
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "plan" / "sources.py",
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
        self.assertIn("single_anchor_evidence_risk", text)
        self.assertNotIn("single_anchor_pass_risk", text)
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
            if ".review_reasons.append" in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

    def test_decision_reason_helper_does_not_expose_append_mutation(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "reasons.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn("set_final_review_reasons", text)
        self.assertNotIn("add_final_review_reason", text)
        self.assertNotIn("review_reasons.append", text)

    def test_decision_summary_uses_generated_not_added_reason_field(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "contract_applier.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn("decision_generated_review_reasons", text)
        self.assertNotIn("final_review_reasons_added", text)
        self.assertNotIn("review_reasons_added", text)
        self.assertNotIn("candidate_blockers_before_decision", text)
        self.assertNotIn("candidate_diagnostics_before_decision", text)

    def test_decision_content_quality_score_role_is_not_generic_score_role(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "evidence_summary.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn('"content_quality_score_role"', text)
        self.assertNotIn('"score_role": "quality_diagnostic_not_hard_gate"', text)

    def test_finalization_does_not_generate_decision_risk_evidence(self) -> None:
        banned = (
            "overlap_bleed_risk_detail",
            "lucky_pass_risk_score_detail",
            "from ..evidence.risk",
            "from ...detection.evidence.risk",
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
        self.assertIn("_low_confidence_context_reason_inputs", contract_text)

    def test_policy_assembly_does_not_use_reported_physical_risk_strings(self) -> None:
        banned = (
            "known_physical_risks",
            "_has_physical_risk",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "policies" / "assembly"
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
