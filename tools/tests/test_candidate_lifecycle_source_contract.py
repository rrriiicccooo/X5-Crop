from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


class CandidateLifecycleSourceContractTest(unittest.TestCase):
    def test_only_candidate_selection_writes_candidate_competition(self) -> None:
        offenders: list[str] = []
        detection_root = PROJECT_ROOT / "x5crop" / "detection"
        for path in detection_root.rglob("*.py"):
            if "candidate/selection" in path.as_posix():
                continue
            source = path.read_text(encoding="utf-8")
            if (
                '"candidate_competition":' in source
                or 'detail["candidate_competition"] =' in source
            ):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_mode_candidates_delegate_candidate_gate_assessment(self) -> None:
        for name in ("review_only.py", "dual_lane_merge.py"):
            source = (
                PROJECT_ROOT / "x5crop" / "detection" / "modes" / name
            ).read_text(encoding="utf-8")
            self.assertIn("apply_mode_candidate_assessment", source)

    def test_candidate_plan_never_reads_or_mutates_detection_candidates(self) -> None:
        banned = ("DetectionCandidate", ".detail", ".confidence", ".frames")
        offenders: list[str] = []
        root = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "plan"
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT)}:{term}"
                for term in banned
                if term in source
            )

        self.assertEqual(offenders, [])

    def test_outer_proposal_has_no_single_call_full_width_wrapper(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "proposal" / "outer.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("def separator_full_width_outer_proposal_candidates", source)

    def test_candidate_signal_mutation_has_one_canonical_helper(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "signals.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("def add_candidate_signal(", source)

    def test_outer_candidate_strategy_has_one_typed_source(self) -> None:
        execution_source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "source_candidates.py"
        ).read_text(encoding="utf-8")

        strategy_reducer_offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
            if "outer_candidate_strategy(" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(strategy_reducer_offenders, [])
        self.assertNotIn('detail.get("family")', execution_source)

    def test_pending_separator_refinement_is_explicitly_policy_free(self) -> None:
        from x5crop.detection.candidate.build.separator_refinements import (
            NEARBY_SEPARATOR_REFINEMENT_FAMILY,
            pending_gap_refinement_detail,
        )

        detail = pending_gap_refinement_detail(NEARBY_SEPARATOR_REFINEMENT_FAMILY)

        self.assertEqual(detail["family"], NEARBY_SEPARATOR_REFINEMENT_FAMILY)
        self.assertFalse(detail["eligible"])

    def test_separator_source_execution_respects_keyword_only_runtime_inputs(self) -> None:
        source_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "count_hypothesis.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        explicit_runtime_inputs = {
            "separator_primary_outer_plan": {"cache", "policy"},
            "separator_extension_outer_plan": {
                "cache",
                "policy",
                "primary_outer_candidates",
            },
            "content_guided_separator_candidate_from_seed": {
                "cache",
                "policy",
                "seed_result",
            },
            "content_candidate_proposal_for_count": {"cache", "content_policy"},
        }
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in explicit_runtime_inputs
        ]

        self.assertGreaterEqual(len(calls), len(explicit_runtime_inputs))
        for call in calls:
            keyword_names = {keyword.arg for keyword in call.keywords}
            self.assertLessEqual(len(call.args), 6)
            self.assertTrue(
                explicit_runtime_inputs[call.func.id].issubset(keyword_names)
            )

    def test_separator_primary_and_extension_have_distinct_execution_entries(self) -> None:
        source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "source_candidates.py"
        ).read_text(encoding="utf-8")
        count_execution = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "count_hypothesis.py"
        ).read_text(encoding="utf-8")

        self.assertIn("def separator_primary_outer_plan", source)
        self.assertIn("def separator_extension_outer_plan", source)
        self.assertIn("def build_separator_candidate_for_outer", source)
        self.assertNotIn("def separator_source_candidates_for_count", source)
        self.assertNotIn("include_extension_outer", source)
        self.assertNotIn("detections:", source)
        self.assertEqual(count_execution.count("separator_primary_outer_plan("), 1)
        self.assertEqual(count_execution.count("separator_extension_outer_plan("), 1)

    def test_content_guided_extension_requires_a_precomputed_seed(self) -> None:
        budget = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "budget.py"
        ).read_text(encoding="utf-8")
        sources = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "source_candidates.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn('families.append("content_guided_separator")', budget)
        self.assertIn("def content_guided_separator_candidate_from_seed", sources)
        function_source = sources.split(
            "def content_guided_separator_candidate_from_seed", 1
        )[1]
        self.assertNotIn("content_guided_separator_seed_for_count(", function_source)

    def test_separator_refinement_detail_reads_only_current_family_policy_fields(self) -> None:
        source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "build"
            / "separator_refinements.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "family_policy.requires_explicit_count_for_partial",
            source,
        )
        self.assertNotIn("nearby_refinement.enabled", source)

    def test_content_candidate_policy_does_not_use_final_review_only_terms(self) -> None:
        offenders: list[str] = []
        banned = (
            "review_only",
            '"review_only"',
            '"assessment_required"',
        )
        for path in (
            PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "content.py",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance" / "content_model.py",
        ):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_guidance_proposes_content_without_building_detection_candidates(self) -> None:
        guidance = (
            PROJECT_ROOT / "x5crop" / "detection" / "guidance" / "content_model.py"
        ).read_text(encoding="utf-8")
        candidate_builder = (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "build" / "content.py"
        )

        self.assertNotIn("DetectionCandidate", guidance)
        self.assertNotIn("RunConfig", guidance)
        self.assertTrue(candidate_builder.is_file())

    def test_content_candidate_assessment_uses_diagnostic_naming(self) -> None:
        banned = (
            "content_candidate_confidence_and_reasons",
            "proposal_reasons",
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

    def test_separator_search_has_no_single_value_profile_selector(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "detection" / "gap_profiles.py").exists()
        )
        banned = ("gap_search_profile", "WIDTH_AWARE_GAP_PROFILE")
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection"
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
        for root in (PROJECT_ROOT / "x5crop",):
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
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "factory.py",
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

if __name__ == "__main__":
    unittest.main()
