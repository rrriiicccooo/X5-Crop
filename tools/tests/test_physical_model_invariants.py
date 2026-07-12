from __future__ import annotations

import math
import unittest

from x5crop.detection.physical.model import SequenceResiduals
from x5crop.domain import (
    AxisBleedParameters,
    BoundaryPositionConstraint,
    Box,
    CropEnvelope,
    FrameBoundary,
    FrameBoundaryReference,
    FrameDimensionPrior,
    HolderSpan,
    MeasurementProvenance,
    PixelInterval,
    SeparatorWidthConstraint,
    SequenceHypothesis,
    VisibleSequenceSpan,
)
from x5crop.output.model import (
    BoundaryOverlapProtection,
    FrameBleedPlan,
    FrameSideBleed,
    OutputGeometry,
)
from x5crop.units import ScanCalibration


def _provenance() -> MeasurementProvenance:
    return MeasurementProvenance("synthetic_measurement", "test", ())


class PhysicalModelInvariantTest(unittest.TestCase):
    def test_pixel_intervals_and_residuals_require_finite_values(self) -> None:
        with self.assertRaises(ValueError):
            PixelInterval(math.nan, 1.0)
        with self.assertRaises(ValueError):
            SequenceResiduals(math.nan, None, 0.0)
        with self.assertRaises(ValueError):
            SequenceResiduals(None, None, -1.0)

    def test_physical_spans_and_priors_reject_impossible_geometry(self) -> None:
        for span_type in (HolderSpan, VisibleSequenceSpan, CropEnvelope):
            with self.subTest(span_type=span_type), self.assertRaises(ValueError):
                span_type(Box(10, 0, 5, 10))
        with self.assertRaises(ValueError):
            FrameDimensionPrior(
                PixelInterval(0.0, 10.0),
                PixelInterval(1.0, 10.0),
                ((36.0, 24.0),),
                "synthetic",
                _provenance(),
            )

    def test_sequence_hypothesis_envelope_must_cover_visible_sequence(self) -> None:
        with self.assertRaises(ValueError):
            SequenceHypothesis(
                "invalid",
                VisibleSequenceSpan(Box(0, 0, 100, 100)),
                CropEnvelope(Box(10, 0, 90, 100)),
                "boundary_led",
                _provenance(),
                (),
            )

    def test_boundary_constraints_and_sources_have_consistent_identity(self) -> None:
        with self.assertRaises(ValueError):
            BoundaryPositionConstraint(0, PixelInterval.exact(10.0), _provenance())
        with self.assertRaises(ValueError):
            SeparatorWidthConstraint(1, PixelInterval(-1.0, 2.0), _provenance())
        with self.assertRaises(ValueError):
            FrameBoundary(
                1,
                PixelInterval.exact(10.0),
                "observed_separator",
                _provenance(),
            )
        with self.assertRaises(ValueError):
            FrameBoundary(
                1,
                PixelInterval.exact(10.0),
                "dimension_constrained",
                _provenance(),
            )

    def test_scan_calibration_rejects_impossible_trusted_state_and_axis(self) -> None:
        with self.assertRaises(ValueError):
            ScanCalibration(None, None, "tiff_resolution", True)
        calibration = ScanCalibration(10.0, 10.0, "tiff_resolution", True)
        with self.assertRaises(ValueError):
            calibration.px_per_mm("long")

    def test_output_models_reject_invalid_geometry_and_plan_state(self) -> None:
        with self.assertRaises(ValueError):
            OutputGeometry(
                CropEnvelope(Box(0, 0, 100, 100)),
                (Box(0, 0, 0, 100),),
            )
        with self.assertRaises(ValueError):
            FrameSideBleed(0, -1, 0, 0)
        with self.assertRaises(ValueError):
            BoundaryOverlapProtection(
                FrameBoundaryReference(None, 1),
                0,
                1,
                5,
                -1,
                5,
                "synthetic",
            )
        with self.assertRaises(ValueError):
            FrameBleedPlan(
                AxisBleedParameters(0, 0),
                (FrameSideBleed(0, 0, 0, 0),),
                (),
                (FrameBoundaryReference(None, 1),),
                True,
                "no_output_overlap",
            )


if __name__ == "__main__":
    unittest.main()
