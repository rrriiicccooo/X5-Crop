from __future__ import annotations

import unittest

from x5crop.domain import (
    MeasurementIdentity,
    MeasurementProvenance,
)

from x5crop.units import (
    CalibrationState,
    PhysicalScaleObservation,
    PhysicalScaleScope,
    PhysicalScaleSource,
    ResolutionMetadataObservation,
    ScanCalibrationResolution,
    resolution_metadata_observation,
)


class UnitModelTests(unittest.TestCase):
    def test_resolution_metadata_is_an_observation_not_trusted_calibration(self) -> None:
        observation = resolution_metadata_observation((300.0, 300.0), 2)

        self.assertIsInstance(observation, ResolutionMetadataObservation)
        self.assertAlmostEqual(observation.x_px_per_mm or 0.0, 300.0 / 25.4)
        self.assertAlmostEqual(observation.y_px_per_mm or 0.0, 300.0 / 25.4)
        self.assertNotIn("trusted", observation.__dataclass_fields__)

    def test_metadata_alone_leaves_calibration_unavailable(self) -> None:
        observation = resolution_metadata_observation((300.0, 300.0), 2)
        calibration = ScanCalibrationResolution.from_observations(
            observation,
            (),
        )

        self.assertEqual(calibration.x.state, CalibrationState.UNAVAILABLE)
        self.assertEqual(calibration.y.state, CalibrationState.UNAVAILABLE)

    def test_missing_or_invalid_resolution_stays_in_metadata_diagnostics(self) -> None:
        missing = resolution_metadata_observation(None, None)
        invalid = resolution_metadata_observation((300.0, 300.0), 1)
        unsupported = resolution_metadata_observation((300.0, 300.0), 99)

        self.assertIn("missing_tiff_resolution", missing.diagnostics)
        self.assertIn("resolution_unit_has_no_absolute_length", invalid.diagnostics)
        self.assertIn("unsupported_resolution_unit:99", unsupported.diagnostics)

    def test_holder_clipping_produces_only_an_approximate_lower_bound(self) -> None:
        metadata = resolution_metadata_observation((300.0, 300.0), 2)
        calibration = ScanCalibrationResolution.from_observations(
            metadata,
            (
                PhysicalScaleObservation(
                    "y",
                    100.0,
                    None,
                    PhysicalScaleSource.FRAME_SHORT_AXIS,
                    PhysicalScaleScope.ROOT_MEASUREMENT,
                    MeasurementProvenance(
                        MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                        "test_scale",
                        (MeasurementIdentity.BOUNDARY_PATHS,),
                    ),
                ),
            ),
        )

        self.assertEqual(calibration.y.state, CalibrationState.APPROXIMATE)
        self.assertIsNone(calibration.y.px_per_mm)
        self.assertIn(
            "tiff_resolution_contradicted_by_physical_scale",
            calibration.y.diagnostics,
        )

    def test_visible_film_base_can_supply_an_upper_bound(self) -> None:
        calibration = ScanCalibrationResolution.from_observations(
            ResolutionMetadataObservation(None, None),
            (
                PhysicalScaleObservation(
                    "y",
                    None,
                    120.0,
                    PhysicalScaleSource.FRAME_SHORT_AXIS,
                    PhysicalScaleScope.ROOT_MEASUREMENT,
                    MeasurementProvenance(
                        MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                        "test_scale",
                        (MeasurementIdentity.BOUNDARY_PATHS,),
                    ),
                ),
            ),
        )

        self.assertEqual(calibration.y.state, CalibrationState.APPROXIMATE)
        self.assertIsNone(calibration.y.minimum_px_per_mm)
        self.assertEqual(calibration.y.maximum_px_per_mm, 120.0)

if __name__ == "__main__":
    unittest.main()
