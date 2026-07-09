from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import unittest

from x5crop.policies.parameters.aggregate import FormatParameters


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ArchitectureResidualContractTest(unittest.TestCase):
    def test_format_parameters_expose_only_fixed_parameter_groups(self) -> None:
        field_names = [field.name for field in fields(FormatParameters)]
        self.assertEqual(
            field_names,
            [
                "name",
                "preprocess",
                "content",
                "outer",
                "separator",
                "candidate",
                "decision",
                "output",
                "diagnostics",
            ],
        )
        old_flat_fields = (
            "content_profile",
            "outer_strategy",
            "separator_support",
            "partial_counts",
            "decision_review",
            "output_overlap",
            "deskew",
        )
        for field_name in old_flat_fields:
            self.assertNotIn(field_name, field_names)

    def test_policy_assembly_does_not_use_reported_physical_note_strings(self) -> None:
        banned = (
            "known_physical_notes",
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

    def test_destructive_cleanup_removes_legacy_policy_and_import_hooks(self) -> None:
        banned = (
            "source_parameters",
            "import_format_module",
            "format_module_name",
            "RuntimePolicyContext",
            "policy_context.py",
            "PARAMETER_FACTORIES",
            "FORMAT_OVERRIDE_PARAMETER_PATHS",
            "split_format_parameter_overrides",
            "source orchestration",
            "FormatParameterViews",
            "parameters.views",
            "decision_contract_for(",
            "default_content_evidence_image_parameters",
            "default_separator_evidence_image_parameters",
            "default_deskew_fallback_evidence_parameters",
            "export.paths",
            "robust_grid",
            "RobustGrid",
            "ROBUST_GRID",
            "candidate_gate_passed",
            "partial_safe_extra_frames",
            "safe_extra_frames",
            "EVIDENCE_POLICY_OVERRIDES",
            "EVIDENCE_POLICY_MODE_OVERRIDES",
            "evidence_policy_values",
            "unacceptable_wrong_pass",
            "risky_regression",
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

    def test_format_preset_assembly_does_not_own_profiles_or_descriptions(self) -> None:
        text = (
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "format_presets.py"
        ).read_text(encoding="utf-8")
        banned = (
            "FrameFitPolicy(",
            "SeparatorEdgePairPolicy(",
            "safe extra",
            "def _notes",
            "def _role",
        )
        offenders = [term for term in banned if term in text]
        self.assertEqual(offenders, [])

    def test_approved_geometry_adjustment_is_output_adjacent(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "detection" / "final" / "geometry.py").exists()
        )
        self.assertTrue(
            (PROJECT_ROOT / "x5crop" / "output" / "geometry_adjustment.py").is_file()
        )

    def test_workflow_does_not_create_output_directory_before_io(self) -> None:
        text = (PROJECT_ROOT / "x5crop" / "runtime" / "workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("output_dir.mkdir", text)
        self.assertIn("output_surface_for_input", text)

    def test_regression_tools_use_current_final_reason_field(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "tools" / "regression").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if '"review_reasons"' in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_foundation_helpers_require_explicit_parameters(self) -> None:
        banned = (
            "params=None",
            "params: None",
            "config=None",
            "config: None",
            "policy=None",
            "policy: None",
        )
        checked_roots = (
            PROJECT_ROOT / "x5crop" / "geometry",
            PROJECT_ROOT / "x5crop" / "cache",
            PROJECT_ROOT / "x5crop" / "detection" / "physical",
            PROJECT_ROOT / "x5crop" / "detection" / "evidence",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance",
        )
        offenders: list[str] = []
        for root in checked_roots:
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_foundation_physical_evidence_and_guidance_do_not_accept_full_detection_policy(self) -> None:
        checked_roots = (
            PROJECT_ROOT / "x5crop" / "geometry",
            PROJECT_ROOT / "x5crop" / "image",
            PROJECT_ROOT / "x5crop" / "io",
            PROJECT_ROOT / "x5crop" / "cache",
            PROJECT_ROOT / "x5crop" / "detection" / "physical",
            PROJECT_ROOT / "x5crop" / "detection" / "evidence",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance",
        )
        offenders: list[str] = []
        for root in checked_roots:
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if "DetectionPolicy" in text:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
