from __future__ import annotations

import ast
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from tools.tests.architecture_contracts import (
    RUNTIME_ROOTS,
    STANDALONE_ROOTS,
    STANDALONE_TOOL_ROOTS,
    forbidden_import_edges,
    functions_with_untyped_parameters,
    functions_with_unused_parameters,
    invalid_dataclass_default_factories,
    modules_with_export_lists,
    pass_through_classes,
    public_top_level_symbols,
    reachable_source_modules,
    source_modules,
    source_layer_memberships,
    standalone_tool_modules,
    unreferenced_top_level_symbols,
    unreferenced_methods,
    unreferenced_public_assignments,
    unreferenced_public_symbols,
    unreferenced_dataclass_fields,
    unused_imports,
)


class LayerBoundariesContractTest(unittest.TestCase):
    def test_active_source_has_no_unreferenced_public_assignments(self) -> None:
        self.assertEqual(unreferenced_public_assignments(), [])

    def test_every_active_module_has_one_source_layer(self) -> None:
        offenders = {
            module_name: source_layer_memberships(module_name)
            for module_name in source_modules()
            if len(source_layer_memberships(module_name)) != 1
        }
        self.assertEqual(offenders, {})

    def test_runtime_policy_default_factories_are_callable_without_hidden_inputs(self) -> None:
        self.assertEqual(
            invalid_dataclass_default_factories("x5crop.policies.runtime"),
            [],
        )

    def test_active_interfaces_have_explicit_parameter_types(self) -> None:
        self.assertEqual(functions_with_untyped_parameters(), [])

    def test_detection_does_not_disable_foundation_parameters_with_none(self) -> None:
        offenders: list[str] = []
        root = PROJECT_ROOT / "x5crop" / "detection"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if (
                        keyword.arg in {"geometry_parameters", "frame_fit", "parameters"}
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is None
                    ):
                        offenders.append(
                            f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:{keyword.arg}"
                        )

        self.assertEqual(offenders, [])

    def test_detection_and_debug_helpers_do_not_hide_optional_runtime_inputs(self) -> None:
        offenders: list[str] = []
        for root in (
            PROJECT_ROOT / "x5crop" / "detection",
            PROJECT_ROOT / "x5crop" / "debug",
        ):
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    positional = [*node.args.posonlyargs, *node.args.args]
                    positional_defaults = [
                        None,
                    ] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
                    defaults = {
                        argument.arg: default
                        for argument, default in zip(positional, positional_defaults)
                    }
                    defaults.update(
                        {
                            argument.arg: default
                            for argument, default in zip(
                                node.args.kwonlyargs,
                                node.args.kw_defaults,
                            )
                        }
                    )
                    for parameter in ("cache", "family_policy"):
                        default = defaults.get(parameter)
                        if isinstance(default, ast.Constant) and default.value is None:
                            offenders.append(
                                f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:{node.name}:{parameter}"
                            )

        self.assertEqual(offenders, [])

    def test_evidence_does_not_embed_application_identity(self) -> None:
        self.assertEqual(
            forbidden_import_edges(
                ("x5crop.detection.evidence",),
                ("x5crop.app_info",),
            ),
            [],
        )

    def test_output_consumes_final_domain_types_not_detection_detail_schema(self) -> None:
        self.assertEqual(
            forbidden_import_edges(("x5crop.output",), ("x5crop.detection",)),
            [],
        )

    def test_runtime_does_not_depend_on_entry_models(self) -> None:
        self.assertEqual(
            forbidden_import_edges(("x5crop.runtime",), ("x5crop.entry",)),
            [],
        )

    def test_policy_models_do_not_own_report_serialization(self) -> None:
        from x5crop.policies.decision.contract import DetectionDecisionContract
        from x5crop.policies.runtime.policy import DetectionPolicy

        self.assertNotIn("report_detail", DetectionPolicy.__dict__)
        self.assertNotIn("report_detail", DetectionDecisionContract.__dict__)

        pipeline_source = (
            PROJECT_ROOT / "x5crop" / "detection" / "pipeline.py"
        ).read_text(encoding="utf-8")
        decision_source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "contract_applier.py"
        ).read_text(encoding="utf-8")
        workflow_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "workflow.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("runtime_policy_detail", pipeline_source)
        self.assertNotIn("decision_policy_detail", decision_source)
        self.assertIn("detection_policy_report_detail", workflow_source)
        self.assertIn("decision_contract_report_detail", workflow_source)

    def test_deskew_quality_uses_explicit_parameters_without_numeric_fallbacks(self) -> None:
        from x5crop.image.deskew_parameters import DeskewParameters

        self.assertIn("quality_inlier_weight", DeskewParameters.__dataclass_fields__)
        path = PROJECT_ROOT / "x5crop" / "image" / "deskew.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(functions["fit_line"].args.defaults, [])
        self.assertEqual(functions["fit_line"].args.kw_defaults, [None, None, None])
        self.assertEqual(
            [argument.arg for argument in functions["deskew_quality"].args.args],
            ["detail", "deskew"],
        )
        deskew_quality_source = ast.get_source_segment(
            source,
            functions["deskew_quality"],
        )
        self.assertNotIn('get("median_residual", 10.0)', deskew_quality_source)

    def test_detection_pipeline_requires_runtime_owned_analysis_cache(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "pipeline.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        choose_detection = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "choose_detection"
        )
        self.assertEqual(choose_detection.args.defaults, [])
        self.assertNotIn("make_analysis_cache", source)

    def test_every_active_module_is_reachable_from_a_registered_root(self) -> None:
        modules = set(source_modules())
        reached = set(reachable_source_modules(RUNTIME_ROOTS | STANDALONE_ROOTS))

        self.assertEqual(sorted(modules - reached), [])

    def test_every_standalone_tool_is_registered_once(self) -> None:
        self.assertEqual(standalone_tool_modules(), STANDALONE_TOOL_ROOTS)

    def test_candidate_sublayers_follow_the_lifecycle_direction(self) -> None:
        contracts = (
            (
                ("x5crop.detection.candidate.plan",),
                (
                    "x5crop.detection.candidate.build",
                    "x5crop.detection.candidate.assessment",
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.candidate.extension",
                    "x5crop.detection.decision",
                ),
            ),
            (
                ("x5crop.detection.candidate.proposal",),
                (
                    "x5crop.detection.candidate.build",
                    "x5crop.detection.candidate.assessment",
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.candidate.extension",
                    "x5crop.detection.decision",
                ),
            ),
            (
                ("x5crop.detection.candidate.build",),
                (
                    "x5crop.detection.candidate.assessment",
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.candidate.extension",
                    "x5crop.detection.decision",
                ),
            ),
            (
                ("x5crop.detection.candidate.assessment",),
                (
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.candidate.extension",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
            (
                ("x5crop.detection.candidate.selection",),
                (
                    "x5crop.detection.candidate.extension",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
        )
        offenders = [
            edge
            for sources, targets in contracts
            for edge in forbidden_import_edges(sources, targets)
        ]
        self.assertEqual(offenders, [])

    def test_detection_evidence_guidance_and_decision_do_not_import_later_stages(self) -> None:
        contracts = (
            (
                ("x5crop.detection.evidence",),
                (
                    "x5crop.detection.candidate",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
            (
                ("x5crop.detection.guidance",),
                (
                    "x5crop.detection.candidate.assessment",
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
            (
                ("x5crop.detection.decision",),
                (
                    "x5crop.detection.physical",
                    "x5crop.detection.guidance",
                    "x5crop.detection.candidate.build",
                    "x5crop.detection.candidate.proposal",
                    "x5crop.detection.candidate.selection",
                    "x5crop.detection.final",
                ),
            ),
        )
        offenders = [
            edge
            for sources, targets in contracts
            for edge in forbidden_import_edges(sources, targets)
        ]
        self.assertEqual(offenders, [])

    def test_finalization_only_reads_finalized_evidence(self) -> None:
        edges = forbidden_import_edges(
            ("x5crop.detection.final",),
            (
                "x5crop.detection.candidate",
                "x5crop.detection.physical",
                "x5crop.detection.guidance",
                "x5crop.detection.evidence",
                "x5crop.detection.decision",
            ),
        )
        self.assertEqual(
            edges,
            [("x5crop.detection.final.finalize", "x5crop.detection.evidence.read_only")],
        )

    def test_report_and_debug_do_not_import_detection_computation_layers(self) -> None:
        self.assertEqual(
            forbidden_import_edges(
                ("x5crop.report", "x5crop.debug"),
                (
                    "x5crop.detection.candidate",
                    "x5crop.detection.physical",
                    "x5crop.detection.guidance",
                    "x5crop.detection.evidence",
                    "x5crop.detection.decision",
                    "x5crop.detection.final",
                ),
            ),
            [],
        )

    def test_policy_registry_is_resolved_only_at_policy_runtime_boundaries(self) -> None:
        callers: set[str] = set()
        for module in source_modules().values():
            tree = ast.parse(module.path.read_text(encoding="utf-8"))
            if any(
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id == "get_detection_policy"
                for node in ast.walk(tree)
            ):
                callers.add(module.name)
        self.assertEqual(
            callers,
            {
                "x5crop.policies.consistency",
                "x5crop.policies.runtime.bundle",
            },
        )

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

    def test_active_source_has_no_unreferenced_public_symbols(self) -> None:
        self.assertEqual(unreferenced_public_symbols(), [])

    def test_active_source_has_no_unreferenced_top_level_helpers(self) -> None:
        self.assertEqual(unreferenced_top_level_symbols(), [])

    def test_active_source_has_no_unreferenced_methods(self) -> None:
        self.assertEqual(unreferenced_methods(), [])

    def test_internal_modules_do_not_publish_unused_export_lists(self) -> None:
        self.assertEqual(modules_with_export_lists(), [])

    def test_active_interfaces_do_not_accept_unused_parameters(self) -> None:
        self.assertEqual(functions_with_unused_parameters(), [])

    def test_runtime_dataclass_fields_have_real_consumers(self) -> None:
        self.assertEqual(unreferenced_dataclass_fields(), [])

    def test_active_source_has_no_unused_imports(self) -> None:
        self.assertEqual(unused_imports(), [])

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
        self.assertTrue(hasattr(final, "FinalizationPolicy"))

    def test_output_policy_is_owned_by_runtime_output_module(self) -> None:
        from x5crop.policies.runtime.output import (
            EdgeBleedProtectionPolicy,
            OutputPolicy,
        )

        self.assertIn("edge_bleed_protection", OutputPolicy.__dataclass_fields__)
        self.assertIn("guard_ratio", EdgeBleedProtectionPolicy.__dataclass_fields__)

    def test_universal_capabilities_do_not_have_constant_policy_switches(self) -> None:
        from x5crop.policies.parameters.separator import (
            LeadingGridFailureParameters,
            SeparatorSupportParameters,
            SeparatorWidthProfileParameters,
        )
        from x5crop.policies.parameters.outer import (
            EdgeAnchoredContentPositionParameters,
            FloatingContentPositionParameters,
            FullWidthSeparatorOuterParameters,
        )
        from x5crop.geometry.detection_parameters import NearbySeparatorRefinementParameters
        from x5crop.image.gray import BaseGrayParameters
        from x5crop.policies.runtime.candidate import (
            CandidateExecutionBudgetPolicy,
            CandidatePlanPolicy,
            ContentGuidedSeparatorCandidatePolicy,
            EvidenceIndependencePolicy,
            SeparatorFullWidthCompetitionPolicy,
        )
        from x5crop.policies.runtime.base import FrameFitPolicy
        from x5crop.policies.decision.contract import DecisionPolicy
        from x5crop.policies.runtime.content import ContentPolicy
        from x5crop.policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
        from x5crop.policies.parameters.decision import DecisionReviewParameters
        from x5crop.policies.runtime.final import FinalizationPolicy
        from x5crop.policies.runtime.outer import (
            BaseOuterProposalPolicy,
            LongAxisGeometryCorrectionPolicy,
            PartialPlacementGeometryPolicy,
            OuterCorrectionFamilyPolicy,
            ShortAxisGeometryCorrectionPolicy,
        )
        from x5crop.policies.runtime.output import EdgeBleedProtectionPolicy, OutputPolicy
        from x5crop.policies.runtime.separator import (
            SeparatorGeometrySupportModePolicy,
            SeparatorModelGapProposalPolicy,
            SeparatorPolicy,
            SeparatorRefinementFamilyPolicy,
            SeparatorWidthProfilePolicy,
        )

        switches = {
            FinalizationPolicy: "apply_approved_geometry_adjustment",
            OutputPolicy: "apply_output_bleed",
            RuntimeDiagnosticsPolicy: "attach_read_only_when_requested",
            ContentPolicy: "validates_candidates",
            EdgeBleedProtectionPolicy: "enabled",
            BaseOuterProposalPolicy: "enabled",
            EdgeAnchoredContentPositionParameters: "enabled",
            FloatingContentPositionParameters: "enabled",
            LongAxisGeometryCorrectionPolicy: "enabled",
            ShortAxisGeometryCorrectionPolicy: "enabled",
            LeadingGridFailureParameters: "enabled",
            SeparatorWidthProfileParameters: "full_enabled",
            SeparatorFullWidthCompetitionPolicy: "enabled",
            EvidenceIndependencePolicy: "enabled",
            DecisionReviewParameters: "align_outer_to_content",
            DecisionPolicy: "align_outer_to_content",
            ContentGuidedSeparatorCandidatePolicy: "requires_exact_content_runs",
            SeparatorSupportParameters: "allow_geometry_support",
            SeparatorGeometrySupportModePolicy: "allow_grid",
            SeparatorGeometrySupportModePolicy: "enabled",
            SeparatorModelGapProposalPolicy: "geometry_equal_model_enabled",
            NearbySeparatorRefinementParameters: "enabled",
            FrameFitPolicy: "geometry_fallback",
            BaseGrayParameters: "miniswhite_inverts",
            PartialPlacementGeometryPolicy: "skip_floating_when_edge_trusted",
        }
        for policy_type, field_name in switches.items():
            self.assertNotIn(field_name, policy_type.__dataclass_fields__)
        self.assertNotIn("partial_enabled", SeparatorWidthProfileParameters.__dataclass_fields__)
        for field_name in (
            "stop_after_reliable_primary",
            "skip_outer_correction_after_reliable_selection",
            "requires_separator_source",
            "requires_candidate_gate",
            "requires_hard_separator_ok",
            "requires_no_candidate_signals",
        ):
            self.assertNotIn(
                field_name,
                CandidateExecutionBudgetPolicy.__dataclass_fields__,
            )
        self.assertNotIn(
            "outer_correction_extension",
            CandidatePlanPolicy.__dataclass_fields__,
        )
        self.assertNotIn("hard_required_all_gaps", SeparatorPolicy.__dataclass_fields__)
        self.assertNotIn("geometry_support_modes", SeparatorPolicy.__dataclass_fields__)
        self.assertNotIn("detection_long_axis_bleed", OutputPolicy.__dataclass_fields__)
        self.assertNotIn("detection_short_axis_bleed", OutputPolicy.__dataclass_fields__)
        for field_name in (
            "requires_explicit_count_for_partial",
            "requires_separator_assessment",
            "strip_modes",
        ):
            self.assertNotIn(field_name, OuterCorrectionFamilyPolicy.__dataclass_fields__)
        self.assertNotIn(
            "requires_explicit_count_for_partial",
            SeparatorRefinementFamilyPolicy.__dataclass_fields__,
        )
        self.assertNotIn("required_count", SeparatorWidthProfilePolicy.__dataclass_fields__)
        self.assertNotIn("required_count", FullWidthSeparatorOuterParameters.__dataclass_fields__)
        for policy_type, field_names in (
            (ContentGuidedSeparatorCandidatePolicy, ("enabled",)),
            (SeparatorSupportParameters, ("allow_full_detected_geometry",)),
            (SeparatorGeometrySupportModePolicy, ("allow_grid",)),
        ):
            for field_name in field_names:
                self.assertNotIn(field_name, policy_type.__dataclass_fields__)
        for field_name in (
            "requires_default_count",
            "requires_standard_width_search",
            "requires_incomplete_hard_gaps",
        ):
            self.assertNotIn(
                field_name,
                SeparatorModelGapProposalPolicy.__dataclass_fields__,
            )

    def test_finalization_assembly_does_not_own_diagnostics_policy(self) -> None:
        from x5crop.policies.assembly import finalization

        self.assertFalse(hasattr(finalization, "diagnostics_policy"))
        self.assertTrue(callable(finalization.finalization_policy))

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
            self.assertFalse(hasattr(diagnostics, name))

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

        self.assertNotIn("format_id == FormatId.F135_DUAL.value", text)
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

if __name__ == "__main__":
    unittest.main()
