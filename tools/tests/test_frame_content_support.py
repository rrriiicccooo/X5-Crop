from __future__ import annotations

import unittest

import numpy as np

from tools.tests.physical_gate_support import candidate_evidence_fixture, candidate_fixture
from x5crop.cache import MeasurementCache
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.model import content_preservation_state
from x5crop.detection.evidence.content.external_boundaries import (
    external_aperture_preservation_evidence,
)
from x5crop.detection.evidence.photo_sequence_coverage import (
    PhotoSequenceCoverageEvidence,
)
from x5crop.detection.evidence.content.internal_boundaries import (
    inter_photo_boundary_preservation_evidence,
)
from x5crop.detection.evidence.content.photo_content import (
    PhotoContentEvidence,
    PhotoContentObservation,
    photo_content_evidence,
)
from x5crop.detection.evidence.content.activation import sample_supports_content
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    PhotoSequenceSolution,
    SequenceResiduals,
)
from x5crop.domain import (
    BoundarySide,
    Box,
    EvidenceState,
    FrameDimensionPrior,
    FrameDimensionPriorSource,
    HolderSpan,
    InterPhotoBoundaryReference,
    InterPhotoSpacing,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoAperture,
    PhotoApertureBoundaryResolution,
    PhotoApertureEdgeSource,
    PixelInterval,
)
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)


def _cache(gray: np.ndarray) -> MeasurementCache:
    evidence = (gray < 225).astype(np.uint8) * 255
    return MeasurementCache(
        "horizontal",
        gray,
        evidence,
        evidence.astype(np.float32) / 255.0,
        image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        ),
    )


def _single_aperture_geometry(
    box: Box,
    *,
    measured_boundaries: bool = True,
) -> PhotoSequenceSolution:
    provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        "synthetic_single_aperture",
        (MeasurementIdentity.GRAY_WORK,),
    )

    def edge(side: BoundarySide, position: float):
        return PhotoApertureBoundaryResolution(
            1,
            side,
            PixelInterval.exact(position),
            (
                EvidenceState.SUPPORTED
                if measured_boundaries
                else EvidenceState.UNAVAILABLE
            ),
            (
                PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
                if measured_boundaries
                else PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS
            ),
            provenance,
        )

    aperture = PhotoAperture(
        1,
        edge(BoundarySide.LEADING, float(box.left)),
        edge(BoundarySide.TRAILING, float(box.right)),
        edge(BoundarySide.TOP, float(box.top)),
        edge(BoundarySide.BOTTOM, float(box.bottom)),
    )
    return PhotoSequenceSolution(
        format_id="120-645",
        layout="horizontal",
        strip_mode="full",
        count=1,
        holder_span=HolderSpan(box),
        photo_apertures=(aperture,),
        aperture_edge_assignments=(),
        separator_observations=(),
        separator_assignments=(),
        inter_photo_spacings=(),
        frame_dimension_prior=FrameDimensionPrior(
            (42.0, 56.0),
            FrameDimensionPriorSource.PHYSICAL_ASPECT,
            MeasurementProvenance(
                MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                "synthetic_frame_prior",
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
            ),
        ),
        photo_width_constraint_px=PixelInterval.exact(float(box.width)),
        photo_height_constraint_px=PixelInterval.exact(float(box.height)),
        residuals=SequenceResiduals(0.0, 0.0, 0.0),
        assignment_consensus=BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.UNCONTESTED,
            1,
            (),
        ),
        search_budget_exhausted=False,
        automatic_processing_supported=True,
        sequence_provenance=provenance,
        raw_boundary_paths=(),
        holder_boundaries=(),
    )


def _measured_apertures_for_spacing(spacing_px: float) -> tuple[PhotoAperture, ...]:
    def edge(
        photo_index: int,
        side: BoundarySide,
        position: float,
    ) -> PhotoApertureBoundaryResolution:
        return PhotoApertureBoundaryResolution(
            photo_index,
            side,
            PixelInterval.exact(position),
            EvidenceState.SUPPORTED,
            PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
            MeasurementProvenance(
                MeasurementIdentity.BOUNDARY_PATHS,
                f"synthetic_photo_{photo_index}_{side.value}",
                (MeasurementIdentity.GRAY_WORK,),
            ),
        )

    first_trailing = 100.0
    second_leading = first_trailing + spacing_px
    return (
        PhotoAperture(
            1,
            edge(1, BoundarySide.LEADING, 0.0),
            edge(1, BoundarySide.TRAILING, first_trailing),
            edge(1, BoundarySide.TOP, 0.0),
            edge(1, BoundarySide.BOTTOM, 100.0),
        ),
        PhotoAperture(
            2,
            edge(2, BoundarySide.LEADING, second_leading),
            edge(2, BoundarySide.TRAILING, second_leading + 100.0),
            edge(2, BoundarySide.TOP, 0.0),
            edge(2, BoundarySide.BOTTOM, 100.0),
        ),
    )


