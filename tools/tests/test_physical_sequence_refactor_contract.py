from __future__ import annotations

import ast
from dataclasses import replace
from inspect import signature
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    frame_bleed_fixture,
    holder_occlusion_not_applicable,
    selection_fixture,
    separator_constraints,
    separator_observation,
    transform_geometry_fixture,
)
from x5crop.detection.candidate.selection.model import GeometryResolution
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.candidate.model import content_preservation_state
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.content.frame_support import (
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.partial_edge import PartialEdgeSafetyEvidence
from x5crop.detection.evidence.sequence_content_alignment import (
    SequenceContentAlignmentEvidence,
)
from x5crop.detection.physical.boundary import holder_occlusion_for_sequence
from x5crop.detection.physical.boundary import visible_sequence_length_interval
from x5crop.detection.physical.model import BoundaryAssignmentConsensus
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    separator_width_constraint,
)
from x5crop.detection.physical.sequence_solver import solve_frame_sequence
from x5crop.detection.physical.spacing import (
    CorroboratedSpacingEvidence,
    ObservedSpacingEvidence,
    SpacingHypothesis,
    observed_spacing_evidence,
    corroborate_single_missing_overlap,
    sequence_conservation_evidence,
    spacing_hypothesis,
)
from x5crop.domain import (
    BoundaryObservation,
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


class PhysicalSequenceRefactorContractTest(unittest.TestCase):
    def test_not_applicable_assignment_consensus_has_no_solution(self) -> None:
        consensus = BoundaryAssignmentConsensus(
            EvidenceState.NOT_APPLICABLE,
            "review_only_geometry_has_no_assignments",
            0,
            (),
        )
        self.assertEqual(consensus.solution_count, 0)

    def test_observed_spacing_and_geometry_hypothesis_are_distinct_types(
        self,
    ) -> None:
        provenance = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            "test",
            (),
        )
        self.assertIsInstance(
            observed_spacing_evidence(
                FrameBoundaryReference(None, 1),
                PixelInterval.exact(5.0),
                provenance,
            ),
            ObservedSpacingEvidence,
        )
        self.assertIsInstance(
            spacing_hypothesis(
                FrameBoundaryReference(None, 1),
                PixelInterval.exact(-5.0),
                provenance,
            ),
            SpacingHypothesis,
        )

    def test_spacing_kind_is_derived_from_its_signed_interval(self) -> None:
        provenance = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            "test",
            (),
        )
        invalid_factories = (
            lambda: ObservedSpacingEvidence(
                FrameBoundaryReference(None, 1),
                "separator",
                PixelInterval.exact(-5.0),
                provenance,
                "mismatched_observation",
            ),
            lambda: SpacingHypothesis(
                FrameBoundaryReference(None, 1),
                "overlap",
                PixelInterval.exact(5.0),
                provenance,
                "mismatched_hypothesis",
            ),
            lambda: ObservedSpacingEvidence(
                FrameBoundaryReference(None, 1),
                "separator",
                PixelInterval.exact(5.0),
                provenance,
                "",
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_holder_occlusion_builder_uses_the_canonical_inputs(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "x5crop/detection/physical/sequence_solver.py"
        ).read_text(encoding="utf-8")
        calls = tuple(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "holder_occlusion_for_sequence"
        )
        self.assertEqual(len(calls), 2)
        self.assertTrue(
            all(
                len(call.args)
                == len(signature(holder_occlusion_for_sequence).parameters)
                for call in calls
            )
        )

    def test_sequence_solver_callers_supply_the_execution_budget(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "x5crop/detection/candidate/build/sequence_candidate.py"
        ).read_text(encoding="utf-8")
        calls = tuple(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "solve_frame_sequence"
        )
        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(
            {len(call.args) for call in calls},
            {len(signature(solve_frame_sequence).parameters)},
        )

    def test_holder_occlusion_is_measured_after_sequence_resolution(self) -> None:
        build_source = (
            Path(__file__).resolve().parents[2]
            / "x5crop/detection/candidate/build/sequence_candidate.py"
        ).read_text(encoding="utf-8")
        solver_source = (
            Path(__file__).resolve().parents[2]
            / "x5crop/detection/physical/sequence_solver.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(build_source)
        solver_calls = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "solve_frame_sequence"
        )
        self.assertEqual(len(solver_calls), 1)
        self.assertNotIn("holder_occlusion_for_sequence", build_source)
        self.assertNotIn("provisional", solver_source)
        holder_measurement = solver_source.rindex(
            "holder_occlusion_for_sequence("
        )
        self.assertLess(
            solver_source.index("boundaries = representative.boundaries"),
            holder_measurement,
        )
        self.assertLess(
            holder_measurement,
            solver_source.index("relations = _relations("),
        )

    def test_sequence_solver_reports_assignment_budget_exhaustion(self) -> None:
        result = solve_frame_sequence(
            (
                separator_observation(100.0),
                separator_observation(200.0),
            ),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            1,
        )
        self.assertTrue(result.search_budget_exhausted)

    def test_overlapping_separator_bands_cannot_form_negative_photo_extent(
        self,
    ) -> None:
        result = solve_frame_sequence(
            (
                separator_observation(120.0, start=80.0, end=160.0),
                separator_observation(180.0, start=150.0, end=210.0),
            ),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval(50.0, 150.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            10_000,
        )
        self.assertTrue(all(frame.valid() for frame in result.frames))
        self.assertTrue(
            all(interval.width_px.maximum > 0.0 for interval in result.photo_intervals)
        )
        selected = tuple(
            assignment
            for assignment in result.assignments
            if assignment.used_for_boundary
        )
        self.assertFalse(
            len(selected) == 2
            and selected[0].observation.end > selected[1].observation.start
        )

    def test_broad_tonal_band_cannot_become_independent_separator(self) -> None:
        observation = separator_observation(
            325.0,
            start=250.0,
            end=400.0,
        )
        assignment = assign_observation_to_boundary(
            3,
            observation,
            *separator_constraints(
                3,
                PixelInterval(246.0, 404.0),
                PixelInterval(0.0, 50.0),
            ),
        )
        self.assertFalse(assignment.independent)

    def test_band_center_alone_cannot_create_independent_separator(self) -> None:
        observation = separator_observation(
            100.0,
            start=50.0,
            end=150.0,
        )
        assignment = assign_observation_to_boundary(
            1,
            observation,
            *separator_constraints(
                1,
                PixelInterval(90.0, 110.0),
                PixelInterval(0.0, 200.0),
            ),
        )

        self.assertEqual(assignment.state, EvidenceState.UNAVAILABLE)
        self.assertTrue(assignment.geometry_dependent)
        self.assertFalse(assignment.independent)

    def test_cross_axis_contradicted_band_is_not_an_independent_separator(
        self,
    ) -> None:
        observation = separator_observation(
            100.0,
            cross_axis_state=EvidenceState.CONTRADICTED,
        )
        assignment = assign_observation_to_boundary(
            1,
            observation,
            *separator_constraints(1, PixelInterval(90.0, 110.0)),
        )

        self.assertFalse(assignment.independent)

    def test_cross_axis_measurement_has_no_parallel_evidence_owner(self) -> None:
        module = (
            Path(__file__).resolve().parents[2]
            / "x5crop/detection/evidence/separator_continuity.py"
        )
        self.assertFalse(module.exists())

    def test_alternative_supported_separator_cuts_remain_unresolved(self) -> None:
        result = solve_frame_sequence(
            (
                separator_observation(90.0, tonal_evidence=1.0),
                separator_observation(110.0, tonal_evidence=0.5),
            ),
            (),
            VisibleSequenceSpan(Box(0, 0, 200, 100)),
            2,
            FrameDimensionPrior(
                PixelInterval(80.0, 120.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            100,
        )

        self.assertEqual(
            result.assignment_consensus.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            result.assignment_consensus.conflicting_boundary_indexes,
            (1,),
        )

    def test_assignment_disagreement_prevents_geometry_resolution(self) -> None:
        candidate = candidate_fixture()
        candidate = replace(
            candidate,
            geometry=replace(
                candidate.geometry,
                assignment_consensus=BoundaryAssignmentConsensus(
                    EvidenceState.UNAVAILABLE,
                    "alternative_separator_assignments_disagree",
                    2,
                    (1,),
                ),
            ),
        )
        selection = select_candidates(
            (candidate,),
            larger_counts_evaluated=True,
        )

        self.assertFalse(selection.geometry_resolution.supported)
        self.assertIn(
            "separator_assignment_geometry_unresolved",
            selection.geometry_resolution.reasons,
        )

    def test_positive_separator_width_is_not_erased_by_other_overlap(self) -> None:
        constraint = separator_width_constraint(
            VisibleSequenceSpan(Box(0, 0, 270, 100)),
            1,
            3,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            holder_occlusion_not_applicable(),
        )

        self.assertGreaterEqual(constraint.width.maximum, 10.0)

    def test_dimension_constrained_cut_preserves_position_uncertainty(self) -> None:
        result = solve_frame_sequence(
            (),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval(80.0, 120.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            100,
        )

        self.assertTrue(
            all(
                boundary.position.maximum > boundary.position.minimum
                for boundary in result.boundaries
            )
        )
        self.assertEqual(result.photo_intervals[0].end, result.boundaries[0].position)
        self.assertEqual(result.photo_intervals[1].start, result.boundaries[0].position)
        self.assertFalse(result.photo_intervals[0].end_independently_observed)
        self.assertFalse(result.photo_intervals[1].start_independently_observed)

    def test_calibrated_sequence_can_corroborate_one_missing_overlap(self) -> None:
        observations = (
            separator_observation(92.5, start=90.0, end=95.0),
        )
        edge_provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            "synthetic_edges",
            (MeasurementIdentity.GRAY_WORK,),
        )
        result = solve_frame_sequence(
            observations,
            (),
            VisibleSequenceSpan(Box(0, 0, 285, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SCAN_CALIBRATION,
                MeasurementProvenance(
                    MeasurementIdentity.SCAN_CALIBRATION,
                    "synthetic",
                    (
                        MeasurementIdentity.TIFF_RESOLUTION,
                        MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                    ),
                ),
            ),
            (
                BoundaryObservation(
                    "leading",
                    PixelInterval.exact(0.0),
                    "texture_transition",
                    edge_provenance,
                ),
                BoundaryObservation(
                    "trailing",
                    PixelInterval.exact(285.0),
                    "texture_transition",
                    edge_provenance,
                ),
            ),
            100,
        )

        overlap = result.relations[1]
        self.assertIsInstance(overlap, CorroboratedSpacingEvidence)
        self.assertEqual(overlap.kind, "overlap")
        self.assertEqual(overlap.signed_width_px, PixelInterval.exact(-20.0))
        self.assertFalse(overlap.independently_observed)
        self.assertTrue(overlap.supports_output_protection)
        conservation = sequence_conservation_evidence(
            visible_length_px=PixelInterval.exact(285.0),
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=result.relations,
            holder_occlusion=holder_occlusion_not_applicable(),
        )
        self.assertEqual(conservation.state, EvidenceState.UNAVAILABLE)

    def test_uncalibrated_missing_spacing_remains_a_hypothesis(self) -> None:
        result = solve_frame_sequence(
            (separator_observation(92.5, start=90.0, end=95.0),),
            (),
            VisibleSequenceSpan(Box(0, 0, 285, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                    "synthetic",
                    (MeasurementIdentity.SHORT_AXIS_BOUNDARIES,),
                ),
            ),
            (),
            100,
        )

        self.assertIsInstance(result.relations[1], SpacingHypothesis)

    def test_geometry_derived_negative_spacing_is_not_supported_overlap(self) -> None:
        spacing = spacing_hypothesis(
            FrameBoundaryReference(None, 1),
            PixelInterval(-20.0, -10.0),
            MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                "synthetic",
                (MeasurementIdentity.FRAME_DIMENSIONS,),
            ),
        )
        self.assertEqual(spacing.kind, "overlap")
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)

    def test_boundary_uncertainty_prevents_midpoint_only_overlap_support(
        self,
    ) -> None:
        edge_provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            "synthetic",
            (MeasurementIdentity.GRAY_WORK,),
        )
        span = VisibleSequenceSpan(Box(5, 0, 305, 100))
        boundaries = (
            BoundaryObservation(
                "leading",
                PixelInterval(0.0, 10.0),
                "white_holder_transition",
                edge_provenance,
            ),
            BoundaryObservation(
                "trailing",
                PixelInterval(280.0, 330.0),
                "white_holder_transition",
                edge_provenance,
            ),
        )
        visible_length = visible_sequence_length_interval(span, boundaries)
        result = corroborate_single_missing_overlap(
            visible_length_px=visible_length,
            count=3,
            frame_width_px=PixelInterval.exact(100.0),
            spacings=(
                observed_spacing_evidence(
                    FrameBoundaryReference(None, 1),
                    PixelInterval.exact(5.0),
                    edge_provenance,
                ),
                spacing_hypothesis(
                    FrameBoundaryReference(None, 2),
                    PixelInterval(-100.0, 100.0),
                    MeasurementProvenance(
                        MeasurementIdentity.FRAME_GEOMETRY,
                        "synthetic",
                        (MeasurementIdentity.FRAME_DIMENSIONS,),
                    ),
                ),
            ),
            holder_occlusion=holder_occlusion_not_applicable(),
            boundary_observations=boundaries,
            dimension_source=FrameDimensionPriorSource.SCAN_CALIBRATION,
        )
        self.assertEqual(visible_length, PixelInterval(270.0, 330.0))
        self.assertTrue(
            any(isinstance(spacing, SpacingHypothesis) for spacing in result)
        )
        self.assertFalse(
            any(
                isinstance(spacing, CorroboratedSpacingEvidence)
                for spacing in result
            )
        )

    def test_sequence_solver_cannot_emit_non_monotonic_frames(self) -> None:
        result = solve_frame_sequence(
            (separator_observation(280.0, start=275.0, end=285.0),),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval(10.0, 290.0),
                PixelInterval.exact(100.0),
                (36.0, 24.0),
                FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                MeasurementProvenance(
                    MeasurementIdentity.FRAME_DIMENSIONS,
                    "synthetic",
                    (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                ),
            ),
            (),
            10_000,
        )
        self.assertTrue(all(frame.valid() for frame in result.frames))
        self.assertTrue(
            all(
                left.right <= right.left
                for left, right in zip(result.frames, result.frames[1:])
            )
        )

    def test_content_at_frame_edges_is_not_undercrop(self) -> None:
        frame_content = FrameContentEvidence(
            EvidenceState.SUPPORTED,
            "content_observed",
            0.2,
            0.4,
            0.4,
            (
                FrameContentObservation(1, 0.4, 0.4, True, ("right",)),
                FrameContentObservation(2, 0.4, 0.4, True, ("left",)),
            ),
        )
        alignment = SequenceContentAlignmentEvidence(
            EvidenceState.SUPPORTED,
            "content_inside_visible_sequence",
            Box(0, 0, 200, 100),
            Box(0, 0, 200, 100),
            (),
            False,
            False,
            0,
            0,
            0,
            0,
        )
        partial = PartialEdgeSafetyEvidence(
            is_partial=False,
            hard_separator_count=1,
            expected_separator_count=1,
            frame_coverage_state=EvidenceState.SUPPORTED,
            frame_dimension_state=EvidenceState.SUPPORTED,
            diagnostics=(),
        )
        coverage = FrameCoverageEvidence(
            holder_long_axis_interval=(0, 200),
            visible_sequence_interval=(0, 200),
            frame_intervals=((0, 200),),
            content_runs=((0, 200),),
            candidate_frame_count=2,
        )
        state = content_preservation_state(
            coverage,
            alignment,
            partial,
        )
        self.assertTrue(
            all(
                observation.boundary_contact_sides
                for observation in frame_content.observations
            )
        )
        self.assertEqual(state, EvidenceState.SUPPORTED)

    def test_unresolved_auto_count_cannot_be_approved(self) -> None:
        candidate = candidate_fixture()
        selection = replace(
            selection_fixture(candidate),
            geometry_resolution=GeometryResolution(
                EvidenceState.UNAVAILABLE,
                False,
                False,
                False,
                False,
                True,
                True,
                ("count_unresolved",),
            ),
        )
        detection = apply_decision_gate(
            selection,
            frame_bleed_fixture(),
            transform_geometry_fixture(),
        )
        self.assertEqual(detection.status, "needs_review")


if __name__ == "__main__":
    unittest.main()
