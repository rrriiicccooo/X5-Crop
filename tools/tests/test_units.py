from __future__ import annotations

import unittest

from x5crop.domain import ImageProfile
from x5crop.units import (
    ScanCalibration,
    scan_calibration_from_profile,
)


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
        calibration = scan_calibration_from_profile(_profile())

        self.assertNotIn(
            "inferred_from_frame_short_axis",
            calibration.__dataclass_fields__,
        )
        self.assertEqual(calibration.source, "unavailable")

    def test_scan_calibration_from_inch_resolution(self) -> None:
        calibration = scan_calibration_from_profile(_profile(((300, 1), (300, 1)), 2))
        self.assertTrue(calibration.trusted)
        self.assertEqual(calibration.source, "tiff_resolution")
        self.assertAlmostEqual(calibration.x_px_per_mm or 0.0, 300.0 / 25.4)
        self.assertAlmostEqual(calibration.y_px_per_mm or 0.0, 300.0 / 25.4)

    def test_scan_calibration_from_centimeter_resolution(self) -> None:
        calibration = scan_calibration_from_profile(_profile(((120, 1), (120, 1)), 3))
        self.assertTrue(calibration.trusted)
        self.assertAlmostEqual(calibration.x_px_per_mm or 0.0, 12.0)
        self.assertAlmostEqual(calibration.y_px_per_mm or 0.0, 12.0)

    def test_scan_calibration_rejects_missing_or_invalid_units(self) -> None:
        missing = scan_calibration_from_profile(_profile())
        invalid = scan_calibration_from_profile(_profile(((300, 1), (300, 1)), 1))
        unsupported = scan_calibration_from_profile(_profile(((300, 1), (300, 1)), 99))

        self.assertFalse(missing.trusted)
        self.assertIn("missing_tiff_resolution", missing.warnings)
        self.assertFalse(invalid.trusted)
        self.assertIn("resolution_unit_has_no_absolute_length", invalid.warnings)
        self.assertFalse(unsupported.trusted)
        self.assertIn("unsupported_resolution_unit:99", unsupported.warnings)

    def test_valid_anisotropic_resolution_is_preserved_per_axis(self) -> None:
        calibration = scan_calibration_from_profile(
            _profile(((300, 1), (1200, 1)), 2)
        )
        self.assertTrue(calibration.trusted)
        self.assertAlmostEqual(calibration.x_px_per_mm or 0.0, 300.0 / 25.4)
        self.assertAlmostEqual(calibration.y_px_per_mm or 0.0, 1200.0 / 25.4)

if __name__ == "__main__":
    unittest.main()
