from __future__ import annotations

import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from tools.tests.parameter_contracts import (
    hidden_detection_percentiles,
    parameter_contracts,
    stale_parameter_contracts,
    unclassified_parameter_fields,
)
from x5crop.configuration.preprocess import PreprocessConfiguration
from x5crop.image.evidence import (
    DeskewFallbackEvidenceParameters,
    SeparatorEvidenceImageParameters,
)
import x5crop.units as units


class ParameterLegitimacyContractTest(unittest.TestCase):
    def test_every_runtime_parameter_has_one_complete_contract(self) -> None:
        self.assertEqual(unclassified_parameter_fields(), [])
        self.assertEqual(stale_parameter_contracts(), [])
        for contract in parameter_contracts().values():
            self.assertTrue(contract.unit)
            self.assertTrue(contract.stage)
            self.assertTrue(contract.rationale)

    def test_detection_percentiles_are_explicit_parameters(self) -> None:
        self.assertEqual(hidden_detection_percentiles(), [])

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

    def test_single_frame_boundary_requirement_is_named(self) -> None:
        source = (
            PROJECT_ROOT
            / "x5crop/detection/candidate/assessment/candidate.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("len(measured_single_frame_boundaries) >= 2", source)


if __name__ == "__main__":
    unittest.main()
