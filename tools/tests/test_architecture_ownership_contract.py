from __future__ import annotations

from pathlib import Path
import unittest

from tools.tests.architecture_contracts import (
    PROJECT_ROOT,
    duplicate_dataclass_models,
    translated_parameter_models,
)


class ArchitectureOwnershipContractTest(unittest.TestCase):
    def test_removed_architecture_surfaces_do_not_exist(self) -> None:
        removed = (
            "x5crop/gap_methods.py",
            "x5crop/debug/gaps.py",
            "x5crop/detection/evidence/count_planning.py",
            "x5crop/detection/evidence/exposure_overlap.py",
            "x5crop/detection/physical/outer",
            "x5crop/detection/candidate/extension",
            "x5crop/output/geometry_adjustment.py",
            "x5crop/output/protection.py",
            "x5crop/runtime/output_protection.py",
            "x5crop/policies/parameters/exposure_overlap.py",
            "x5crop/policies/runtime/sequence.py",
            "x5crop/policies/assembly/sequence.py",
        )
        self.assertEqual(
            [relative for relative in removed if (PROJECT_ROOT / relative).exists()],
            [],
        )

    def test_runtime_policy_has_current_physical_groups_only(self) -> None:
        from x5crop.policies.parameters.aggregate import FormatParameters
        from x5crop.policies.runtime.policy import DetectionPolicy

        self.assertEqual(
            tuple(FormatParameters.__dataclass_fields__),
            (
                "preprocess",
                "content",
                "separator",
                "candidate",
                "diagnostics",
            ),
        )
        self.assertEqual(
            tuple(DetectionPolicy.__dataclass_fields__),
            (
                "physical_spec",
                "strip_mode",
                "preprocess",
                "detector_kind",
                "separator",
                "content",
                "candidate_plan",
                "diagnostics",
            ),
        )

    def test_candidate_plan_contains_budget_parameters_not_source_labels(self) -> None:
        from x5crop.policies.parameters.candidate import CandidatePlanParameters

        self.assertEqual(
            tuple(CandidatePlanParameters.__dataclass_fields__),
            ("sequence_hypotheses", "sequence_solver", "dual_lane_divider"),
        )

    def test_policy_identity_is_derived_from_format_and_mode(self) -> None:
        from x5crop.policies.runtime.policy import DetectionPolicy

        self.assertNotIn("policy_id", DetectionPolicy.__dataclass_fields__)
        self.assertIsInstance(DetectionPolicy.policy_id, property)

    def test_parameter_layers_do_not_duplicate_or_translate_models(self) -> None:
        self.assertEqual(
            duplicate_dataclass_models(
                "x5crop.geometry.detection_parameters",
                "x5crop.policies.parameters",
            ),
            [],
        )
        self.assertEqual(
            duplicate_dataclass_models(
                "x5crop.policies.parameters",
                "x5crop.policies.runtime",
            ),
            [],
        )
        self.assertEqual(translated_parameter_models(), [])

    def test_evidence_cache_keys_include_parameters_and_exact_geometry(self) -> None:
        frame_support = (
            PROJECT_ROOT
            / "x5crop/detection/evidence/content/frame_support.py"
        ).read_text(encoding="utf-8")
        separator_cache = (
            PROJECT_ROOT / "x5crop/cache/separator.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "key = (parameters, *box_cache_key(sequence_box))",
            frame_support,
        )
        self.assertIn(
            "statistics_key = (parameters, *box_cache_key(sequence_box), float(threshold))",
            frame_support,
        )
        self.assertIn(
            "return (profile_config, *box_cache_key(corridor))",
            separator_cache,
        )

    def test_policy_assembly_has_one_central_builder(self) -> None:
        assembly = PROJECT_ROOT / "x5crop/policies/assembly"
        self.assertTrue((assembly / "factory.py").is_file())
        for obsolete in (
            "format_presets.py",
            "presets.py",
            "output.py",
            "finalization.py",
        ):
            self.assertFalse((assembly / obsolete).exists())

    def test_contract_test_modules_keep_one_reviewable_responsibility(self) -> None:
        offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for path in (PROJECT_ROOT / "tools/tests").glob("test_*_contract.py")
            if len(path.read_text(encoding="utf-8").splitlines()) > 800
        ]
        self.assertEqual(offenders, [])

    def test_regression_tools_are_current_schema_diff_auditors(self) -> None:
        source = (
            PROJECT_ROOT / "tools/regression/compare.py"
        ).read_text(encoding="utf-8")
        self.assertIn("final_review_reasons", source)
        for forbidden in ("parity_gate", "golden_oracle", "reference_classify"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
