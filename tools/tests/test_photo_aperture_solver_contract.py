from __future__ import annotations

from dataclasses import fields, replace
from inspect import signature
import unittest

from tools.tests.photo_aperture_solver_support import (
    dimensions as _dimensions,
    geometry as _geometry,
    plan as _plan,
    provenance as _provenance,
    scope as _scope,
    separator as _separator,
)
from x5crop.detection.physical.sequence_solver import (
    PhotoSequenceSolveResult,
    _measured_aperture_constraints,
    photo_aperture_cross_axis_plan,
    solve_photo_sequence,
)
from x5crop.detection.physical import sequence_solver
from x5crop.image.content import ContentRegionObservation
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    PhotoSequenceSolution,
)
from x5crop.report.read_models import typed_read_model
from x5crop.report.validation import _typed_value_from_read_model
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    FrameDimensionPriorSource,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    ObservationId,
    PhotoApertureEdgeSource,
    PhotoApertureCrossAxisHypothesis,
    PixelInterval,
    SeparatorBandAssignment,
)


class PhotoApertureSolverContractTest(unittest.TestCase):
    def test_solver_accepts_count_independent_visible_content_constraints(self) -> None:
        self.assertIn(
            "visible_content",
            signature(solve_photo_sequence).parameters,
        )

    def test_solver_build_objectives_have_one_named_physical_semantics(self) -> None:
        objective_type = getattr(sequence_solver, "_SequenceBuildObjectives", None)
        self.assertIsNotNone(objective_type)
        assert objective_type is not None
        self.assertEqual(
            tuple(field.name for field in fields(objective_type)),
            (
                "uncorroborated_overlap_extent_px",
                "supported_separator_count",
                "internal_boundary_measurement_quality",
                "dimension_residual",
                "external_boundary_measurement_quality",
                "boundary_uncertainty_ratio",
                "visible_aperture_coverage_px",
            ),
        )
        self.assertNotIn(
            "physical_objectives",
            sequence_solver._SequenceBuild.__dataclass_fields__,
        )

    def test_exact_measured_option_capacity_is_not_search_exhaustion(self) -> None:
        scope = _scope(
            width=100,
            height=120,
            leading=0.0,
            trailing=100.0,
            top=10.0,
            bottom=110.0,
        )
        cross_axis = _plan(scope).hypotheses[0]

        options, _evaluations, exhausted = _measured_aperture_constraints(
            scope,
            cross_axis,
            _dimensions(100.0, 100.0),
            excluded_separator_bands=(),
            evaluation_budget=100,
            maximum_options=1,
        )

        self.assertEqual(len(options), 1)
        self.assertFalse(exhausted)

    def test_separator_bound_paths_do_not_reenter_generic_aperture_search(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0),
        )
        cross_axis = _plan(scope).hypotheses[0]
        support = _separator(100.0, 110.0, supported=True)

        options, _evaluations, exhausted = _measured_aperture_constraints(
            scope,
            cross_axis,
            _dimensions(100.0, 100.0),
            excluded_separator_bands=(support.observation,),
            evaluation_budget=100,
            maximum_options=8,
        )

        self.assertEqual(options, ())
        self.assertFalse(exhausted)

    def test_separator_search_prunes_noise_before_combination_budget_is_exhausted(self) -> None:
        scope = _scope(
            width=650,
            height=120,
            leading=0.0,
            trailing=650.0,
            top=10.0,
            bottom=110.0,
        )
        supported = tuple(
            _separator(float(start), float(start + 10), supported=True)
            for start in (100, 210, 320, 430, 540)
        )
        noise = tuple(
            _separator(float(start), float(start + 5))
            for start in range(20, 620, 20)
            if start not in {100, 320, 540}
        )

        solved = solve_photo_sequence(
            (*noise, *supported),
            scope,
            _plan(scope),
            6,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=200,
            maximum_solution_alternatives=1,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(
            tuple(
                assignment.observation
                for assignment in solved.separator_assignments
            ),
            tuple(support.observation for support in supported),
        )
        self.assertLess(solved.assignment_evaluations, 200)

    def test_separator_solution_does_not_hide_conflicting_measured_apertures(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(5.0, 105.0, 110.0),
        )

        solved = solve_photo_sequence(
            (_separator(100.0, 110.0, supported=True),),
            scope,
            _plan(scope),
            2,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=2_000,
            maximum_solution_alternatives=16,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(len(solved.separator_assignments), 1)
        self.assertEqual(
            solved.assignment_consensus.outcome,
            AssignmentConsensusOutcome.DISAGREED,
        )
        self.assertTrue(solved.assignment_consensus.conflicting_photo_indexes)
        self.assertFalse(solved.search_budget_exhausted)

    def test_visible_content_only_prunes_geometry_that_omits_measured_runs(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(5.0, 105.0, 110.0),
        )

        solved = solve_photo_sequence(
            (_separator(100.0, 110.0, supported=True),),
            scope,
            _plan(scope),
            2,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, ((0, 100), (110, 210)), 0),
            maximum_assignment_evaluations=2_000,
            maximum_solution_alternatives=16,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(
            solved.assignment_consensus.outcome,
            AssignmentConsensusOutcome.UNCONTESTED,
        )
        self.assertEqual(
            tuple(
                (aperture.leading.position, aperture.trailing.position)
                for aperture in solved.photo_apertures
            ),
            (
                (PixelInterval.exact(0.0), PixelInterval.exact(100.0)),
                (PixelInterval.exact(110.0), PixelInterval.exact(210.0)),
            ),
        )

    def test_dimension_fallback_is_pruned_when_supported_band_fits_neighbors(self) -> None:
        scope = _scope(
            width=1310,
            height=120,
            leading=0.0,
            trailing=1310.0,
            top=10.0,
            bottom=110.0,
        )
        separators = tuple(
            _separator(float(start), float(start + 10), supported=True)
            for start in range(100, 1210, 110)
        )

        solved = solve_photo_sequence(
            separators,
            scope,
            _plan(scope),
            12,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=500,
            maximum_solution_alternatives=64,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertFalse(solved.search_budget_exhausted)
        self.assertEqual(len(solved.separator_assignments), 11)
        self.assertLess(solved.assignment_evaluations, 100)

    def test_impossible_measured_aperture_chain_is_rejected_without_exhaustive_search(self) -> None:
        scope = _scope(
            width=200,
            height=120,
            leading=0.0,
            trailing=200.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(0.0,) * 120 + (100.0,) * 120,
        )

        solved = solve_photo_sequence(
            (),
            scope,
            _plan(scope),
            12,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=5_000,
            maximum_solution_alternatives=8,
        )

        self.assertNotIsInstance(solved, PhotoSequenceSolveResult)
        self.assertLess(solved.assignment_evaluations, 5_000)

    def test_unavailable_solution_preserves_search_budget_exhaustion(self) -> None:
        scope = _scope(
            width=200,
            height=120,
            leading=0.0,
            trailing=200.0,
            top=10.0,
            bottom=110.0,
            internal_paths=tuple(float(value) for value in range(5, 195, 5)),
        )

        solved = solve_photo_sequence(
            (),
            scope,
            _plan(scope),
            12,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=1,
            maximum_solution_alternatives=1,
        )

        self.assertNotIsInstance(solved, PhotoSequenceSolveResult)
        self.assertTrue(solved.search_budget_exhausted)

    def test_uncertain_edges_must_guarantee_positive_aperture_width(self) -> None:
        scope = _scope(
            width=200,
            height=120,
            leading=0.0,
            trailing=200.0,
            top=10.0,
            bottom=110.0,
        )
        paths = tuple(
            replace(
                path,
                samples=tuple(
                    replace(
                        sample,
                        position=(
                            PixelInterval(0.0, 100.0)
                            if path.provenance.observation_id
                            == ObservationId("leading_aperture_path")
                            else PixelInterval(100.0, 200.0)
                        ),
                    )
                    for sample in path.samples
                ),
            )
            if path.axis == BoundaryAxis.LONG
            else path
            for path in scope.raw_boundary_paths
        )
        uncertain_scope = replace(scope, raw_boundary_paths=paths)

        solved = solve_photo_sequence(
            (),
            uncertain_scope,
            _plan(uncertain_scope),
            1,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(uncertain_scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=100,
            maximum_solution_alternatives=8,
        )

        self.assertNotIsInstance(solved, PhotoSequenceSolveResult)

    def test_separator_assignment_edges_must_match_observed_band_edges(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0),
        )
        observation = _separator(100.0, 110.0, supported=True)
        dimensions = _dimensions(100.0, 100.0)
        solved = solve_photo_sequence(
            (observation,),
            scope,
            _plan(scope),
            2,
            dimensions,
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        assignment = solved.separator_assignments[0]
        with self.assertRaisesRegex(ValueError, "observed band edges"):
            SeparatorBandAssignment(
                assignment.boundary_index,
                assignment.observation,
                assignment.cross_axis_measurement,
                replace(
                    assignment.preceding_trailing_edge,
                    position=PixelInterval.exact(
                        observation.observation.start - 1.0
                    ),
                ),
                assignment.following_leading_edge,
                assignment.width_constraint,
            )

    def test_weak_separator_can_only_form_provisional_aperture_edges(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=5.0,
            trailing=205.0,
            top=10.0,
            bottom=110.0,
        )
        dimensions = _dimensions(95.0, 100.0)

        observations = (_separator(100.0, 110.0),)
        solved = solve_photo_sequence(
            observations,
            scope,
            _plan(scope),
            2,
            dimensions,
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(solved.separator_assignments, ())
        self.assertEqual(
            solved.photo_apertures[0].trailing.source,
            PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        )
        self.assertEqual(
            solved.photo_apertures[1].leading.source,
            PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        )
        self.assertEqual(
            solved.photo_apertures[0].trailing.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            solved.inter_photo_spacings[0].basis,
            InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        geometry = _geometry(scope, observations, dimensions, solved)
        self.assertEqual(len(geometry.inter_photo_spacings), geometry.count - 1)
        self.assertEqual(
            _typed_value_from_read_model(
                typed_read_model(geometry),
                PhotoSequenceSolution,
            ),
            geometry,
        )

    def test_global_photo_width_consensus_skips_extra_tonal_band(self) -> None:
        scope = _scope(
            width=330,
            height=120,
            leading=0.0,
            trailing=320.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0),
        )
        first = _separator(100.0, 110.0, supported=True)
        unrelated = _separator(145.0, 200.0, supported=True)
        second = _separator(210.0, 220.0, supported=True)

        observations = (first, unrelated, second)
        dimensions = _dimensions(100.0, 100.0)
        solved = solve_photo_sequence(
            observations,
            scope,
            _plan(scope),
            3,
            dimensions,
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        selected_bands = {
            assignment.observation for assignment in solved.separator_assignments
        }
        self.assertIn(first.observation, selected_bands)
        self.assertIn(second.observation, selected_bands)
        self.assertNotIn(unrelated.observation, selected_bands)

    def test_photo_width_measurements_share_a_physical_interval_not_one_exact_pixel_width(self) -> None:
        scope = _scope(
            width=460,
            height=120,
            leading=0.0,
            trailing=460.0,
            top=0.0,
            bottom=120.0,
        )
        top_path = next(
            path
            for path in scope.raw_boundary_paths
            if path.provenance.observation_id
            == ObservationId("top_aperture_path")
        )
        bottom_path = next(
            path
            for path in scope.raw_boundary_paths
            if path.provenance.observation_id
            == ObservationId("bottom_aperture_path")
        )
        uncertain_top = replace(
            top_path,
            samples=tuple(
                replace(sample, position=PixelInterval(0.0, 10.0))
                for sample in top_path.samples
            ),
        )
        uncertain_bottom = replace(
            bottom_path,
            samples=tuple(
                replace(sample, position=PixelInterval(110.0, 120.0))
                for sample in bottom_path.samples
            ),
        )
        uncertain_scope = replace(
            scope,
            raw_boundary_paths=tuple(
                uncertain_top
                if path is top_path
                else uncertain_bottom
                if path is bottom_path
                else path
                for path in scope.raw_boundary_paths
            ),
        )
        cross_axis = PhotoApertureCrossAxisHypothesis(
            uncertain_top,
            uncertain_bottom,
        )
        observations = (
            _separator(100.0, 110.0, supported=True, cross_axis=cross_axis),
            _separator(215.0, 225.0, supported=True, cross_axis=cross_axis),
            _separator(340.0, 350.0, supported=True, cross_axis=cross_axis),
        )

        solved = solve_photo_sequence(
            observations,
            uncertain_scope,
            photo_aperture_cross_axis_plan(
                uncertain_scope,
                _dimensions(1.0, 1.0),
                4,
                maximum_hypotheses=8,
            ),
            4,
            _dimensions(1.0, 1.0),
            ContentRegionObservation(uncertain_scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(len(solved.separator_assignments), 3)
        self.assertEqual(
            solved.photo_width_constraint_px,
            PixelInterval(100.0, 120.0),
        )

    def test_width_contradicted_tonal_band_becomes_dimension_constrained(self) -> None:
        scope = _scope(
            width=440,
            height=120,
            leading=0.0,
            trailing=440.0,
            top=10.0,
            bottom=110.0,
        )
        first = _separator(100.0, 110.0, supported=True)
        overwide = _separator(190.0, 230.0, supported=True)
        third = _separator(330.0, 340.0, supported=True)

        solved = solve_photo_sequence(
            (first, overwide, third),
            scope,
            _plan(scope),
            4,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(
            tuple(item.observation for item in solved.separator_assignments),
            (first.observation, third.observation),
        )
        self.assertEqual(
            solved.photo_apertures[1].trailing.source,
            PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        )
        self.assertEqual(
            solved.photo_apertures[2].leading.source,
            PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        )

    def test_band_wide_enough_for_a_photo_is_not_a_hard_separator(self) -> None:
        scope = _scope(
            width=350,
            height=120,
            leading=0.0,
            trailing=350.0,
            top=10.0,
            bottom=110.0,
        )
        overwide = _separator(100.0, 250.0, supported=True)

        solved = solve_photo_sequence(
            (overwide,),
            scope,
            _plan(scope),
            2,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(solved.separator_assignments, ())
        self.assertEqual(
            solved.photo_apertures[0].trailing.source,
            PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        )
        self.assertEqual(
            solved.photo_apertures[1].leading.source,
            PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        )

    def test_width_contradicted_band_keeps_intersecting_aperture_edges(self) -> None:
        scope = _scope(
            width=440,
            height=120,
            leading=0.0,
            trailing=430.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(210.0, 220.0),
        )
        uncertain_positions = {
            PixelInterval.exact(210.0): PixelInterval(189.0, 211.0),
            PixelInterval.exact(220.0): PixelInterval(219.0, 231.0),
        }
        scope = replace(
            scope,
            raw_boundary_paths=tuple(
                replace(
                    item,
                    samples=tuple(
                        replace(
                            sample,
                            position=uncertain_positions[item.position],
                        )
                        for sample in item.samples
                    ),
                )
                if item.position in uncertain_positions
                else item
                for item in scope.raw_boundary_paths
            ),
        )
        first = _separator(100.0, 110.0, supported=True)
        overwide = _separator(190.0, 230.0, supported=True)
        third = _separator(320.0, 330.0, supported=True)

        solved = solve_photo_sequence(
            (first, overwide, third),
            scope,
            _plan(scope),
            4,
            _dimensions(100.0, 100.0),
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(
            solved.photo_apertures[1].trailing.source,
            PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
        )
        self.assertEqual(
            solved.photo_apertures[2].leading.source,
            PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
        )
        self.assertEqual(
            solved.inter_photo_spacings[1].basis,
            InterPhotoSpacingBasis.OBSERVED,
        )
        self.assertEqual(
            tuple(item.observation for item in solved.separator_assignments),
            (first.observation, third.observation),
        )

    def test_canvas_adjacent_bands_cannot_bind_internal_photo_boundaries(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=5.0,
            trailing=205.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0),
        )
        leading_holder_band = _separator(0.0, 5.0, supported=True)
        internal = _separator(100.0, 110.0, supported=True)
        trailing_holder_band = _separator(205.0, 210.0, supported=True)

        observations = (leading_holder_band, internal, trailing_holder_band)
        dimensions = _dimensions(95.0, 100.0)
        solved = solve_photo_sequence(
            observations,
            scope,
            _plan(scope),
            2,
            dimensions,
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(
            tuple(item.observation for item in solved.separator_assignments),
            (internal.observation,),
        )

    def test_positive_separator_band_cannot_produce_overlap_spacing(self) -> None:
        scope = _scope(
            width=310,
            height=120,
            leading=10.0,
            trailing=300.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 200.0),
        )
        observations = (
            _separator(100.0, 110.0, supported=True),
            _separator(200.0, 210.0, supported=True),
        )
        dimensions = FrameDimensionPrior(
            frame_size_mm=(1.0, 1.0),
            source=FrameDimensionPriorSource.SCAN_CALIBRATION,
            provenance=_provenance(
                MeasurementIdentity.SCAN_CALIBRATION,
                "synthetic_calibrated_dimensions",
            ),
            calibrated_width_px=PixelInterval(90.0, 110.0),
            calibrated_height_px=PixelInterval.exact(100.0),
        )

        solved = solve_photo_sequence(
            observations,
            scope,
            _plan(scope),
            3,
            dimensions,
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertTrue(
            all(
                spacing.signed_width_px.maximum >= 0.0
                for spacing in solved.inter_photo_spacings
            )
        )

    def test_holder_clipped_edge_photos_need_not_match_full_photo_width(self) -> None:
        scope = _scope(
            width=310,
            height=120,
            leading=15.0,
            trailing=295.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0, 200.0, 210.0),
            holder_sides=(BoundarySide.LEADING, BoundarySide.TRAILING),
        )
        observations = (
            _separator(100.0, 110.0, supported=True),
            _separator(200.0, 210.0, supported=True),
        )
        dimensions = FrameDimensionPrior(
            frame_size_mm=(1.0, 1.0),
            source=FrameDimensionPriorSource.SCAN_CALIBRATION,
            provenance=_provenance(
                MeasurementIdentity.SCAN_CALIBRATION,
                "synthetic_calibrated_dimensions",
            ),
            calibrated_width_px=PixelInterval.exact(90.0),
            calibrated_height_px=PixelInterval.exact(100.0),
        )
        solved = solve_photo_sequence(
            observations,
            scope,
            _plan(scope),
            3,
            dimensions,
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        geometry = _geometry(scope, observations, dimensions, solved)

        self.assertLess(
            geometry.photo_apertures[0].trailing.position.midpoint
            - geometry.photo_apertures[0].leading.position.midpoint,
            geometry.photo_width_constraint_px.minimum,
        )
        self.assertTrue(
            geometry.photo_apertures[1].trailing.position.minus(
                geometry.photo_apertures[1].leading.position
            ).intersects(geometry.photo_width_constraint_px)
        )

    def test_short_edge_photos_without_holder_contact_are_not_physical(self) -> None:
        scope = _scope(
            width=310,
            height=120,
            leading=15.0,
            trailing=295.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0, 200.0, 210.0),
        )
        observations = (
            _separator(100.0, 110.0, supported=True),
            _separator(200.0, 210.0, supported=True),
        )
        dimensions = FrameDimensionPrior(
            frame_size_mm=(1.0, 1.0),
            source=FrameDimensionPriorSource.SCAN_CALIBRATION,
            provenance=_provenance(
                MeasurementIdentity.SCAN_CALIBRATION,
                "synthetic_calibrated_dimensions",
            ),
            calibrated_width_px=PixelInterval.exact(90.0),
            calibrated_height_px=PixelInterval.exact(100.0),
        )

        solved = solve_photo_sequence(
            observations,
            scope,
            _plan(scope),
            3,
            dimensions,
            ContentRegionObservation(scope.holder_span.box, (), 0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertNotIsInstance(solved, PhotoSequenceSolveResult)


if __name__ == "__main__":
    unittest.main()
