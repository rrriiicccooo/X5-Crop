from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import (
    PROJECT_ROOT,
    duplicate_dataclass_models,
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
            "x5crop/configuration/profiles.py",
            "x5crop/configuration/assembly.py",
            "x5crop/constants.py",
        )
        self.assertEqual(
            [relative for relative in removed if (PROJECT_ROOT / relative).exists()],
            [],
        )

    def test_runtime_configuration_has_current_physical_groups_only(self) -> None:
        from x5crop.configuration.model import DetectionConfiguration

        self.assertEqual(
            tuple(DetectionConfiguration.__dataclass_fields__),
            (
                "physical_spec",
                "strip_mode",
                "preprocess",
                "boundary",
                "separator",
                "content",
                "candidate_plan",
                "diagnostics",
            ),
        )
        self.assertIsInstance(DetectionConfiguration.detector_kind, property)

    def test_candidate_plan_contains_budget_parameters_not_source_labels(self) -> None:
        from x5crop.configuration.candidate import CandidatePlanParameters

        self.assertEqual(
            tuple(CandidatePlanParameters.__dataclass_fields__),
            ("sequence_hypotheses", "sequence_solver", "dual_lane_divider"),
        )

    def test_configuration_identity_is_derived_from_format_and_mode(self) -> None:
        from x5crop.configuration.model import DetectionConfiguration

        self.assertNotIn(
            "configuration_id",
            DetectionConfiguration.__dataclass_fields__,
        )
        self.assertIsInstance(
            DetectionConfiguration.configuration_id,
            property,
        )

    def test_legacy_policy_topology_is_absent(self) -> None:
        self.assertFalse((PROJECT_ROOT / "x5crop/policies").exists())

    def test_configuration_does_not_duplicate_foundation_models(self) -> None:
        self.assertEqual(
            duplicate_dataclass_models(
                "x5crop.geometry.detection_parameters",
                "x5crop.configuration",
            ),
            [],
        )

    def test_evidence_cache_keys_include_parameters_and_exact_geometry(self) -> None:
        from x5crop.cache import (
            MeasurementParametersKey,
            MeasurementRegionKey,
            ThresholdedMeasurementRegionKey,
        )

        self.assertEqual(
            tuple(field.name for field in fields(MeasurementParametersKey)),
            ("parameters",),
        )
        self.assertEqual(
            tuple(field.name for field in fields(MeasurementRegionKey)),
            ("parameters", "region"),
        )
        self.assertEqual(
            tuple(
                field.name for field in fields(ThresholdedMeasurementRegionKey)
            ),
            ("parameters", "region", "threshold"),
        )

    def test_configuration_registry_is_the_only_builder(self) -> None:
        root = PROJECT_ROOT / "x5crop/configuration"
        self.assertTrue((root / "registry.py").is_file())
        for obsolete in ("profiles.py", "assembly.py", "aggregate.py"):
            self.assertFalse((root / obsolete).exists())

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
