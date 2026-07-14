from __future__ import annotations

import unittest

import x5crop.units as units

from x5crop.units import (
    ResolutionMetadataObservation,
    resolution_metadata_observation,
)


class UnitModelTests(unittest.TestCase):
    def test_units_has_no_unreachable_scan_calibration_model(self) -> None:
        self.assertFalse(hasattr(units, "ScanCalibrationResolution"))
        self.assertFalse(hasattr(units, "CalibrationAxisResolution"))
        self.assertFalse(hasattr(units, "resolution_metadata_after_rotation"))

    def test_resolution_metadata_is_an_observation_not_trusted_calibration(self) -> None:
        observation = resolution_metadata_observation((300.0, 300.0), 2)

        self.assertIsInstance(observation, ResolutionMetadataObservation)
        self.assertAlmostEqual(observation.x_px_per_mm or 0.0, 300.0 / 25.4)
        self.assertAlmostEqual(observation.y_px_per_mm or 0.0, 300.0 / 25.4)
        self.assertNotIn("trusted", observation.__dataclass_fields__)

    def test_missing_or_invalid_resolution_stays_in_metadata_diagnostics(self) -> None:
        missing = resolution_metadata_observation(None, None)
        invalid = resolution_metadata_observation((300.0, 300.0), 1)
        unsupported = resolution_metadata_observation((300.0, 300.0), 99)

        self.assertIn("missing_tiff_resolution", missing.diagnostics)
        self.assertIn("resolution_unit_has_no_absolute_length", invalid.diagnostics)
        self.assertIn("unsupported_resolution_unit:99", unsupported.diagnostics)

if __name__ == "__main__":
    unittest.main()
