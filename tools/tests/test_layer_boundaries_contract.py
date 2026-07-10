from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from tools.tests.architecture_contracts import (
    RUNTIME_ROOTS,
    STANDALONE_ROOTS,
    forbidden_import_edges,
    pass_through_classes,
    public_top_level_symbols,
    reachable_source_modules,
    source_modules,
)


class LayerBoundariesContractTest(unittest.TestCase):
    def test_every_active_module_is_reachable_from_a_registered_root(self) -> None:
        modules = set(source_modules())
        reached = set(reachable_source_modules(RUNTIME_ROOTS | STANDALONE_ROOTS))

        self.assertEqual(sorted(modules - reached), [])

    def test_lower_layers_do_not_import_runtime_orchestration(self) -> None:
        lower_layers = (
            "x5crop.detection",
            "x5crop.output",
            "x5crop.export",
            "x5crop.report",
            "x5crop.debug",
        )
        self.assertEqual(
            forbidden_import_edges(lower_layers, ("x5crop.runtime",)),
            [],
        )

    def test_foundation_does_not_import_higher_layers(self) -> None:
        foundation = (
            "x5crop.geometry",
            "x5crop.image",
            "x5crop.io",
            "x5crop.cache",
            "x5crop.units",
        )
        higher_layers = (
            "x5crop.runtime",
            "x5crop.policies",
            "x5crop.detection",
            "x5crop.output",
            "x5crop.export",
            "x5crop.report",
            "x5crop.debug",
        )
        self.assertEqual(forbidden_import_edges(foundation, higher_layers), [])

    def test_public_types_have_one_canonical_owner(self) -> None:
        import ast

        duplicates = {
            name: owners
            for name, owners in public_top_level_symbols(ast.ClassDef).items()
            if len(owners) > 1
        }
        self.assertEqual(duplicates, {})

    def test_public_helpers_have_one_canonical_owner(self) -> None:
        import ast

        duplicates = {
            name: owners
            for name, owners in public_top_level_symbols(ast.FunctionDef).items()
            if len(owners) > 1 and name != "main"
        }
        self.assertEqual(duplicates, {})

    def test_empty_subclass_aliases_do_not_exist(self) -> None:
        self.assertEqual(pass_through_classes(), [])

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

    def test_exposure_overlap_policy_is_not_owned_by_diagnostics_modules(self) -> None:
        from x5crop.policies.assembly import diagnostics
        from x5crop.policies.runtime import diagnostics as runtime_diagnostics

        banned = (
            "ExposureOverlapEvidencePolicy",
            "exposure_overlap_evidence",
        )
        for name in banned:
            self.assertFalse(hasattr(runtime_diagnostics, name))
            self.assertNotIn(name, tuple(diagnostics.__all__))

    def test_exposure_overlap_evidence_does_not_use_diagnostic_ownership_name(self) -> None:
        offenders: list[str] = []
        banned = ("diagnostic_" + "overlap", "Diagnostic" + "Overlap")
        for root in (PROJECT_ROOT / "x5crop",):
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if any(term in text for term in banned):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

    def test_format_physical_count_does_not_branch_on_format_id(self) -> None:
        text = (PROJECT_ROOT / "x5crop" / "formats" / "__init__.py").read_text(encoding="utf-8")

        self.assertNotIn("format_id == FormatId.DUAL_LANE.value", text)
        self.assertIn('physical_layout == "dual_lane"', text)

    def test_decision_evidence_policy_receives_physical_spec(self) -> None:
        text = (
            PROJECT_ROOT / "x5crop" / "policies" / "decision" / "evidence_policy.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("format_spec(", text)
        self.assertIn("spec: FormatPhysicalSpec", text)

    def test_format_preset_helpers_use_spec_and_traits_not_format_id(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "format_presets.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        private_helper_arguments: dict[str, list[str]] = {}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_"):
                private_helper_arguments[node.name] = [arg.arg for arg in node.args.args]

        offenders = {
            name: args
            for name, args in private_helper_arguments.items()
            if "format_id" in args
        }
        self.assertEqual(offenders, {})

    def test_decision_contract_does_not_own_output_or_diagnostics_policy(self) -> None:
        from x5crop.policies.decision.contract import DetectionDecisionContract

        banned = {
            "output",
            "diagnostics",
        }

        self.assertTrue(banned.isdisjoint(DetectionDecisionContract.__dataclass_fields__))

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

    def test_read_only_diagnostics_use_effects_detail(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "evidence" / "read_only.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn('"effects"', text)
        self.assertIn('"output": False', text)
        self.assertIn('"confidence": False', text)
        self.assertIn('"decision": False', text)
        self.assertIn("exposure_overlap_counts", text)
        self.assertNotIn("changes_output", text)
        self.assertNotIn("changes_confidence", text)
        self.assertNotIn("changes_final_decision", text)

    def test_decision_package_marker_does_not_reexport_runtime_helpers(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "decision" / "__init__.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        import_from_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]

        self.assertEqual(import_from_nodes, [])

    def test_finalization_does_not_generate_exposure_overlap_evidence(self) -> None:
        banned = (
            "exposure_overlap_evidence_detail",
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

    def test_exposure_evidence_output_plan_and_decision_keep_one_way_dependencies(self) -> None:
        exposure_text = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "evidence"
            / "exposure_overlap.py"
        ).read_text(encoding="utf-8")
        output_plan_text = (
            PROJECT_ROOT / "x5crop" / "output" / "protection.py"
        ).read_text(encoding="utf-8")
        decision_text = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "final_decision.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("runtime.diagnostics", exposure_text)
        self.assertNotIn("output.protection", exposure_text)
        self.assertNotIn("decision", exposure_text)
        self.assertNotIn("x5crop.detection", output_plan_text)
        self.assertNotIn("policies.registry", output_plan_text)
        self.assertNotIn("evidence.exposure_overlap", decision_text)
        self.assertNotIn("output.protection", decision_text)

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

        self.assertTrue((PROJECT_ROOT / "x5crop" / "output" / "bleed.py").is_file())



if __name__ == "__main__":
    unittest.main()
