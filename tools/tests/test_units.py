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

    def test_physical_length_uses_calibration_before_ratio_and_clamp(self) -> None:
        trusted = ScanCalibration(10.0, 10.0, "tiff_resolution", True)
        untrusted = ScanCalibration(None, None, "unavailable", False)
        length = PhysicalLength(mm=5.0, fallback_ratio=0.25, min_px=20.0, max_px=80.0)

        self.assertEqual(length.resolve_px(trusted, axis="x", reference_px=400.0), 50.0)
        self.assertEqual(length.resolve_px(untrusted, axis="x", reference_px=400.0), 80.0)

    def test_physical_length_falls_back_to_pixel_clamp_without_reference(self) -> None:
        untrusted = ScanCalibration(None, None, "unavailable", False)
        length = PhysicalLength(fallback_ratio=0.25, min_px=12.0, max_px=80.0)
        self.assertEqual(length.resolve_px(untrusted, axis="x"), 12.0)


if __name__ == "__main__":
    unittest.main()
