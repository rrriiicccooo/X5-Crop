from __future__ import annotations

from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


class CurrentSchemaNamingContractTest(unittest.TestCase):
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
