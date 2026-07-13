from __future__ import annotations

from dataclasses import fields, replace
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    supported_calibration_fixture,
    unavailable_calibration_fixture,
)
from x5crop.detection.evidence.physical_scale import physical_scale_observations
from x5crop.detection.physical.photo_size import (
    FrameDimensionEvidence,
    frame_dimension_evidence,
    frame_dimension_priors,
)
from x5crop.domain import (
    EvidenceState,
    FrameDimensionPriorSource,
    HolderSpan,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoApertureEdgeSource,
    PixelInterval,
)
from x5crop.formats import format_spec


def _dimension_evidence(
    widths: tuple[PixelInterval, ...],
    separator_widths: tuple[float, ...],
) -> FrameDimensionEvidence:
    return FrameDimensionEvidence(
        frame_width_mm=56.0,
        frame_height_mm=56.0,
        frame_width_prior_px=PixelInterval(95.0, 105.0),
        photo_width_intervals_px=widths,
        separator_widths_px=separator_widths,
        observed_width_mm=None,
        observed_height_mm=None,
        observed_aspect=1.0,
        aspect_error_ratio=0.0,
        calibration_used=False,
    )


class PhotoSizePhysicalModelTest(unittest.TestCase):
    def test_holder_slack_is_not_dimension_or_scale_evidence(self) -> None:
        candidate = candidate_fixture()
        geometry = candidate.geometry
        expanded_holder = replace(
            geometry,
            holder_span=HolderSpan(
                replace(geometry.holder_span.box, right=geometry.holder_span.box.right + 90)
            ),
        )

        self.assertEqual(
            frame_dimension_evidence(
                geometry,
                unavailable_calibration_fixture(),
            ),
            frame_dimension_evidence(
                expanded_holder,
                unavailable_calibration_fixture(),
            ),
        )
        self.assertEqual(
            physical_scale_observations(
                geometry,
                candidate.assessment.evidence.holder_boundary,
            ),
            physical_scale_observations(
                expanded_holder,
                candidate.assessment.evidence.holder_boundary,
            ),
        )

    def test_discrete_frame_sizes_produce_discrete_priors(self) -> None:
        priors = frame_dimension_priors(
            format_spec("120-66"),
            supported_calibration_fixture(10.0, 10.0),
            layout="horizontal",
        )
        self.assertEqual(
            tuple(prior.frame_size_mm for prior in priors),
            ((56.0, 56.0), (54.0, 54.0)),
        )
        self.assertEqual(
            tuple(prior.calibrated_width_px for prior in priors),
            (PixelInterval.exact(560.0), PixelInterval.exact(540.0)),
        )
        self.assertNotIn(
            PixelInterval.exact(550.0),
            tuple(prior.calibrated_width_px for prior in priors),
        )

    def test_uncalibrated_priors_preserve_every_physical_size_option(self) -> None:
        priors = frame_dimension_priors(
            format_spec("120-66"),
            unavailable_calibration_fixture(),
            layout="horizontal",
        )
        self.assertEqual(
            tuple(prior.frame_size_mm for prior in priors),
            ((56.0, 56.0), (54.0, 54.0)),
        )
        self.assertTrue(
            all(prior.source == FrameDimensionPriorSource.PHYSICAL_ASPECT for prior in priors)
        )

    def test_dimension_evidence_names_selected_physical_size(self) -> None:
        names = {field.name for field in fields(FrameDimensionEvidence)}
        self.assertTrue(
            {"frame_width_mm", "frame_height_mm", "frame_aspect"} <= names
        )
        self.assertFalse(any(name.startswith("nominal_") for name in names))

    def test_physical_prior_does_not_become_dimension_evidence(self) -> None:
        geometry = candidate_fixture().geometry
        provenance = MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            "dimension_only_aperture",
            (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
        )
        apertures = tuple(
            replace(
                aperture,
                leading=replace(
                    aperture.leading,
                    state=EvidenceState.UNAVAILABLE,
                    source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
                    provenance=provenance,
                ),
                trailing=replace(
                    aperture.trailing,
                    state=EvidenceState.UNAVAILABLE,
                    source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
                    provenance=provenance,
                ),
            )
            for aperture in geometry.photo_apertures
        )
        provisional = replace(
            geometry,
            photo_apertures=apertures,
            separator_assignments=(),
        )

        evidence = frame_dimension_evidence(
            provisional,
            unavailable_calibration_fixture(),
        )

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.photo_widths_px, ())

    def test_separator_width_variation_does_not_contradict_photo_size(self) -> None:
        evidence = _dimension_evidence(
            (
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
            ),
            (2.0, 18.0),
        )

        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertGreater(evidence.separator_width_cv or 0.0, 0.0)

    def test_photo_width_variation_is_a_physical_contradiction(self) -> None:
        evidence = _dimension_evidence(
            (
                PixelInterval.exact(100.0),
                PixelInterval.exact(125.0),
            ),
            (10.0,),
        )

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertEqual(evidence.reason, "physical_frame_dimensions_contradicted")


if __name__ == "__main__":
    unittest.main()
