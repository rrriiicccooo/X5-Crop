from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from x5crop.constants import FINAL_REVIEW_REASONS


class CurrentSchemaNamingContractTest(unittest.TestCase):
    def test_test_fixtures_use_only_current_decision_schema(self) -> None:
        invalid_reason_entries: list[str] = []
        removed_schema_entries: list[str] = []
        for path in (PROJECT_ROOT / "tools" / "tests").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                            continue
                        if key.value == "confidence_caps":
                            removed_schema_entries.append(
                                f"{path.relative_to(PROJECT_ROOT)}:{key.lineno}:confidence_caps"
                            )
                        if key.value != "final_review_reasons" or not isinstance(
                            value, (ast.List, ast.Tuple)
                        ):
                            continue
                        for item in value.elts:
                            if (
                                isinstance(item, ast.Constant)
                                and isinstance(item.value, str)
                                and item.value not in FINAL_REVIEW_REASONS
                            ):
                                invalid_reason_entries.append(
                                    f"{path.relative_to(PROJECT_ROOT)}:{item.lineno}:{item.value}"
                                )
                if isinstance(node, ast.Call):
                    for keyword in node.keywords:
                        if keyword.arg == "confidence_threshold":
                            removed_schema_entries.append(
                                f"{path.relative_to(PROJECT_ROOT)}:{keyword.value.lineno}:confidence_threshold"
                            )
        self.assertEqual(invalid_reason_entries, [])
        self.assertEqual(removed_schema_entries, [])

    def test_contract_tests_do_not_keep_inactive_source_exemptions(self) -> None:
        source = (
            PROJECT_ROOT / "tools" / "tests" / "test_architecture_ownership_contract.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("allowed_numeric_owners", source)

    def test_candidate_lifecycle_uses_current_model_names(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (
                PROJECT_ROOT / "x5crop" / "detection",
                PROJECT_ROOT / "x5crop" / "policies" / "parameters",
            )
            for path in root.rglob("*.py")
        )

        for old_name in (
            "fallback_count",
            "grid_fallback_cap",
            "content_grid_fallback",
            "geometry_fallback",
        ):
            self.assertNotIn(old_name, source)

    def test_contract_modules_use_owned_domains_not_residual_buckets(self) -> None:
        tests_root = PROJECT_ROOT / "tools" / "tests"

        self.assertFalse((tests_root / "test_architecture_residual_contract.py").exists())
        self.assertTrue((tests_root / "test_architecture_ownership_contract.py").is_file())

    def test_gap_taxonomy_has_one_hard_evidence_identity(self) -> None:
        from x5crop.constants import HARD_GAP_METHODS, MODEL_GAP_METHODS

        source = (PROJECT_ROOT / "x5crop" / "gap_methods.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("DIRECT_HARD_GAP_METHODS", source)
        self.assertNotIn("is_direct_hard_gap_method", source)
        self.assertIsInstance(HARD_GAP_METHODS, frozenset)
        self.assertIsInstance(MODEL_GAP_METHODS, frozenset)

    def test_separator_measurement_has_one_physical_identity(self) -> None:
        from x5crop.domain import MeasurementProvenance, SeparatorBandObservation

        self.assertEqual(
            tuple(SeparatorBandObservation.__dataclass_fields__),
            (
                "index",
                "center",
                "score",
                "method",
                "provenance",
                "start",
                "end",
                "lane_box",
                "continuity",
                "tonal_evidence",
            ),
        )
        self.assertTrue(SeparatorBandObservation.__dataclass_params__.frozen)
        self.assertEqual(
            tuple(MeasurementProvenance.__dataclass_fields__),
            ("root_measurement", "source", "dependencies", "boundary_anchors"),
        )
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
        )
        self.assertNotIn("class Gap:", source)

    def test_content_is_guidance_not_a_candidate_source(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
        )

        self.assertNotIn("CANDIDATE_SOURCE_CONTENT", source)
        self.assertFalse(
            (
                PROJECT_ROOT
                / "x5crop/detection/candidate/build/content.py"
            ).exists()
        )

    def test_contract_tests_reference_only_current_paths(self) -> None:
        contract_source = (
            PROJECT_ROOT / "tools" / "tests" / "test_architecture_ownership_contract.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn('"policies" / "formats"', contract_source)
        self.assertIn('/ "factory.py"', contract_source)

    def test_architecture_uses_current_decision_ownership_names(self) -> None:
        architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

        self.assertNotIn("contract applier", architecture.lower())
        self.assertNotIn("reuse compatible analysis", architecture.lower())
        self.assertNotIn("legacy processresult", architecture.lower())
        self.assertNotIn("physical lengths resolve", architecture.lower())
        self.assertNotIn("物理长度优先", architecture)
        self.assertNotIn("policy context", architecture.lower())

        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertNotIn("`PhysicalLength`", changelog)

        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b\d+\s+tests\b", agents, re.IGNORECASE))

    def test_architecture_describes_parameter_profile_ownership_not_removed_format_field(self) -> None:
        architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertNotIn("frame_geometry_profile", architecture)
        self.assertIn("parameter profile", architecture.lower())
        self.assertNotIn("`frame_geometry_profile` 由 physical", changelog)
        self.assertNotIn("`frame_geometry_profile` is derived", changelog)

    def test_user_facing_strip_mode_uses_holder_occupancy_not_strip_completeness(self) -> None:
        cli = (PROJECT_ROOT / "x5crop" / "entry" / "cli.py").read_text(encoding="utf-8")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        quick_start = (PROJECT_ROOT / "快速启动_Quick_Start.md").read_text(encoding="utf-8")

        self.assertNotIn("partial/head mode", cli)
        self.assertIn("holder", cli)
        self.assertNotIn("Use `partial mode = no` for complete strips.", readme)
        self.assertNotIn("完整片条：按 Return，保持 `no`。", quick_start)
        self.assertNotIn("Complete strip: press Return and keep `no`.", quick_start)

    def test_active_source_has_no_property_or_constant_aliases(self) -> None:
        format_source = (
            PROJECT_ROOT / "x5crop" / "formats" / "__init__.py"
        ).read_text(encoding="utf-8")
        safety_path = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "safety.py"
        )

        self.assertNotIn("def frame_aspect", format_source)
        self.assertFalse(safety_path.exists())

    def test_regression_compare_rejects_non_current_schema_rows(self) -> None:
        from tools.regression.compare import compare_report_rows

        invalid = {"source": "input.tif"}
        with self.assertRaises(ValueError):
            compare_report_rows([invalid], [invalid])

    def test_parameter_registry_receives_resolved_physical_spec(self) -> None:
        from inspect import signature

        from x5crop.policies.parameters.registry import format_parameters

        self.assertEqual(list(signature(format_parameters).parameters), ["spec"])

    def test_current_documents_use_current_owners_and_tool_contracts(self) -> None:
        banned_by_document = {
            "ARCHITECTURE.md": (
                "`x5crop.runtime.config`",
                "`runtime.config`",
                "`PixelKernel`",
                "runtime profiling / timing read model",
                "runtime profile names",
                "report sections",
                "JSONL / CSV / sections",
                "raw-gap frame construction",
                "原始 gaps 构造 frame",
            ),
            "CHANGELOG.md": (
                "`runtime.config`",
                "`PixelKernel`",
                "`--fail-on-diff`",
                "runtime profile names",
                "raw-gap frame construction",
            ),
            "AGENTS.md": ("broad separator width / separator-derived outer",),
        }
        offenders: list[str] = []
        for document, banned in banned_by_document.items():
            text = (PROJECT_ROOT / document).read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{document}: {term}")
        self.assertEqual(offenders, [])

    def test_current_documents_have_no_adjacent_duplicate_lines(self) -> None:
        offenders: list[str] = []
        for document in ("README.md", "ARCHITECTURE.md", "CHANGELOG.md", "AGENTS.md"):
            lines = (PROJECT_ROOT / document).read_text(encoding="utf-8").splitlines()
            for line_number, (before, after) in enumerate(zip(lines, lines[1:]), start=1):
                if before.strip() and before == after:
                    offenders.append(f"{document}:{line_number}:{before}")
        self.assertEqual(offenders, [])

    def test_format_identity_has_one_canonical_name(self) -> None:
        from x5crop.detection.geometry import CandidateGeometry
        from x5crop.domain import ProcessResult
        from x5crop.runtime.options import RuntimeOptions
        from x5crop.formats import FormatPhysicalSpec
        from x5crop.policies.runtime.policy import DetectionPolicy
        from x5crop.run_config import RunConfig

        for contract in (CandidateGeometry, RuntimeOptions, RunConfig):
            self.assertIn("format_id", contract.__dataclass_fields__)
        self.assertEqual(set(ProcessResult.__dataclass_fields__), {"record"})
        self.assertNotIn("name", FormatPhysicalSpec.__dataclass_fields__)
        self.assertIn("physical_spec", DetectionPolicy.__dataclass_fields__)
        self.assertNotIn("format", DetectionPolicy.__dataclass_fields__)

        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in ("film_format", "format_name"):
                if term in text:
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT)}: {term}"
                    )
        self.assertEqual(offenders, [])

    def test_format_identity_uses_plain_canonical_strings(self) -> None:
        import x5crop.formats as formats

        self.assertFalse(hasattr(formats, "FormatId"))
        for format_id, spec in formats.FORMATS.items():
            self.assertIsInstance(spec.format_id, str)
            self.assertEqual(spec.format_id, format_id)
            self.assertTrue(
                spec.lane_format_id is None or isinstance(spec.lane_format_id, str)
            )

        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in (".format_id.value", ".lane_format_id.value", "FormatId."):
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")
        self.assertEqual(offenders, [])

    def test_format_physical_specs_are_not_read_through_name_aliases(self) -> None:
        identifiers = {
            "fmt",
            "spec",
            "format_spec",
            "physical_spec",
            "initial_format",
            "lane_format_spec",
        }
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr == "name"
                    and isinstance(node.value, ast.Name)
                    and node.value.id in identifiers
                ):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_separator_width_candidate_capability_is_not_a_format_trait(self) -> None:
        from x5crop.formats import FORMATS
        from x5crop.policies.registry import get_detection_policy

        for spec in FORMATS.values():
            if spec.physical_layout != "single_strip":
                continue
            for strip_mode in ("full", "partial"):
                self.assertEqual(
                    get_detection_policy(spec.format_id, strip_mode)
                    .separator.width_profile.mode,
                    "conditional",
                )

    def test_full_strip_geometry_support_has_no_policy_switch(self) -> None:
        from x5crop.formats import FORMATS
        from x5crop.policies.registry import get_detection_policy

        for spec in FORMATS.values():
            policy = get_detection_policy(spec.format_id, "full")
            self.assertNotIn(
                "geometry_support",
                policy.separator.__dataclass_fields__,
            )

    def test_active_detection_has_no_grid_gap_family(self) -> None:
        banned = (
            "GAP_GRID",
            "grid_model_gap",
            "stable_grid",
            "leading_grid",
            "grid_refine",
            "grid_outer_refine",
            "content_grid_placement",
        )
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")
        self.assertEqual(offenders, [])

    def test_format_descriptions_do_not_claim_format_specific_separator_widths(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "formats" / "descriptions.py"
        self.assertFalse(path.exists())

    def test_separator_support_is_not_locally_named_as_a_gate(self) -> None:
        paths = (
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "separator.py",
        )
        offenders = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for term in (
                "gate = separator_support_parameters",
                "gate = params.separator.separator_support",
            ):
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")
        self.assertEqual(offenders, [])

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

    def test_candidate_and_report_detail_do_not_restore_legacy_separator_width_names(self) -> None:
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

    def test_report_schema_identity_is_not_version_named(self) -> None:
        banned = (
            "REPORT_SCHEMA_VERSION",
            "v4_9_policy_schema",
            "schema_version",
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

    def test_report_schema_identity_is_owned_by_report_layer(self) -> None:
        policy_identity_source = (
            PROJECT_ROOT / "x5crop" / "policies" / "identity.py"
        ).read_text(encoding="utf-8")
        policy_reporting_source = (
            PROJECT_ROOT / "x5crop" / "policies" / "reporting" / "__init__.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("REPORT_SCHEMA_ID", policy_identity_source)
        self.assertNotIn("REPORT_SCHEMA_REVISION", policy_identity_source)
        self.assertNotIn("report_schema_id", policy_reporting_source)
        self.assertNotIn("report_schema_revision", policy_reporting_source)

    def test_agent_regression_guidance_does_not_hardcode_local_fixture_layout(self) -> None:
        agents_source = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        regression_section = agents_source.split("## Regression Priorities", 1)[1].split(
            "## Current Handoff", 1
        )[0]

        hardcoded_paths = [
            line
            for line in regression_section.splitlines()
            if "`Test/" in line and "`Test/`" not in line
        ]
        self.assertEqual(hardcoded_paths, [])

    def test_policy_identity_uses_canonical_format_id_without_alias_map(self) -> None:
        source = (PROJECT_ROOT / "x5crop" / "policies" / "identity.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("_POLICY_ID_STEMS", source)
        self.assertNotIn("unknown_strip", source)
        self.assertNotIn("policy_id_stem_for", source)

        from x5crop.policies.identity import (
            detection_policy_id_for,
        )

        self.assertEqual(
            detection_policy_id_for("120-66", "partial"),
            "detection:120-66:partial",
        )

    def test_current_changelog_names_the_current_report_schema(self) -> None:
        from x5crop.report.identity import REPORT_SCHEMA_REVISION

        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        chinese, english = changelog.split("## English Changelog", maxsplit=1)
        for section in (chinese, english):
            self.assertIn(f"`{REPORT_SCHEMA_REVISION}`", section)



if __name__ == "__main__":
    unittest.main()
