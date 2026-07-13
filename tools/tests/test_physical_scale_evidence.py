from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import unittest
from typing import get_type_hints

from tools.tests.physical_gate_support import candidate_boundary_paths, candidate_fixture
from x5crop.detection.evidence.holder_boundary import HolderBoundaryEvidence
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.detection.evidence.physical_scale import (
    boundary_scale_observations,
    candidate_scan_calibration,
    candidate_scale_observations_match_geometry,
    physical_scale_observations,
)
from x5crop.domain import (
    BoundaryPathGroup,
    BoundaryPathSource,
    BoundarySide,
    MeasurementIdentity,
    MeasurementProvenance,
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
    textured_inner_sides: frozenset[BoundarySide] = frozenset(),
) -> HolderBoundaryEvidence:
    paths = tuple(
        replace(
            path,
            inner_appearance=(
                replace(path.inner_appearance, texture_median=2.0)
                if path.side in textured_inner_sides
                and path.inner_appearance is not None
                else path.inner_appearance
            ),
        )
        for path in candidate_boundary_paths()
    )
    return HolderBoundaryEvidence(paths, 1.0)


class PhysicalScaleEvidenceTests(unittest.TestCase):
    def test_scale_model_has_no_film_base_identity_or_upper_bound_branch(self) -> None:
        source = inspect.getsource(physical_scale_observations)
        self.assertNotIn("FILM_BASE", source)
        self.assertNotIn("ApertureContact", source)

    def test_active_scale_model_uses_supported_not_legacy_trusted_identity(self) -> None:
        root = Path(__file__).resolve().parents[2] / "x5crop"
        offenders = [
            path.relative_to(root.parent).as_posix()
            for path in root.rglob("*.py")
            if "trusted calibration" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_scale_observation_carries_typed_measurement_provenance(self) -> None:
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

    def test_two_textured_inner_edges_produce_only_a_short_axis_lower_bound(self) -> None:
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

    def test_low_texture_inner_edges_do_not_invent_physical_scale(self) -> None:
        observations = physical_scale_observations(
            candidate_fixture().geometry,
            _holder_boundary(),
        )
        self.assertFalse(
            any(
                item.source == PhysicalScaleSource.FRAME_SHORT_AXIS
                for item in observations
            )
        )

    def test_one_textured_inner_edge_is_not_a_short_axis_measurement(self) -> None:
        observations = physical_scale_observations(
            candidate_fixture().geometry,
            _holder_boundary(frozenset({BoundarySide.TOP})),
        )
        self.assertFalse(
            any(
                item.source == PhysicalScaleSource.FRAME_SHORT_AXIS
                for item in observations
            )
        )

    def test_boundary_scale_precedes_candidate_geometry(self) -> None:
        holder_boundary = _holder_boundary(
            frozenset({BoundarySide.TOP, BoundarySide.BOTTOM})
        )
        observations = boundary_scale_observations(
            (
                BoundaryPathGroup(
                    BoundaryPathSource.HOLDER_BOUNDARY,
                    holder_boundary.paths,
                ),
            ),
            format_spec("135"),
            "horizontal",
            edge_texture_limit=1.0,
        )
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].axis, "y")
        self.assertEqual(observations[0].minimum_px_per_mm, 100.0 / 24.0)
        self.assertIsNone(observations[0].maximum_px_per_mm)

    def test_candidate_calibration_preserves_root_scale_observations(self) -> None:
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
        context_calibration = ScanCalibrationResolution.from_observations(
            ResolutionMetadataObservation(10.0, 10.0),
            (root,),
        )
        candidate = candidate_scan_calibration(
            context_calibration,
            candidate_fixture().geometry,
            _holder_boundary(),
        )
        self.assertIn(root, candidate.physical_observations)
        self.assertIn(
            "tiff_resolution_contradicted_by_physical_scale",
            candidate.y.diagnostics,
        )

    def test_candidate_scale_observations_remain_bound_to_geometry(self) -> None:
        candidate = candidate_fixture()
        evidence = candidate.assessment.evidence
        calibration = candidate_scan_calibration(
            ScanCalibrationResolution.from_observations(
                ResolutionMetadataObservation(None, None),
                (),
            ),
            candidate.geometry,
            evidence.holder_boundary,
        )
        first = calibration.physical_observations[0]
        forged = ScanCalibrationResolution.from_observations(
            calibration.metadata,
            (
                replace(
                    first,
                    minimum_px_per_mm=(first.minimum_px_per_mm or 0.0) + 1.0,
                    maximum_px_per_mm=(first.maximum_px_per_mm or 0.0) + 1.0,
                ),
                *calibration.physical_observations[1:],
            ),
        )
        with self.assertRaises(ValueError):
            replace(
                candidate,
                assessment=replace(
                    candidate.assessment,
                    evidence=replace(evidence, scan_calibration=forged),
                ),
            )

    def test_candidate_scale_identity_ignores_provenance_description_text(self) -> None:
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

    def test_independent_photo_intervals_produce_bounded_long_axis_scale(self) -> None:
        candidate = candidate_fixture()
        observations = physical_scale_observations(
            candidate.geometry,
            candidate.assessment.evidence.holder_boundary,
        )
        long_axis = next(
            item
            for item in observations
            if item.source == PhysicalScaleSource.FRAME_DIMENSION_CONSENSUS
        )
        self.assertEqual(long_axis.axis, "x")
        self.assertEqual(long_axis.minimum_px_per_mm, 95.0 / 36.0)
        self.assertEqual(long_axis.maximum_px_per_mm, 95.0 / 36.0)

    def test_one_independent_photo_interval_is_not_dimension_consensus(self) -> None:
        candidate = candidate_fixture()
        first, second = candidate.geometry.photo_intervals
        generated = MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            "synthetic_unobserved_trailing_edge",
            (MeasurementIdentity.SEQUENCE_CUTS,),
        )
        geometry = replace(
            candidate.geometry,
            photo_intervals=(
                first,
                replace(
                    second,
                    end_provenance=generated,
                    end_independently_observed=False,
                ),
            ),
        )
        observations = physical_scale_observations(
            geometry,
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
            visible_sequence_span=geometry.visible_sequence_span,
            frames=geometry.frames,
            frame_boundaries=geometry.frame_boundaries,
            separator_assignments=geometry.separator_assignments,
            physical_spec=format_spec("135"),
            content_support_available=evidence.frame_content.support_available,
            frame_coverage=evidence.frame_coverage,
            frame_dimensions=evidence.frame_dimensions,
            calibration=calibration,
        )
        self.assertFalse(calibration.fully_supported)
        self.assertEqual(occupancy.long_axis_px_per_mm, 10.0)


if __name__ == "__main__":
    unittest.main()
