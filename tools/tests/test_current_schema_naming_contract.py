from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


class CurrentSchemaNamingContractTest(unittest.TestCase):
    def test_contract_tests_reference_only_current_paths(self) -> None:
        contract_source = (
            PROJECT_ROOT / "tools" / "tests" / "test_architecture_residual_contract.py"
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

    def test_active_source_has_no_property_or_constant_aliases(self) -> None:
        format_source = (
            PROJECT_ROOT / "x5crop" / "formats" / "__init__.py"
        ).read_text(encoding="utf-8")
        safety_source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "safety.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("def frame_aspect", format_source)
        self.assertNotIn("SAFETY_CANDIDATE_BLOCKER", safety_source)

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
        from x5crop.domain import DetectionCandidate, ProcessResult
        from x5crop.entry.options import CliOptions
        from x5crop.formats import FormatPhysicalSpec
        from x5crop.policies.decision.contract import DetectionDecisionContract
        from x5crop.run_config import RunConfig

        for contract in (DetectionCandidate, ProcessResult, CliOptions, RunConfig):
            self.assertIn("format_id", contract.__dataclass_fields__)
        self.assertNotIn("name", FormatPhysicalSpec.__dataclass_fields__)
        self.assertIn("physical_spec", DetectionDecisionContract.__dataclass_fields__)
        self.assertNotIn("format", DetectionDecisionContract.__dataclass_fields__)

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

    def test_full_strip_geometry_support_is_a_universal_physical_capability(self) -> None:
        from x5crop.formats import FORMATS
        from x5crop.policies.registry import get_detection_policy

        for spec in FORMATS.values():
            policy = get_detection_policy(spec.format_id, "full")
            expected = (
                ("detected_geometry", "stable_grid")
                if spec.physical_layout == "single_strip"
                else ()
            )
            self.assertEqual(policy.separator.geometry_support.active_modes(), expected)

    def test_format_descriptions_do_not_claim_format_specific_separator_widths(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "formats" / "descriptions.py"
        text = path.read_text(encoding="utf-8")
        banned = (
            "few_wide_internal_gaps",
            "broad_internal_separator_widths",
            "broad_internal_gap_widths_expected",
            "broad_separator_width_can_be_false_frame_boundary",
            "broad_separator_width_may_compete_with_content",
        )
        self.assertEqual([term for term in banned if term in text], [])

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
            decision_policy_id_for,
            detection_policy_id_for,
        )

        self.assertEqual(
            detection_policy_id_for("120-66", "partial"),
            "detection:120-66:partial",
        )
        self.assertEqual(
            decision_policy_id_for("120-66", "partial"),
            "decision:120-66:partial",
        )



if __name__ == "__main__":
    unittest.main()
