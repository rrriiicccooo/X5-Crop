from __future__ import annotations

from dataclasses import replace
from typing import get_type_hints
import unittest

import numpy as np

from tools.tests.physical_gate_support import (
    boundary_path_fixture,
    candidate_evidence_fixture,
    candidate_fixture,
)
from x5crop.cache import MeasurementCache
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.candidate.assessment.model import (
    BoundaryProofPath,
    CandidateGateInput,
)
from x5crop.detection.candidate.model import content_preservation_state
from x5crop.detection.evidence.content.external_boundaries import (
    external_aperture_preservation_evidence,
)
from x5crop.detection.evidence.photo_aperture_coverage import (
    PhotoApertureCoverageEvidence,
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
    BoundaryKind,
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
    ObservationId,
    PhotoAperture,
    PhotoApertureBoundaryResolution,
    PhotoApertureEdgeAssignment,
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
    def edge(side: BoundarySide, position: float):
        provenance = MeasurementProvenance(
            (
                MeasurementIdentity.PHOTO_EDGES
                if measured_boundaries
                else MeasurementIdentity.FRAME_GEOMETRY
            ),
            ObservationId(f"synthetic_single_aperture:{side.value}"),
            (
                (MeasurementIdentity.GRAY_WORK,)
                if measured_boundaries
                else (MeasurementIdentity.FRAME_DIMENSIONS,)
            ),
            (
                "synthetic single-aperture measurement"
                if measured_boundaries
                else "synthetic single-aperture dimension hypothesis"
            ),
        )
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
    boundaries = (
        aperture.leading,
        aperture.trailing,
        aperture.top,
        aperture.bottom,
    )
    raw_paths = (
        tuple(
            boundary_path_fixture(
                boundary.side,
                boundary.position,
                BoundaryKind.TONAL_TRANSITION,
                boundary.provenance,
            )
            for boundary in boundaries
        )
        if measured_boundaries
        else ()
    )
    edge_assignments = (
        tuple(
            PhotoApertureEdgeAssignment(
                1,
                boundary.side,
                path,
                boundary,
            )
            for boundary, path in zip(boundaries, raw_paths, strict=True)
        )
        if measured_boundaries
        else ()
    )
    return PhotoSequenceSolution(
        format_id="120-645",
        layout="horizontal",
        strip_mode="full",
        count=1,
        holder_span=HolderSpan(box),
        photo_apertures=(aperture,),
        aperture_edge_assignments=edge_assignments,
        separator_observations=(),
        separator_assignments=(),
        inter_photo_spacings=(),
        frame_dimension_prior=FrameDimensionPrior(
            (42.0, 56.0),
            FrameDimensionPriorSource.PHYSICAL_ASPECT,
            MeasurementProvenance(
                MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                ObservationId("synthetic_frame_prior"),
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                "synthetic physical frame prior",
            ),
        ),
        photo_width_constraint_px=PixelInterval.exact(float(box.width)),
        photo_height_constraint_px=PixelInterval.exact(float(box.height)),
        residuals=SequenceResiduals(0.0, 0.0),
        assignment_consensus=BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.UNCONTESTED,
            1,
            (),
        ),
        search_budget_exhausted=False,
        raw_boundary_paths=raw_paths,
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
                ObservationId(f"synthetic_photo_{photo_index}_{side.value}"),
                (MeasurementIdentity.GRAY_WORK,),
                "synthetic measured aperture edge",
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
    def test_photo_content_uses_canonical_photo_and_boundary_identities(self) -> None:
        annotations = get_type_hints(PhotoContentObservation)

        self.assertIn("photo_index", annotations)
        self.assertNotIn("index", annotations)
        self.assertEqual(
            annotations["boundary_contact_sides"],
            tuple[BoundarySide, ...],
        )

    def test_internal_content_crossing_requires_physical_spacing_evidence(self) -> None:
        geometry = candidate_fixture().geometry
        crossing = PhotoContentEvidence(
            0.5,
            (
                PhotoContentObservation(
                    1,
                    0.8,
                    0.8,
                    True,
                    (BoundarySide.TRAILING,),
                ),
                PhotoContentObservation(
                    2,
                    0.8,
                    0.8,
                    True,
                    (BoundarySide.LEADING,),
                ),
            ),
        )
        boundary = InterPhotoBoundaryReference(None, 1)
        provenance = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("synthetic_spacing"),
            (MeasurementIdentity.GRAY_WORK,),
            "synthetic inter-photo spacing",
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

    def test_description_text_cannot_create_independent_overlap_evidence(self) -> None:
        geometry = candidate_fixture().geometry
        crossing = PhotoContentEvidence(
            0.5,
            (
                PhotoContentObservation(
                    1,
                    0.8,
                    0.8,
                    True,
                    (BoundarySide.TRAILING,),
                ),
                PhotoContentObservation(
                    2,
                    0.8,
                    0.8,
                    True,
                    (BoundarySide.LEADING,),
                ),
            ),
        )
        apertures = _measured_apertures_for_spacing(-5.0)
        shared = ObservationId("shared_boundary_observation")
        first = replace(
            apertures[0],
            trailing=replace(
                apertures[0].trailing,
                provenance=replace(
                    apertures[0].trailing.provenance,
                    observation_id=shared,
                    description="left description",
                ),
            ),
        )
        second = replace(
            apertures[1],
            leading=replace(
                apertures[1].leading,
                provenance=replace(
                    apertures[1].leading.provenance,
                    observation_id=shared,
                    description="right description",
                ),
            ),
        )
        spacing = replace(
            geometry.inter_photo_spacings[0],
            signed_width_px=PixelInterval.exact(-5.0),
            basis=InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS,
        )

        evidence = inter_photo_boundary_preservation_evidence(
            2,
            (first, second),
            (spacing,),
            crossing,
        )

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)

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
                evidence.photo_aperture_coverage,
                evidence.inter_photo_boundary_preservation,
                crossing,
                evidence.partial_edge_safety,
            ),
            EvidenceState.CONTRADICTED,
        )

    def test_external_preservation_keeps_each_photo_cross_axis_edges(self) -> None:
        geometry = candidate_fixture().geometry
        preservation = external_aperture_preservation_evidence(
            geometry,
            _cache(np.full((100, 310), 255, dtype=np.uint8)),
            get_detection_configuration("135", "full").content.evidence,
        )

        self.assertEqual(
            tuple(
                (item.photo_index, item.side)
                for item in preservation.observations
            ),
            (
                (1, BoundarySide.LEADING),
                (1, BoundarySide.TOP),
                (1, BoundarySide.BOTTOM),
                (2, BoundarySide.TOP),
                (2, BoundarySide.BOTTOM),
                (2, BoundarySide.TRAILING),
            ),
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

    def test_measured_aperture_content_conflict_blocks_candidate_gate(self) -> None:
        gray = np.full((120, 900), 255, dtype=np.uint8)
        gray[20:100, 50:850] = 0
        geometry = _single_aperture_geometry(Box(250, 0, 650, 120))

        preservation = external_aperture_preservation_evidence(
            geometry,
            _cache(gray),
            get_detection_configuration("120-645", "full").content.evidence,
        )

        self.assertEqual(preservation.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            preservation.reason,
            "visible_content_crosses_external_aperture",
        )
        evidence = candidate_evidence_fixture()
        preservation_state = content_preservation_state(
            evidence.photo_aperture_coverage,
            evidence.inter_photo_boundary_preservation,
            preservation,
            evidence.partial_edge_safety,
        )
        self.assertEqual(preservation_state, EvidenceState.CONTRADICTED)
        gate = candidate_gate_assessment(
            CandidateGateInput(
                content_preservation=preservation_state,
                photo_geometry=EvidenceState.SUPPORTED,
                evidence_independence=EvidenceState.SUPPORTED,
                proof_paths=(
                    BoundaryProofPath(
                        "separator_sequence_led",
                        EvidenceState.SUPPORTED,
                        ("synthetic_separator_sequence",),
                    ),
                    BoundaryProofPath(
                        "geometry_led",
                        EvidenceState.UNAVAILABLE,
                        ("synthetic_photo_dimensions",),
                    ),
                    BoundaryProofPath(
                        "partial_occupancy_led",
                        EvidenceState.NOT_APPLICABLE,
                        ("synthetic_full_strip",),
                    ),
                ),
            )
        )
        self.assertFalse(gate.passed)
        self.assertEqual(gate.failed_checks, ("content_preservation",))
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

    def test_content_run_smoothing_uncertainty_can_span_a_separator(self) -> None:
        coverage = PhotoApertureCoverageEvidence(
            holder_long_axis_interval=(0, 310),
            photo_aperture_intervals=((0, 150), (160, 310)),
            content_runs=((25, 285),),
            content_position_uncertainty_px=5,
        )

        self.assertEqual(coverage.state, EvidenceState.SUPPORTED)
        self.assertEqual(coverage.uncovered_content, ())

    def test_content_between_apertures_is_not_covered_by_their_outer_envelope(
        self,
    ) -> None:
        coverage = PhotoApertureCoverageEvidence(
            holder_long_axis_interval=(0, 1000),
            photo_aperture_intervals=((0, 100), (900, 1000)),
            content_runs=((200, 800),),
            content_position_uncertainty_px=5,
        )

        self.assertEqual(coverage.state, EvidenceState.CONTRADICTED)
        self.assertEqual(coverage.uncovered_content, ((200, 800),))

    def test_overlapping_photo_apertures_are_valid_sequence_coverage(self) -> None:
        coverage = PhotoApertureCoverageEvidence(
            holder_long_axis_interval=(0, 310),
            photo_aperture_intervals=((0, 160), (150, 310)),
            content_runs=((25, 285),),
            content_position_uncertainty_px=0,
        )

        self.assertEqual(coverage.state, EvidenceState.SUPPORTED)


if __name__ == "__main__":
    unittest.main()
