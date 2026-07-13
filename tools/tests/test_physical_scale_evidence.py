from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import unittest
from typing import get_type_hints

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.evidence.holder_boundary import HolderBoundaryEvidence
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.detection.evidence.physical_scale import (
    boundary_scale_observations,
    candidate_scan_calibration,
    candidate_scale_observations_match_geometry,
    physical_scale_observations,
)
from x5crop.domain import (
    BoundaryMeasurementSet,
    BoundarySide,
    ContainmentFallback,
    EvidenceState,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoApertureEdgeSource,
)
from x5crop.formats import format_spec
from x5crop.units import (
    PhysicalScaleObservation,
    PhysicalScaleScope,
    PhysicalScaleSource,
    ResolutionMetadataObservation,
    ScanCalibrationResolution,
)


def _holder_boundary(
    textured_inner_sides: frozenset[BoundarySide],
) -> HolderBoundaryEvidence:
    base = candidate_fixture().assessment.evidence.holder_boundary
    boundaries = []
    for boundary in base.boundaries:
        textured = boundary.side in textured_inner_sides
        path = boundary.path
        path = (
            replace(
                path,
                upper_appearance=replace(
                    path.upper_appearance,
                    texture_median=2.0 if textured else 0.0,
                ),
            )
            if boundary.side in {BoundarySide.LEADING, BoundarySide.TOP}
            else replace(
                path,
                lower_appearance=replace(
                    path.lower_appearance,
                    texture_median=2.0 if textured else 0.0,
                ),
            )
        )
        boundaries.append(replace(boundary, path=path))
    return HolderBoundaryEvidence(tuple(boundaries), 1.0)


