from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import unittest
from typing import get_type_hints

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.evidence.holder_boundary import HolderBoundaryEvidence
from x5crop.detection.evidence.photo_scale import (
    PhotoScaleObservation,
    PhotoScaleSource,
    photo_scale_observations,
    photo_scale_observations_match_geometry,
)
from x5crop.domain import (
    BoundarySide,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoApertureEdgeSource,
)


def _holder_boundary(
    textured_inner_sides: frozenset[BoundarySide],
) -> HolderBoundaryEvidence:
    base = candidate_fixture().assessment.evidence.holder_boundary
    boundaries = []
    for boundary in base.boundaries:
        textured = boundary.side in textured_inner_sides
        supporting_paths = tuple(
            (
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
            for path in boundary.supporting_paths
        )
        boundaries.append(replace(boundary, supporting_paths=supporting_paths))
    return HolderBoundaryEvidence(tuple(boundaries), 1.0)


class PhotoScaleEvidenceTests(unittest.TestCase):
    def test_photo_scale_sources_name_measurements_not_uncomputed_consensus(
        self,
    ) -> None:
        self.assertIn("APERTURE_DIMENSION_INTERVAL", PhotoScaleSource.__members__)
        self.assertNotIn("APERTURE_DIMENSION_CONSENSUS", PhotoScaleSource.__members__)

    def test_scale_model_has_no_material_identity_branch(self) -> None:
        source = inspect.getsource(photo_scale_observations)
        self.assertNotIn("FILM_BASE", source)
        self.assertNotIn("ApertureContact", source)

    def test_scale_observation_carries_typed_provenance(self) -> None:
        self.assertIs(
            get_type_hints(PhotoScaleObservation)["provenance"],
            MeasurementProvenance,
        )

    def test_scale_source_cannot_disagree_with_measurement_root(self) -> None:
        with self.assertRaises(ValueError):
            PhotoScaleObservation(
                "x",
                1.0,
                1.0,
                PhotoScaleSource.APERTURE_DIMENSION_INTERVAL,
                MeasurementProvenance(
                    MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                    ObservationId("wrong_root"),
                    (),
                    "wrong root fixture",
                ),
            )

    def test_scale_bounds_match_their_physical_source(self) -> None:
        with self.assertRaises(ValueError):
            PhotoScaleObservation(
                "y",
                10.0,
                10.0,
                PhotoScaleSource.SHORT_AXIS_LOWER_BOUND,
                MeasurementProvenance(
                    MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                    ObservationId("invalid_exact_short_axis"),
                    (),
                    "invalid exact short-axis scale",
                ),
            )
        with self.assertRaises(ValueError):
            PhotoScaleObservation(
                "x",
                10.0,
                None,
                PhotoScaleSource.APERTURE_DIMENSION_INTERVAL,
                MeasurementProvenance(
                    MeasurementIdentity.PHOTO_EDGES,
                    ObservationId("invalid_unbounded_dimension_consensus"),
                    (),
                    "invalid unbounded dimension consensus",
                ),
            )

    def test_two_textured_inner_edges_produce_short_axis_lower_bound(self) -> None:
        geometry = candidate_fixture().geometry
        observations = photo_scale_observations(
            geometry,
            _holder_boundary(frozenset({BoundarySide.TOP, BoundarySide.BOTTOM})),
        )
        short_axis = next(
            item
            for item in observations
            if item.source == PhotoScaleSource.SHORT_AXIS_LOWER_BOUND
        )
        self.assertEqual(short_axis.axis, "y")
        self.assertEqual(short_axis.minimum_px_per_mm, 100.0 / 24.0)
        self.assertIsNone(short_axis.maximum_px_per_mm)

    def test_incomplete_texture_support_does_not_invent_short_axis_scale(self) -> None:
        for sides in (frozenset(), frozenset({BoundarySide.TOP})):
            with self.subTest(sides=sides):
                observations = photo_scale_observations(
                    candidate_fixture().geometry,
                    _holder_boundary(sides),
                )
                self.assertFalse(
                    any(
                        item.source == PhotoScaleSource.SHORT_AXIS_LOWER_BOUND
                        for item in observations
                    )
                )

    def test_candidate_scale_identity_ignores_description_text(self) -> None:
        candidate = candidate_fixture()
        evidence = candidate.assessment.evidence
        renamed = tuple(
            replace(
                observation,
                provenance=replace(
                    observation.provenance,
                    description=f"description_{index}",
                ),
            )
            for index, observation in enumerate(
                evidence.photo_scale_observations,
                start=1,
            )
        )
        self.assertTrue(
            photo_scale_observations_match_geometry(
                candidate.geometry,
                evidence.holder_boundary,
                renamed,
            )
        )

    def test_two_independent_apertures_produce_long_axis_consensus(self) -> None:
        candidate = candidate_fixture()
        observations = photo_scale_observations(
            candidate.geometry,
            candidate.assessment.evidence.holder_boundary,
        )
        long_axis = tuple(
            item
            for item in observations
            if item.source
            == PhotoScaleSource.APERTURE_DIMENSION_INTERVAL
        )
        self.assertEqual(len(long_axis), 2)

    def test_one_independent_aperture_is_not_dimension_consensus(self) -> None:
        candidate = candidate_fixture()
        geometry = candidate.geometry
        provenance = MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            ObservationId("unobserved_second_photo_edge"),
            (MeasurementIdentity.FRAME_DIMENSIONS,),
            "unobserved second photo edge",
        )
        second = replace(
            geometry.photo_apertures[1],
            trailing=replace(
                geometry.photo_apertures[1].trailing,
                state=EvidenceState.UNAVAILABLE,
                source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
                provenance=provenance,
            ),
        )
        provisional = replace(
            geometry,
            photo_apertures=(geometry.photo_apertures[0], second),
            aperture_edge_assignments=tuple(
                assignment
                for assignment in geometry.aperture_edge_assignments
                if assignment.resolution != geometry.photo_apertures[1].trailing
            ),
        )
        observations = photo_scale_observations(
            provisional,
            candidate.assessment.evidence.holder_boundary,
        )
        self.assertFalse(
            any(
                item.source
                == PhotoScaleSource.APERTURE_DIMENSION_INTERVAL
                for item in observations
            )
        )

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
