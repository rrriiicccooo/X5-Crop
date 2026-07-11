from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import (
    PROJECT_ROOT,
    duplicate_dataclass_models,
    source_import_graph,
)


class LayerBoundariesOutputContractTest(unittest.TestCase):
    def test_runtime_reuse_does_not_deserialize_report_schema(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "analysis_reuse.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "DecisionGateAssessment(",
            "GateCheck(",
            "FinalDetection.restore(",
            "def _box_from_record",
            "def _geometry_from_record",
            "def _separator_observation_from_record",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn(
            "final_detection_from_record as _final_detection_from_record",
            source,
        )
        self.assertTrue(
            (PROJECT_ROOT / "x5crop" / "report" / "restoration.py").is_file()
        )

    def test_report_output_has_one_runtime_owner(self) -> None:
        owners = []
        for path in (PROJECT_ROOT / "x5crop" / "runtime").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "write_report_outputs_for_result" in source:
                owners.append(path.name)

        self.assertEqual(owners, ["app.py"])

    def test_debug_reads_one_canonical_gap_evidence_shape(self) -> None:
        debug_source = (PROJECT_ROOT / "x5crop" / "debug" / "gaps.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FinalDetection", debug_source)
        self.assertIn("detection.separator_observations", debug_source)
        self.assertNotIn(".detail", debug_source)
        self.assertFalse(
            (PROJECT_ROOT / "x5crop/detection/evidence/read_only.py").exists()
        )

    def test_every_debug_panel_is_reachable_from_active_policy(self) -> None:
        from x5crop.formats import FORMAT_CHOICES
        from x5crop.policies.registry import get_detection_policy

        active_panels = {
            panel_id
            for format_id in FORMAT_CHOICES
            for strip_mode in ("full", "partial")
            for panel_id in get_detection_policy(
                format_id,
                strip_mode,
            ).diagnostics.debug_panels
        }
        active_titles = {
            panel.panel_id
            for format_id in FORMAT_CHOICES
            for strip_mode in ("full", "partial")
            for panel in get_detection_policy(
                format_id,
                strip_mode,
            ).diagnostics.debug_panel_titles
        }
        source_path = PROJECT_ROOT / "x5crop" / "debug" / "panels.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        renderer_ids = {
            key.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "panel_builders"
                for target in node.targets
            )
            and isinstance(node.value, ast.Dict)
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }

        self.assertEqual(renderer_ids, active_panels)
        self.assertEqual(active_titles, active_panels)

    def test_runtime_resolves_each_format_mode_once(self) -> None:
        cli_source = (
            PROJECT_ROOT / "x5crop" / "entry" / "cli.py"
        ).read_text(encoding="utf-8")
        bootstrap_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "bootstrap.py"
        ).read_text(encoding="utf-8")
        app_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "app.py"
        ).read_text(encoding="utf-8")
        workflow_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "workflow.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("FORMATS", cli_source)
        self.assertEqual(bootstrap_source.count("DetectionPolicyBundle.for_format_mode"), 1)
        self.assertNotIn("DetectionPolicyBundle.for_format_mode", app_source)
        self.assertNotIn("DetectionPolicyBundle.for_format_mode", workflow_source)

        from inspect import signature
        from x5crop.runtime.app import process_parallel_files

        self.assertEqual(
            tuple(signature(process_parallel_files).parameters),
            ("invocation", "worker_config"),
        )

    def test_entry_only_parses_options_and_delegates_to_runtime(self) -> None:
        entry_root = PROJECT_ROOT / "x5crop" / "entry"
        entry_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(entry_root.glob("*.py"))
        )

        self.assertNotIn("first_tiff_shape", entry_source)
        self.assertNotIn("infer_layout", entry_source)
        self.assertNotIn("DetectionPolicyBundle", entry_source)
        self.assertNotIn("RunConfig(", entry_source)
        self.assertFalse((entry_root / "invocation.py").exists())

    def test_runtime_options_have_one_canonical_model(self) -> None:
        entry_options = PROJECT_ROOT / "x5crop" / "entry" / "options.py"
        runtime_options = PROJECT_ROOT / "x5crop" / "runtime" / "options.py"
        bootstrap = (
            PROJECT_ROOT / "x5crop" / "runtime" / "bootstrap.py"
        ).read_text(encoding="utf-8")

        self.assertFalse(entry_options.exists())
        self.assertTrue(runtime_options.is_file())
        runtime_source = runtime_options.read_text(encoding="utf-8")
        self.assertIn("class RuntimeOptions", runtime_source)
        self.assertNotIn("Protocol", bootstrap)
        self.assertNotIn("RuntimeOptionValues", bootstrap)

    def test_physical_spec_does_not_own_parameter_profile_identity(self) -> None:
        from x5crop.formats import FormatPhysicalSpec
        from x5crop.policies.parameters.registry import parameter_profile_for_spec

        self.assertFalse(hasattr(FormatPhysicalSpec, "frame_geometry_profile"))
        self.assertEqual(parameter_profile_for_spec.__module__, "x5crop.policies.parameters.registry")

    def test_report_policy_read_models_do_not_live_in_detection_detail(self) -> None:
        workflow = (
            PROJECT_ROOT / "x5crop" / "runtime" / "workflow.py"
        ).read_text(encoding="utf-8")
        self.assertFalse((PROJECT_ROOT / "x5crop/detection/detail.py").exists())

        for field_name in (
            "RUNTIME_POLICY_DETAIL",
            "DECISION_POLICY_DETAIL",
            "POLICY_ID",
        ):
            self.assertNotIn(field_name, workflow)

    def test_output_protection_consumes_the_canonical_parameter_type(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "output" / "protection.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("PolicyLike", source)
        self.assertIn("ExposureOverlapProtectionParameters", source)

    def test_output_protection_receives_base_bleed_explicitly(self) -> None:
        from inspect import signature

        from x5crop.runtime.output_protection import prepare_output_protection

        source = (
            PROJECT_ROOT / "x5crop/runtime/output_protection.py"
        ).read_text(encoding="utf-8")
        self.assertIn("base_bleed", signature(prepare_output_protection).parameters)
        self.assertNotIn("context.config", source)

    def test_debug_receives_only_the_subpolicies_it_uses(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop" / "debug").glob("*.py")
        )

        self.assertNotIn("DetectionPolicy", source)

    def test_output_geometry_does_not_depend_on_runtime_config(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "output" / "geometry_adjustment.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("RunConfig", source)
        self.assertIn("AxisBleedParameters", source)

    def test_finalization_receives_only_its_explicit_subpolicies(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "detection" / "final" / "finalize.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("DetectionPolicy", source)

    def test_policy_assembly_has_no_pass_through_preset_models(self) -> None:
        assembly = PROJECT_ROOT / "x5crop" / "policies" / "assembly"
        self.assertFalse((assembly / "presets.py").exists())
        self.assertFalse((assembly / "format_presets.py").exists())
        registry = (
            PROJECT_ROOT / "x5crop" / "policies" / "registry.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from .assembly.factory import build_detection_policy", registry)

    def test_runtime_policy_has_no_single_value_forwarding_models(self) -> None:
        runtime_root = PROJECT_ROOT / "x5crop" / "policies" / "runtime"
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(runtime_root.glob("*.py"))
        )

        for class_name in (
            "DetectorPolicy",
            "CountHypothesisPolicy",
            "FinalizationPolicy",
            "BaseOuterProposalPolicy",
        ):
            self.assertNotIn(f"class {class_name}", source)

    def test_candidate_runtime_does_not_write_unconsumed_detail(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (
                PROJECT_ROOT / "x5crop/detection/candidate",
                PROJECT_ROOT / "x5crop/detection/modes",
            )
            for path in sorted(root.rglob("*.py"))
        )
        self.assertNotIn(".detail", source)
        self.assertNotIn("detail=", source)

    def test_decision_evidence_policy_surface_is_removed(self) -> None:
        decision_parameters = (
            PROJECT_ROOT / "x5crop" / "policies" / "parameters" / "decision.py"
        )
        evidence_policy = (
            PROJECT_ROOT / "x5crop" / "policies" / "decision" / "evidence_policy.py"
        )

        self.assertFalse(decision_parameters.exists())
        self.assertFalse(evidence_policy.exists())

    def test_crop_decision_output_tuning_is_format_parameter_owned(self) -> None:
        geometry_parameters = (
            PROJECT_ROOT / "x5crop" / "geometry" / "detection_parameters.py"
        ).read_text(encoding="utf-8")
        candidate_parameters = (
            PROJECT_ROOT / "x5crop" / "policies" / "parameters" / "candidate.py"
        ).read_text(encoding="utf-8")
        runtime_separator = (
            PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "separator.py"
        ).read_text(encoding="utf-8")
        aggregate_parameters = (
            PROJECT_ROOT / "x5crop" / "policies" / "parameters" / "aggregate.py"
        ).read_text(encoding="utf-8")
        profile_presets = PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "profile_presets.py"

        self.assertNotIn("class FrameFitParameters", geometry_parameters)
        self.assertIn("PhysicalLength", geometry_parameters)
        self.assertIn("class CandidatePlanParameters", candidate_parameters)
        self.assertNotIn("sequence_score_weight", runtime_separator)
        self.assertIn("separator_width_profile_search", aggregate_parameters)
        self.assertIn("edge_bleed_protection", aggregate_parameters)
        self.assertFalse(profile_presets.exists())

    def test_separator_width_outer_budget_is_parameter_owned(self) -> None:
        from x5crop.policies.parameters.separator import SeparatorWidthProfileParameters
        from x5crop.policies.registry import get_detection_policy

        required = {
            "band_candidate_count",
            "sequence_candidate_count",
            "max_candidates",
        }
        self.assertTrue(required.issubset(SeparatorWidthProfileParameters.__dataclass_fields__))
        width_profile = get_detection_policy("135", "full").separator.width_profile
        self.assertEqual(set(width_profile.__dataclass_fields__), {"mode", "parameters"})

    def test_active_source_symbols_require_active_source_consumers(self) -> None:
        units_source = (PROJECT_ROOT / "x5crop" / "units.py").read_text(encoding="utf-8")
        gap_geometry_source = (
            PROJECT_ROOT / "x5crop" / "geometry" / "gap_geometry.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class PhysicalLength", units_source)
        self.assertIn("PhysicalLength", (
            PROJECT_ROOT / "x5crop/geometry/detection_parameters.py"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("def photo_width_cv_from_gap_edges", gap_geometry_source)

    def test_runtime_has_no_process_one_worker_forwarder(self) -> None:
        workflow_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "workflow.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("def process_one_worker", workflow_source)

    def test_active_source_import_graph_is_acyclic(self) -> None:
        graph = source_import_graph()
        remaining = {module: set(targets) for module, targets in graph.items()}
        while remaining:
            leaves = {
                module
                for module, targets in remaining.items()
                if not (targets & remaining.keys())
            }
            if not leaves:
                break
            remaining = {
                module: targets - leaves
                for module, targets in remaining.items()
                if module not in leaves
            }

        self.assertEqual(remaining, {})

    def test_policy_assembly_receives_one_resolved_physical_spec(self) -> None:
        policy_factory = (
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "factory.py"
        ).read_text(encoding="utf-8")
        parameter_registry = (
            PROJECT_ROOT / "x5crop" / "policies" / "parameters" / "registry.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("format_spec(", policy_factory)
        self.assertNotIn("format_spec(", parameter_registry)
        self.assertIn("def format_parameters(spec: FormatPhysicalSpec)", parameter_registry)

    def test_active_source_has_no_undecorated_forwarding_aliases(self) -> None:
        banned_functions = {
            "merge_outer_proposal_candidates",
            "candidate_signals",
            "propose_equal_model_gap",
        }
        offenders = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name in banned_functions
                ):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{node.name}")

        self.assertEqual(offenders, [])

    def test_geometry_and_detection_share_one_separator_band_collection(self) -> None:
        self.assertEqual(
            duplicate_dataclass_models("x5crop.geometry", "x5crop.detection"),
            [],
        )

    def test_tool_support_has_no_unreferenced_public_helpers(self) -> None:
        support_path = PROJECT_ROOT / "tools" / "tests" / "architecture_contracts.py"
        support_tree = ast.parse(support_path.read_text(encoding="utf-8"))
        public_functions = {
            node.name
            for node in support_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        }
        referenced: set[str] = set()
        for path in (PROJECT_ROOT / "tools").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    referenced.add(node.id)
                elif isinstance(node, ast.Attribute):
                    referenced.add(node.attr)
        unreferenced = sorted(public_functions - referenced)

        self.assertEqual(unreferenced, [])

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
            / "decision_gate.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("runtime.diagnostics", exposure_text)
        self.assertNotIn("output.protection", exposure_text)
        self.assertNotIn("decision", exposure_text)
        self.assertNotIn("x5crop.detection", output_plan_text)
        self.assertNotIn("policies.registry", output_plan_text)
        self.assertNotIn("output.protection", decision_text)

    def test_outer_alignment_evidence_does_not_own_correction_policy(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "evidence" / "outer_alignment.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn("OuterAlignmentEvidenceParameters", text)
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

    def test_output_helpers_do_not_write_unreachable_detail(self) -> None:
        output_root = PROJECT_ROOT / "x5crop" / "output"
        source = "\n".join(
            (output_root / name).read_text(encoding="utf-8")
            for name in ("geometry_adjustment.py", "bleed.py")
        )
        for key in (
            'detection.detail["approved_geometry_adjustment"]',
            'detection.detail["edge_bleed_protection"]',
            'detection.detail["output_bleed"]',
        ):
            self.assertNotIn(key, source)


if __name__ == "__main__":
    unittest.main()
