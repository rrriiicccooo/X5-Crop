from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    holder_occlusion_not_applicable,
    separator_observation,
)
from x5crop.detection.physical.boundary import (
    HolderOcclusionSideOutcome,
    holder_occlusion_for_sequence,
)
from x5crop.detection.physical.sequence_solver import solve_frame_sequence
from x5crop.detection.physical.spacing import (
    CorroboratedSpacingEvidence,
    SpacingHypothesis,
    corroborate_single_missing_overlap,
    observed_spacing_evidence,
    spacing_hypothesis,
)
from x5crop.domain import (
    BoundaryKind,
    BoundaryObservation,
    BoundarySide,
    Box,
    EvidenceState,
    FrameBoundaryReference,
    FrameDimensionPrior,
    FrameDimensionPriorSource,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
    VisibleSequenceSpan,
)


class SequenceSolverIntegrityContractTest(unittest.TestCase):
    def test_runtime_sequence_order_can_corroborate_one_missing_overlap(
        self,
    ) -> None:
        edge_provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            "synthetic",
            (MeasurementIdentity.GRAY_WORK,),
        )
        boundaries = (
            BoundaryObservation(
                BoundarySide.LEADING,
                PixelInterval.exact(0.0),
                BoundaryKind.TONAL_TRANSITION,
                edge_provenance,
            ),
            BoundaryObservation(
                BoundarySide.TRAILING,
                PixelInterval.exact(290.0),
                BoundaryKind.TONAL_TRANSITION,
                edge_provenance,
            ),
        )
        solved = solve_frame_sequence(
            (separator_observation(97.5, start=95.0, end=100.0),),
            (),
            VisibleSequenceSpan(Box(0, 0, 290, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SCAN_CALIBRATION,
                MeasurementProvenance(
                    MeasurementIdentity.SCAN_CALIBRATION,
                    "synthetic",
                    (MeasurementIdentity.TIFF_RESOLUTION,),
                ),
            ),
            boundaries,
            10_000,
        )

        self.assertIsInstance(
            solved.relations[1],
            CorroboratedSpacingEvidence,
        )

    def test_white_holder_occlusion_expands_sequence_search_without_becoming_evidence(
        self,
    ) -> None:
        edge_provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            "synthetic",
            (MeasurementIdentity.GRAY_WORK,),
        )
        observations = (
            BoundaryObservation(
                BoundarySide.LEADING,
                PixelInterval.exact(0.0),
                BoundaryKind.WHITE_HOLDER_TRANSITION,
                edge_provenance,
            ),
            BoundaryObservation(
                BoundarySide.TRAILING,
                PixelInterval.exact(192.0),
                BoundaryKind.TONAL_TRANSITION,
                edge_provenance,
            ),
        )
        separator = separator_observation(91.0, start=90.0, end=92.0)

        solved = solve_frame_sequence(
            (separator,),
            (),
            VisibleSequenceSpan(Box(0, 0, 192, 100)),
            2,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SCAN_CALIBRATION,
                MeasurementProvenance(
                    MeasurementIdentity.SCAN_CALIBRATION,
                    "synthetic",
                    (MeasurementIdentity.TIFF_RESOLUTION,),
                ),
            ),
            observations,
            10_000,
        )

        self.assertTrue(solved.assignments[0].independent)
        self.assertEqual(
            solved.holder_occlusion.leading.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            solved.holder_occlusion.leading.hidden_width_px,
            PixelInterval.exact(10.0),
        )

    def test_impossible_overlap_cannot_be_corroborated(self) -> None:
        provenance = MeasurementProvenance(
            MeasurementIdentity.SEPARATOR_PROFILE,
            "synthetic",
            (MeasurementIdentity.GRAY_WORK,),
        )
        spacings = (
            observed_spacing_evidence(
                FrameBoundaryReference(None, 1),
                PixelInterval.exact(10.0),
                provenance,
            ),
            spacing_hypothesis(
                FrameBoundaryReference(None, 2),
                PixelInterval(-100.0, 100.0),
                provenance,
            ),
        )
        edge_observations = (
            BoundaryObservation(
                BoundarySide.LEADING,
                PixelInterval.exact(0.0),
                BoundaryKind.TONAL_TRANSITION,
                provenance,
            ),
            BoundaryObservation(
                BoundarySide.TRAILING,
                PixelInterval.exact(100.0),
                BoundaryKind.TONAL_TRANSITION,
                provenance,
            ),
        )

        result = corroborate_single_missing_overlap(
            visible_length_px=PixelInterval.exact(100.0),
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=spacings,
            holder_occlusion=holder_occlusion_not_applicable(),
            boundary_observations=edge_observations,
            dimension_source=FrameDimensionPriorSource.SCAN_CALIBRATION,
        )

        self.assertIsInstance(result[1], SpacingHypothesis)

    def test_sequence_solution_rejects_cross_field_geometry_drift(self) -> None:
        geometry = candidate_fixture().geometry
        original_assignment = geometry.separator_assignments[0]
        replacement_assignment = replace(
            original_assignment,
            position_constraint=replace(
                original_assignment.position_constraint,
                position=PixelInterval(
                    original_assignment.position_constraint.position.minimum - 1.0,
                    original_assignment.position_constraint.position.maximum + 1.0,
                ),
            ),
        )
        invalid_geometries = (
            lambda: replace(
                geometry.separator_assignments[0],
                position_constraint=replace(
                    geometry.separator_assignments[0].position_constraint,
                    boundary_index=2,
                ),
            ),
            lambda: replace(
                geometry,
                frames=(
                    geometry.frames[0],
                    replace(geometry.frames[1], left=101),
                ),
            ),
            lambda: replace(
                geometry,
                photo_intervals=(
                    geometry.photo_intervals[0],
                    replace(geometry.photo_intervals[1], index=3),
                ),
            ),
            lambda: replace(
                geometry,
                frame_boundaries=(
                    replace(
                        geometry.frame_boundaries[0],
                        assignment=replacement_assignment,
                    ),
                ),
            ),
            lambda: replace(
                geometry,
                inter_frame_spacings=(
                    replace(
                        geometry.inter_frame_spacings[0],
                        boundary=FrameBoundaryReference(None, 2),
                    ),
                ),
            ),
        )
        for factory in invalid_geometries:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_holder_occlusion_allocation_has_typed_outcome(self) -> None:
        provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            "synthetic",
            (MeasurementIdentity.GRAY_WORK,),
        )
        boundaries = (
            BoundaryObservation(
                BoundarySide.LEADING,
                PixelInterval.exact(0.0),
                BoundaryKind.WHITE_HOLDER_TRANSITION,
                provenance,
            ),
            BoundaryObservation(
                BoundarySide.TRAILING,
                PixelInterval.exact(80.0),
                BoundaryKind.WHITE_HOLDER_TRANSITION,
                provenance,
            ),
        )
        occlusion = holder_occlusion_for_sequence(
            boundaries,
            VisibleSequenceSpan(Box(0, 0, 80, 100)),
            (),
            PixelInterval.exact(100.0),
        )

        self.assertEqual(
            occlusion.leading.outcome,
            HolderOcclusionSideOutcome.ALLOCATION_UNRESOLVED,
        )
        self.assertEqual(
            occlusion.unallocated_hidden_width_px,
            PixelInterval.exact(20.0),
        )
        self.assertEqual(
            occlusion.combined_hidden_width_px,
            PixelInterval.exact(20.0),
        )


if __name__ == "__main__":
    unittest.main()
