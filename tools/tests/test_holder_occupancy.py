from __future__ import annotations

from dataclasses import fields
from inspect import signature
import unittest

from tools.tests.physical_gate_support import (
    boundary_path_fixture,
    candidate_boundary_paths,
    separator_cross_axis_measurement,
    separator_observation,
    unavailable_calibration_fixture,
)
from x5crop.detection.evidence.photo_aperture_coverage import (
    PhotoApertureCoverageEvidence,
)
from x5crop.detection.evidence.content.photo_content import (
    PhotoContentEvidence,
    PhotoContentObservation,
)
from x5crop.detection.evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    holder_occupancy_evidence,
)
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    PhotoSequenceSolution,
    SequenceResiduals,
)
from x5crop.detection.physical.photo_size import frame_dimension_evidence
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
    PhotoApertureCrossAxisHypothesis,
    PhotoApertureEdgeAssignment,
    PhotoApertureEdgeSource,
    PixelInterval,
    SeparatorBandAssignment,
    SeparatorWidthConstraint,
)
from x5crop.formats import format_spec


def _underfilled_geometry() -> PhotoSequenceSolution:
    observations = (
        separator_observation(140.0, start=135.0, end=145.0),
        separator_observation(250.0, start=245.0, end=255.0),
    )
    paths = candidate_boundary_paths()
    cross_axis = PhotoApertureCrossAxisHypothesis(paths[2], paths[3])

    def edge(
        photo_index: int,
        side: BoundarySide,
        position: float,
        *,
        separator_index: int | None = None,
    ) -> PhotoApertureBoundaryResolution:
        observation = (
            None if separator_index is None else observations[separator_index]
        )
        provenance = (
            MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(
                    f"synthetic_underfilled_aperture:{photo_index}:{side.value}"
                ),
                (MeasurementIdentity.GRAY_WORK,),
                "synthetic underfilled aperture edge",
            )
            if observation is None
            else observation.provenance
        )
        return PhotoApertureBoundaryResolution(
            photo_index,
            side,
            PixelInterval.exact(position),
            EvidenceState.SUPPORTED,
            (
                PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
                if observation is None
                else PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE
            ),
            provenance,
        )

    apertures = (
        PhotoAperture(
            1,
            edge(1, BoundarySide.LEADING, 30.0),
            edge(1, BoundarySide.TRAILING, 135.0, separator_index=0),
            edge(1, BoundarySide.TOP, 0.0),
            edge(1, BoundarySide.BOTTOM, 100.0),
        ),
        PhotoAperture(
            2,
            edge(2, BoundarySide.LEADING, 145.0, separator_index=0),
            edge(2, BoundarySide.TRAILING, 245.0, separator_index=1),
            edge(2, BoundarySide.TOP, 0.0),
            edge(2, BoundarySide.BOTTOM, 100.0),
        ),
        PhotoAperture(
            3,
            edge(3, BoundarySide.LEADING, 255.0, separator_index=1),
            edge(3, BoundarySide.TRAILING, 360.0),
            edge(3, BoundarySide.TOP, 0.0),
            edge(3, BoundarySide.BOTTOM, 100.0),
        ),
    )
    assignments = tuple(
        SeparatorBandAssignment(
            index,
            observation,
            separator_cross_axis_measurement(observation, cross_axis),
            apertures[index - 1].trailing,
            apertures[index].leading,
            SeparatorWidthConstraint(PixelInterval.exact(100.0)),
        )
        for index, observation in enumerate(observations, start=1)
    )
    spacings = tuple(
        InterPhotoSpacing(
            InterPhotoBoundaryReference(None, index),
            PixelInterval.exact(observation.width),
            observation.provenance,
            InterPhotoSpacingBasis.OBSERVED,
        )
        for index, observation in enumerate(observations, start=1)
    )
    measured_edges = tuple(
        boundary
        for aperture in apertures
        for boundary in (
            aperture.leading,
            aperture.trailing,
            aperture.top,
            aperture.bottom,
        )
        if boundary.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
    )
    raw_paths = tuple(
        boundary_path_fixture(
            boundary.side,
            boundary.position,
            BoundaryKind.TONAL_TRANSITION,
            boundary.provenance,
        )
        for boundary in measured_edges
    )
    edge_assignments = tuple(
        PhotoApertureEdgeAssignment(
            boundary.photo_index,
            boundary.side,
            path,
            boundary,
        )
        for boundary, path in zip(measured_edges, raw_paths, strict=True)
    )
    return PhotoSequenceSolution(
        format_id="120-66",
        layout="horizontal",
        strip_mode="partial",
        count=3,
        holder_span=HolderSpan(Box(0, 0, 400, 100)),
        photo_apertures=apertures,
        aperture_edge_assignments=edge_assignments,
        separator_observations=observations,
        separator_assignments=assignments,
        inter_photo_spacings=spacings,
        frame_dimension_prior=FrameDimensionPrior(
            (56.0, 56.0),
            FrameDimensionPriorSource.PHYSICAL_ASPECT,
            MeasurementProvenance(
                MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                ObservationId("synthetic_square_prior"),
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                "synthetic square prior",
            ),
        ),
        photo_width_constraint_px=PixelInterval.exact(100.0),
        photo_height_constraint_px=PixelInterval.exact(100.0),
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


def _evidence(geometry: PhotoSequenceSolution):
    coverage = PhotoApertureCoverageEvidence(
        holder_long_axis_interval=(0, 400),
        photo_aperture_intervals=((30, 135), (145, 245), (255, 360)),
        content_runs=((40, 125), (155, 235), (265, 350)),
        content_position_uncertainty_px=0,
    )
    dimensions = frame_dimension_evidence(
        geometry,
        unavailable_calibration_fixture(),
    )
    content = PhotoContentEvidence(
        0.5,
        tuple(
            PhotoContentObservation(index, 0.8, 0.8, True, ())
            for index in range(1, 4)
        ),
    )
    return coverage, dimensions, content


class HolderOccupancyTests(unittest.TestCase):
    def test_occupancy_measurement_does_not_accept_user_strip_mode(self) -> None:
        self.assertNotIn("strip_mode", signature(holder_occupancy_evidence).parameters)

    def test_occupancy_has_no_unreachable_long_axis_calibration_surface(self) -> None:
        self.assertNotIn("calibration", signature(holder_occupancy_evidence).parameters)
        self.assertTrue(
            {
                "long_axis_px_per_mm",
                "leading_slack_mm",
                "trailing_slack_mm",
                "calibration_used",
            }.isdisjoint(field.name for field in fields(HolderOccupancyEvidence))
        )

    def test_medium_square_partial_can_be_complete_underfilled(self) -> None:
        geometry = _underfilled_geometry()
        coverage, dimensions, _ = _evidence(geometry)
        occupancy = holder_occupancy_evidence(
            count=geometry.count,
            holder_span=geometry.holder_span,
            photo_apertures=geometry.photo_apertures,
            separator_assignments=geometry.separator_assignments,
            physical_spec=format_spec("120-66"),
            content_support_available=True,
            photo_aperture_coverage=coverage,
            frame_dimensions=dimensions,
        )
        self.assertTrue(occupancy.underfilled)
        self.assertTrue(occupancy.complete_underfilled_strip)

    def test_underfilled_state_uses_normal_partial_edge_evidence(self) -> None:
        geometry = _underfilled_geometry()
        coverage, dimensions, content = _evidence(geometry)
        partial = partial_edge_safety_evidence(
            geometry,
            coverage,
            dimensions,
            content,
        )
        self.assertEqual(partial.state, EvidenceState.SUPPORTED)

    def test_non_underfilled_format_does_not_gain_occupancy_exemption(self) -> None:
        geometry = _underfilled_geometry()
        coverage, dimensions, _ = _evidence(geometry)
        occupancy = holder_occupancy_evidence(
            count=geometry.count,
            holder_span=geometry.holder_span,
            photo_apertures=geometry.photo_apertures,
            separator_assignments=geometry.separator_assignments,
            physical_spec=format_spec("135"),
            content_support_available=True,
            photo_aperture_coverage=coverage,
            frame_dimensions=dimensions,
        )
        self.assertFalse(occupancy.complete_underfilled_strip)


if __name__ == "__main__":
    unittest.main()