class FrameContentSupportTest(unittest.TestCase):
    def test_internal_content_crossing_requires_physical_spacing_evidence(self) -> None:
        geometry = candidate_fixture().geometry
        crossing = PhotoContentEvidence(
            0.5,
            (
                PhotoContentObservation(1, 0.8, 0.8, True, ("right",)),
                PhotoContentObservation(2, 0.8, 0.8, True, ("left",)),
            ),
        )
        boundary = InterPhotoBoundaryReference(None, 1)
        provenance = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            "synthetic_spacing",
            (MeasurementIdentity.GRAY_WORK,),
        )
        cases = (
            (
                InterPhotoSpacing(
                    boundary,
                    PixelInterval.exact(10.0),
                    provenance,
                    InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS,
                ),
                EvidenceState.CONTRADICTED,
            ),
            (geometry.inter_photo_spacings[0], EvidenceState.SUPPORTED),
            (
                InterPhotoSpacing(
                    boundary,
                    PixelInterval.exact(0.0),
                    provenance,
                    InterPhotoSpacingBasis.OBSERVED,
                ),
                EvidenceState.SUPPORTED,
            ),
            (
                InterPhotoSpacing(
                    boundary,
                    PixelInterval.exact(-5.0),
                    provenance,
                    InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS,
                ),
                EvidenceState.SUPPORTED,
            ),
            (
                InterPhotoSpacing(
                    boundary,
                    PixelInterval.exact(-5.0),
                    provenance,
                    InterPhotoSpacingBasis.CORROBORATED_OVERLAP,
                ),
                EvidenceState.SUPPORTED,
            ),
        )
        for spacing, expected in cases:
            with self.subTest(basis=spacing.basis):
                evidence = inter_photo_boundary_preservation_evidence(
                    2,
                    _measured_apertures_for_spacing(
                        spacing.signed_width_px.midpoint,
                    ),
                    (spacing,),
                    crossing,
                )
                self.assertEqual(evidence.state, expected)
                if spacing.kind == "overlap":
                    self.assertEqual(
                        evidence.observations[0].spacing_evidence.basis,
                        InterPhotoSpacingBasis.CORROBORATED_OVERLAP,
                    )

    def test_undersized_sample_cannot_satisfy_content_support(self) -> None:
        self.assertFalse(
            sample_supports_content(
                np.ones((1, 1), dtype=np.float32),
                threshold=0.5,
                minimum_active_pixels=16,
            )
        )

    def test_external_content_crossing_is_not_silently_accepted(self) -> None:
        evidence = candidate_evidence_fixture()
        crossing = external_aperture_preservation_evidence(
            _single_aperture_geometry(
                Box(250, 20, 650, 100),
                measured_boundaries=False,
            ),
            _cache(
                np.pad(
                    np.zeros((80, 420), dtype=np.uint8),
                    ((20, 20), (240, 240)),
                    constant_values=255,
                )
            ),
            get_detection_configuration("120-645", "full").content.evidence,
        )
        self.assertEqual(crossing.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            content_preservation_state(
                evidence.photo_sequence_coverage,
                evidence.inter_photo_boundary_preservation,
                crossing,
                evidence.partial_edge_safety,
            ),
            EvidenceState.CONTRADICTED,
        )

    def test_empty_aperture_is_not_content_damage(self) -> None:
        geometry = candidate_fixture().geometry
        gray = np.full((100, 310), 255, dtype=np.uint8)
        gray[10:90, 170:300] = 0
        evidence = photo_content_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("135", "full").content,
        )
        self.assertNotEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertFalse(evidence.observations[0].content_present)
        self.assertTrue(evidence.observations[1].content_present)

    def test_external_content_measurement_does_not_rewrite_aperture_geometry(self) -> None:
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 50:850] = 0
        geometry = _single_aperture_geometry(Box(250, 0, 650, 120))

        preservation = external_aperture_preservation_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("120-645", "full").content.evidence,
        )

        self.assertEqual(preservation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            preservation.reason,
            "external_aperture_measurement_conflict",
        )
        self.assertEqual(geometry.photo_apertures[0].frame_crop_envelope.box, Box(250, 0, 650, 120))

    def test_single_noise_pixel_cannot_contradict_external_aperture(self) -> None:
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 250:650] = 0
        gray[0, 0] = 0
        geometry = _single_aperture_geometry(Box(250, 20, 650, 100))

        preservation = external_aperture_preservation_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("120-645", "full").content.evidence,
        )

        self.assertNotEqual(preservation.state, EvidenceState.CONTRADICTED)

    def test_separator_gap_inside_sequence_is_not_external_undercrop(self) -> None:
        coverage = PhotoSequenceCoverageEvidence(
            holder_long_axis_interval=(0, 310),
            photo_sequence_interval=(0, 310),
            photo_aperture_intervals=((0, 150), (160, 310)),
            content_runs=((25, 285),),
        )

        self.assertEqual(coverage.state, EvidenceState.SUPPORTED)
        self.assertEqual(coverage.uncovered_content, ())

    def test_overlapping_photo_apertures_are_valid_sequence_coverage(self) -> None:
        coverage = PhotoSequenceCoverageEvidence(
            holder_long_axis_interval=(0, 310),
            photo_sequence_interval=(0, 310),
            photo_aperture_intervals=((0, 160), (150, 310)),
            content_runs=((25, 285),),
        )

        self.assertEqual(coverage.state, EvidenceState.SUPPORTED)


if __name__ == "__main__":
    unittest.main()
