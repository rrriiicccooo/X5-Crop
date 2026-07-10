from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


class CurrentSchemaNamingContractTest(unittest.TestCase):
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
            if "film_format" in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
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
        from x5crop.policies.assembly.format_presets import mode_policy_preset

        for spec in FORMATS.values():
            if spec.physical_layout != "single_strip":
                continue
            for strip_mode in ("full", "partial"):
                self.assertEqual(
                    mode_policy_preset(spec.format_id.value, strip_mode)
                    .separator_width_profile.mode,
                    "conditional",
                )

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
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "profile_defaults.py",
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



if __name__ == "__main__":
    unittest.main()