class PhysicalScaleEvidenceTests(unittest.TestCase):
    def test_scale_model_has_no_material_identity_branch(self) -> None:
        source = inspect.getsource(physical_scale_observations)
        self.assertNotIn("FILM_BASE", source)
        self.assertNotIn("ApertureContact", source)

    def test_scale_observation_carries_typed_provenance(self) -> None:
        self.assertIs(
            get_type_hints(PhysicalScaleObservation)["scope"],
            PhysicalScaleScope,
        )
        self.assertIs(
            get_type_hints(PhysicalScaleObservation)["provenance"],
            MeasurementProvenance,
        )

    def test_scale_source_cannot_disagree_with_measurement_root(self) -> None:
        with self.assertRaises(ValueError):
            PhysicalScaleObservation(
                "x",
                1.0,
                1.0,
                PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS,
                PhysicalScaleScope.CANDIDATE_GEOMETRY,
                MeasurementProvenance(
                    MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                    "wrong_root",
                    (),
                ),
            )

    def test_two_textured_inner_edges_produce_short_axis_lower_bound(self) -> None:
        geometry = candidate_fixture().geometry
        observations = physical_scale_observations(
            geometry,
            _holder_boundary(frozenset({BoundarySide.TOP, BoundarySide.BOTTOM})),
        )
        short_axis = next(
            item
            for item in observations
            if item.source == PhysicalScaleSource.FRAME_SHORT_AXIS
        )
        self.assertEqual(short_axis.axis, "y")
        self.assertEqual(short_axis.minimum_px_per_mm, 100.0 / 24.0)
        self.assertIsNone(short_axis.maximum_px_per_mm)

    def test_incomplete_texture_support_does_not_invent_short_axis_scale(self) -> None:
        for sides in (frozenset(), frozenset({BoundarySide.TOP})):
            with self.subTest(sides=sides):
                observations = physical_scale_observations(
                    candidate_fixture().geometry,
                    _holder_boundary(sides),
                )
                self.assertFalse(
                    any(
                        item.source == PhysicalScaleSource.FRAME_SHORT_AXIS
                        for item in observations
                    )
                )

    def test_boundary_scale_precedes_candidate_geometry(self) -> None:
        geometry = candidate_fixture().geometry
        holder = _holder_boundary(
            frozenset({BoundarySide.TOP, BoundarySide.BOTTOM})
        )
        measurements = BoundaryMeasurementSet(
            tuple(item.path for item in holder.boundaries),
            holder.boundaries,
            ContainmentFallback(
                geometry.holder_span.box,
                MeasurementProvenance(
                    MeasurementIdentity.HOLDER_CANVAS,
                    "test_containment",
                    (MeasurementIdentity.CANVAS,),
                ),
            ),
        )
        observations = boundary_scale_observations(
            measurements,
            format_spec("135"),
            "horizontal",
            edge_texture_limit=1.0,
        )
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].scope, PhysicalScaleScope.ROOT_MEASUREMENT)
        self.assertIsNone(observations[0].maximum_px_per_mm)

    def test_candidate_calibration_preserves_root_observations(self) -> None:
        root = PhysicalScaleObservation(
            "y",
            80.0,
            None,
            PhysicalScaleSource.FRAME_SHORT_AXIS,
            PhysicalScaleScope.ROOT_MEASUREMENT,
            MeasurementProvenance(
                MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                "root_boundary_scale",
                (MeasurementIdentity.BOUNDARY_PATHS,),
            ),
        )
        context = ScanCalibrationResolution.from_observations(
            ResolutionMetadataObservation(10.0, 10.0),
            (root,),
        )
        candidate = candidate_scan_calibration(
            context,
            candidate_fixture().geometry,
            _holder_boundary(frozenset()),
        )
        self.assertIn(root, candidate.physical_observations)

    def test_candidate_scale_identity_ignores_description_text(self) -> None:
        candidate = candidate_fixture()
        evidence = candidate.assessment.evidence
        renamed = ScanCalibrationResolution.from_observations(
            evidence.scan_calibration.metadata,
            tuple(
                replace(
                    observation,
                    provenance=replace(
                        observation.provenance,
                        source=f"description_{index}",
                    ),
                )
                for index, observation in enumerate(
                    evidence.scan_calibration.physical_observations,
                    start=1,
                )
            ),
        )
        self.assertTrue(
            candidate_scale_observations_match_geometry(
                candidate.geometry,
                evidence.holder_boundary,
                renamed,
            )
        )

    def test_two_independent_apertures_produce_long_axis_consensus(self) -> None:
        candidate = candidate_fixture()
        observations = physical_scale_observations(
            candidate.geometry,
            candidate.assessment.evidence.holder_boundary,
        )
        long_axis = tuple(
            item
            for item in observations
            if item.source == PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS
        )
        self.assertEqual(len(long_axis), 2)
        self.assertTrue(
            all(item.scope == PhysicalScaleScope.CANDIDATE_GEOMETRY for item in long_axis)
        )

    def test_one_independent_aperture_is_not_dimension_consensus(self) -> None:
        candidate = candidate_fixture()
        geometry = candidate.geometry
        provenance = MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            "unobserved_second_photo_edge",
            (MeasurementIdentity.FRAME_DIMENSIONS,),
        )
        second = replace(
            geometry.photo_apertures[1],
            leading=replace(
                geometry.photo_apertures[1].leading,
                state=EvidenceState.UNAVAILABLE,
                source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
                provenance=provenance,
            ),
        )
        provisional = replace(
            geometry,
            photo_apertures=(geometry.photo_apertures[0], second),
            separator_assignments=(),
            inter_photo_spacings=(
                replace(
                    geometry.inter_photo_spacings[0],
                    basis=InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS,
                    provenance=provenance,
                ),
            ),
        )
        observations = physical_scale_observations(
            provisional,
            candidate.assessment.evidence.holder_boundary,
        )
        self.assertFalse(
            any(
                item.source == PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS
                for item in observations
            )
        )

    def test_holder_occupancy_uses_supported_long_axis_independently(self) -> None:
        candidate = candidate_fixture()
        geometry = candidate.geometry
        evidence = candidate.assessment.evidence
        calibration = ScanCalibrationResolution.from_observations(
            ResolutionMetadataObservation(10.0, None),
            (
                PhysicalScaleObservation(
                    "x",
                    10.0,
                    10.0,
                    PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS,
                    PhysicalScaleScope.ROOT_MEASUREMENT,
                    MeasurementProvenance(
                        MeasurementIdentity.PHOTO_EDGES,
                        "long_axis_consensus",
                        (MeasurementIdentity.SEPARATOR_PROFILE,),
                    ),
                ),
            ),
        )
        occupancy = holder_occupancy_evidence(
            layout=geometry.layout,
            count=geometry.count,
            holder_span=geometry.holder_span,
            photo_apertures=geometry.photo_apertures,
            separator_assignments=geometry.separator_assignments,
            physical_spec=format_spec("135"),
            content_support_available=evidence.photo_content.support_available,
            photo_sequence_coverage=evidence.photo_sequence_coverage,
            frame_dimensions=evidence.frame_dimensions,
            calibration=calibration,
        )
        self.assertFalse(calibration.fully_supported)
        self.assertEqual(occupancy.long_axis_px_per_mm, 10.0)

    def test_active_scale_model_has_no_legacy_trust_wording(self) -> None:
        root = Path(__file__).resolve().parents[2] / "x5crop"
        offenders = [
            path.relative_to(root.parent).as_posix()
            for path in root.rglob("*.py")
            if "trusted calibration" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
