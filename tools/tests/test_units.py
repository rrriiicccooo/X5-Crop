from __future__ import annotations

import unittest

from x5crop.domain import ImageProfile
from x5crop.units import (
    PhysicalLength,
    ScanCalibration,
    ScanCalibrationTrustParameters,
    scan_calibration_from_profile,
)


TRUST_PARAMETERS = ScanCalibrationTrustParameters()


def _profile(resolution=None, unit=None) -> ImageProfile:
    return ImageProfile(
        shape=(100, 200),
        dtype="uint16",
        axes="YX",
        photometric="MINISBLACK",
        compression="NONE",
        sample_format=None,
        bits_per_sample=16,
        samples_per_pixel=1,
        planar_config=None,
        resolution=resolution,
        resolution_unit=unit,
        icc_profile=None,
    )


class UnitModelTests(unittest.TestCase):
    def test_scan_calibration_has_no_candidate_inference_residue(self) -> None:
        calibration = scan_calibration_from_profile(_profile(), TRUST_PARAMETERS)

        self.assertNotIn(
            "inferred_from_frame_short_axis",
            calibration.__dataclass_fields__,
        )
        self.assertEqual(calibration.source, "unavailable")

    def test_scan_calibration_from_inch_resolution(self) -> None:
        calibration = scan_calibration_from_profile(_profile(((300, 1), (300, 1)), 2), TRUST_PARAMETERS)
        self.assertTrue(calibration.trusted)
        self.assertEqual(calibration.source, "tiff_resolution")
        self.assertAlmostEqual(calibration.x_px_per_mm or 0.0, 300.0 / 25.4)
        self.assertAlmostEqual(calibration.y_px_per_mm or 0.0, 300.0 / 25.4)

    def test_scan_calibration_from_centimeter_resolution(self) -> None:
        calibration = scan_calibration_from_profile(_profile(((120, 1), (120, 1)), 3), TRUST_PARAMETERS)
        self.assertTrue(calibration.trusted)
        self.assertAlmostEqual(calibration.x_px_per_mm or 0.0, 12.0)
        self.assertAlmostEqual(calibration.y_px_per_mm or 0.0, 12.0)

    def test_scan_calibration_rejects_missing_or_invalid_units(self) -> None:
        missing = scan_calibration_from_profile(_profile(), TRUST_PARAMETERS)
        invalid = scan_calibration_from_profile(_profile(((300, 1), (300, 1)), 1), TRUST_PARAMETERS)
        unsupported = scan_calibration_from_profile(_profile(((300, 1), (300, 1)), 99), TRUST_PARAMETERS)

        self.assertFalse(missing.trusted)
        self.assertIn("missing_tiff_resolution", missing.warnings)
        self.assertFalse(invalid.trusted)
        self.assertIn("resolution_unit_has_no_absolute_length", invalid.warnings)
        self.assertFalse(unsupported.trusted)
        self.assertIn("unsupported_resolution_unit:99", unsupported.warnings)

    def test_physical_length_prefers_trusted_mm(self) -> None:
        length = PhysicalLength(2.0, 0.10, 1, 500)
        calibration = ScanCalibration(20.0, 20.0, "tiff_resolution", True)
        self.assertEqual(
            length.resolve_px(calibration, axis="x", reference_px=100.0),
            40,
        )

    def test_physical_length_falls_back_to_reference_ratio(self) -> None:
        length = PhysicalLength(2.0, 0.10, 1, 500)
        calibration = ScanCalibration(None, None, "unavailable", False)
        self.assertEqual(
            length.resolve_px(calibration, axis="x", reference_px=100.0),
            10,
        )

    def test_physical_length_clamps_pixel_result(self) -> None:
        length = PhysicalLength(None, 0.50, 8, 20)
        calibration = ScanCalibration(None, None, "unavailable", False)
        self.assertEqual(length.resolve_px(calibration, axis="x", reference_px=4), 8)
        self.assertEqual(length.resolve_px(calibration, axis="x", reference_px=100), 20)

    def test_overlap_bleed_capacity_uses_physical_length(self) -> None:
        from x5crop.policies.parameters.output import (
            OverlapBleedParameters,
        )

        parameters = OverlapBleedParameters()
        self.assertIsInstance(parameters.long_axis_bleed_capacity, PhysicalLength)

if __name__ == "__main__":
    unittest.main()
