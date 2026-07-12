from __future__ import annotations

import ast
from dataclasses import replace
from inspect import signature
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    frame_bleed_fixture,
    selection_fixture,
    separator_constraints,
    separator_observation,
    transform_geometry_fixture,
)
from x5crop.detection.candidate.selection.model import GeometryResolution
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.content.frame_support import (
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.content.preservation import (
    content_preservation_evidence,
)
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.partial_edge import PartialEdgeSafetyEvidence
from x5crop.detection.evidence.sequence_content_alignment import (
    SequenceContentAlignmentEvidence,
)
from x5crop.detection.physical.boundary import HolderOcclusionEvidence
from x5crop.detection.physical.boundary import holder_occlusion_for_sequence
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
    sequence_conservation_evidence,
    spacing_hypothesis,
)
from x5crop.domain import (
    BoundaryObservation,
    Box,
    EvidenceState,
    FrameBoundaryReference,
    FrameDimensionPrior,
    MeasurementProvenance,
    PixelInterval,
    VisibleSequenceSpan,
)
from x5crop.units import ScanCalibration


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
        provenance = MeasurementProvenance("spacing", "test", ())
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
        provenance = MeasurementProvenance("spacing", "test", ())
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
            / "x5crop/detection/candidate/build/sequence_candidate.py"
        ).read_text(encoding="utf-8")
        calls = tuple(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "holder_occlusion_for_sequence"
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            len(calls[0].args),
            len(signature(holder_occlusion_for_sequence).parameters),
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
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
            (),
            1,
        )
        self.assertTrue(result.search_budget_exhausted)

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
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
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
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
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
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
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
            "holder_boundary_profile",
            "synthetic_edges",
            ("gray_work",),
        )
        result = solve_frame_sequence(
            observations,
            (),
            VisibleSequenceSpan(Box(0, 0, 285, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                ((36.0, 24.0),),
                "scan_calibration",
                MeasurementProvenance(
                    "scan_calibration",
                    "synthetic",
                    ("tiff_resolution", "physical_frame_size"),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
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
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
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
                ((36.0, 24.0),),
                "short_axis_aspect",
                MeasurementProvenance(
                    "physical_frame_aspect",
                    "synthetic",
                    ("short_axis_boundaries",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
            (),
            100,
        )

        self.assertIsInstance(result.relations[1], SpacingHypothesis)

    def test_geometry_derived_negative_spacing_is_not_supported_overlap(self) -> None:
        spacing = spacing_hypothesis(
            FrameBoundaryReference(None, 1),
            PixelInterval(-20.0, -10.0),
            MeasurementProvenance(
                "frame_geometry",
                "synthetic",
                ("frame_dimensions",),
            ),
        )
        self.assertEqual(spacing.kind, "overlap")
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)

    def test_sequence_solver_cannot_emit_non_monotonic_frames(self) -> None:
        result = solve_frame_sequence(
            (separator_observation(280.0, start=275.0, end=285.0),),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval(10.0, 290.0),
                PixelInterval.exact(100.0),
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
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
            "synthetic",
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
            EvidenceState.NOT_APPLICABLE,
            "not_partial",
            False,
            1,
            1,
            EvidenceState.SUPPORTED,
            EvidenceState.NOT_APPLICABLE,
            False,
            (),
        )
        coverage = FrameCoverageEvidence(
            EvidenceState.SUPPORTED,
            "content_runs_covered",
            (0, 200),
            (0, 200),
            ((0, 100), (100, 200)),
            ((0, 200),),
            (),
            0,
        )
        evidence = content_preservation_evidence(
            frame_content,
            alignment,
            partial,
            coverage,
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

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
            ScanCalibration(None, None, "unavailable", False),
            image_width=200,
            image_height=100,
        )
        self.assertEqual(detection.status, "needs_review")


if __name__ == "__main__":
    unittest.main()
