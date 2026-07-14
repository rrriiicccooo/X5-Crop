from __future__ import annotations

import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from tools.tests.parameter_contracts import (
    ParameterRole,
    hidden_runtime_numeric_literals,
    hidden_runtime_percentiles,
    parameter_contracts,
    stale_parameter_contracts,
    unclassified_parameter_owners,
)
from x5crop.configuration.preprocess import PreprocessConfiguration
from x5crop.image.evidence import (
    ContentEvidenceImageParameters,
    DeskewFallbackEvidenceParameters,
    SeparatorEvidenceImageParameters,
)
from x5crop.image.deskew_parameters import DeskewParameters
from x5crop.configuration.content import ContentEvidenceParameters
from x5crop.configuration.candidate import (
    SequenceSolverParameters,
)
from x5crop.configuration.separator import SeparatorObservationParameters
from x5crop.detection.candidate.plan.model import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.output.model import AxisBleedParameters
from x5crop.formats import FormatPhysicalSpec, FrameSizeMm, expected_separator_count
from x5crop.image.separator_profile import SeparatorProfileParameters
from x5crop.geometry.sampling import sampling_step_for_limit
from x5crop.run_config import RunConfig
from x5crop.runtime.options import RuntimeOptions
from x5crop.utils import bbox_from_mask, sampled_percentile
from inspect import signature
import x5crop.units as units


class ParameterLegitimacyContractTest(unittest.TestCase):
    def test_invalid_physical_facts_and_execution_budgets_are_rejected(self) -> None:
        invalid_factories = (
            lambda: FrameSizeMm(0.0, 24.0),
            lambda: FormatPhysicalSpec(
                "invalid",
                3,
                (1, 2),
                "test",
                (FrameSizeMm(36.0, 24.0),),
            ),
            lambda: CountHypothesis(
                0,
                "partial",
                CountHypothesisSource.AUTOMATIC,
            ),
            lambda: AxisBleedParameters(-1, 0),
            lambda: SeparatorProfileParameters(segments=0),
            lambda: SeparatorObservationParameters(minimum_run_px=0),
            lambda: SeparatorObservationParameters(maximum_observations=0),
            lambda: SequenceSolverParameters(maximum_assignment_evaluations=0),
            lambda: ContentEvidenceImageParameters(
                minimum_consensus_channels=5,
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

        with self.assertRaises(ValueError):
            expected_separator_count(0, "single_strip", 1)
        with self.assertRaises(ValueError):
            sampling_step_for_limit(100, 0)

    def test_every_runtime_parameter_has_one_complete_contract(self) -> None:
        self.assertEqual(unclassified_parameter_owners(), [])
        self.assertEqual(stale_parameter_contracts(), [])
        for contract in parameter_contracts().values():
            self.assertTrue(contract.unit)
            self.assertTrue(contract.stage)
            self.assertTrue(contract.rationale)

    def test_parameter_contract_units_are_single_physical_quantities(self) -> None:
        ambiguous_units = {
            "count_or_px",
            "mixed_measurement",
            "physical_identity",
            "rendering",
            "resolved_runtime_input",
        }
        offenders = {
            contract.owner: contract.unit
            for contract in parameter_contracts().values()
            if contract.unit in ambiguous_units
        }
        self.assertEqual(offenders, {})

    def test_deskew_measurements_are_not_reduced_to_an_empirical_scalar(self) -> None:
        for removed in (
            "auto_quality_ok",
            "fallback_quality_gain",
            "quality_inlier_weight",
        ):
            self.assertNotIn(removed, DeskewParameters.__dataclass_fields__)
        source = (
            PROJECT_ROOT / "x5crop/image/deskew.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("deskew_measurement_quality", source)

    def test_runtime_percentiles_are_explicit_parameters(self) -> None:
        self.assertEqual(hidden_runtime_percentiles(), [])

    def test_runtime_has_no_unowned_numeric_literals(self) -> None:
        self.assertEqual(hidden_runtime_numeric_literals(), [])

    def test_fixed_tonal_identity_thresholds_are_absent(self) -> None:
        self.assertNotIn(
            "tonal_dark_mean",
            SeparatorEvidenceImageParameters.__dataclass_fields__,
        )
        self.assertNotIn(
            "tonal_light_mean",
            SeparatorEvidenceImageParameters.__dataclass_fields__,
        )
        self.assertNotIn(
            "extreme_dark_threshold",
            DeskewFallbackEvidenceParameters.__dataclass_fields__,
        )
        self.assertNotIn(
            "extreme_light_threshold",
            DeskewFallbackEvidenceParameters.__dataclass_fields__,
        )
        self.assertNotIn(
            "footprint_dark_threshold",
            DeskewParameters.__dataclass_fields__,
        )

    def test_foundation_measurement_budgets_and_floors_are_explicit(self) -> None:
        self.assertNotIn(
            "minimum_active_pixels",
            ContentEvidenceImageParameters.__dataclass_fields__,
        )
        self.assertIs(
            signature(sampled_percentile).parameters["max_samples"].default,
            signature(sampled_percentile).empty,
        )
        self.assertIs(
            signature(bbox_from_mask).parameters["min_row_fraction"].default,
            signature(bbox_from_mask).empty,
        )
        self.assertIs(
            signature(bbox_from_mask).parameters["min_col_fraction"].default,
            signature(bbox_from_mask).empty,
        )
        self.assertIn(
            "numerical_floor",
            ContentEvidenceImageParameters.__dataclass_fields__,
        )
        self.assertIn(
            "maximum_percentile_samples",
            ContentEvidenceParameters.__dataclass_fields__,
        )

    def test_runtime_numeric_inputs_have_parameter_contracts(self) -> None:
        contracts = parameter_contracts()
        for model, field_names in (
            (
                RuntimeOptions,
                (
                    "requested_count",
                    "page",
                    "bleed",
                    "bleed_x",
                    "bleed_y",
                    "deskew_min_angle",
                    "deskew_max_angle",
                    "jobs",
                ),
            ),
            (
                RunConfig,
                (
                    "requested_count",
                    "page",
                    "bleed_x",
                    "bleed_y",
                    "deskew_min_angle",
                    "deskew_max_angle",
                    "jobs",
                ),
            ),
        ):
            for field_name in field_names:
                owner = f"{model.__module__}.{model.__name__}.{field_name}"
                self.assertIn(owner, contracts)

    def test_architecture_documents_every_parameter_role(self) -> None:
        architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )
        for role in ParameterRole:
            self.assertIn(f"`{role.value}`", architecture)

    def test_debug_separator_image_parameters_belong_to_diagnostics(self) -> None:
        self.assertNotIn(
            "separator_evidence_image",
            PreprocessConfiguration.__dataclass_fields__,
        )

    def test_scan_calibration_has_no_empirical_axis_ratio_gate(self) -> None:
        self.assertFalse(hasattr(units, "ScanCalibrationTrustParameters"))

    def test_content_guidance_uses_owned_numerical_floor(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/detection/evidence/content/regions.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("1e-06", source)
        self.assertNotIn("1e-6", source)

    def test_output_default_is_not_owned_by_output_layer(self) -> None:
        source = (PROJECT_ROOT / "x5crop/output/frame_bleed.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("DEFAULT_OUTPUT_BLEED", source)

if __name__ == "__main__":
    unittest.main()
