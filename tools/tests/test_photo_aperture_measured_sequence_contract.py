from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.photo_aperture_solver_support import (
    dimensions as _dimensions,
    path as _path,
    plan as _plan,
    scope as _scope,
)
from x5crop.detection.physical.sequence_solver import (
    PhotoSequenceSolveResult,
    solve_photo_sequence,
)
from x5crop.domain import (
    BoundaryAxis,
    InterPhotoSpacingBasis,
    PixelInterval,
)


class PhotoApertureMeasuredSequenceContractTest(unittest.TestCase):
    def test_measured_contact_can_join_adjacent_photo_apertures_without_separator(self) -> None:
        scope = _scope(
            width=220,
            height=120,
            leading=10.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(110.0,),
        )
        solved = solve_photo_sequence(
            (),
            scope,
            _plan(scope),
            2,
            _dimensions(100.0, 100.0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(solved.inter_photo_spacings[0].kind, "contact")
        self.assertEqual(
            solved.inter_photo_spacings[0].basis,
            InterPhotoSpacingBasis.OBSERVED,
        )

    def test_measured_path_keeps_its_uncertainty_when_dimensions_intersect(self) -> None:
        scope = _scope(
            width=220,
            height=120,
            leading=10.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(110.0,),
        )
        exact_internal = next(
            item
            for item in scope.raw_boundary_paths
            if item.axis == BoundaryAxis.LONG
            and item.position == PixelInterval.exact(110.0)
        )
        uncertain_internal = replace(
            exact_internal,
            position=PixelInterval(109.0, 111.0),
            local_positions=(PixelInterval(109.0, 111.0),),
        )
        scope = replace(
            scope,
            raw_boundary_paths=tuple(
                uncertain_internal if item is exact_internal else item
                for item in scope.raw_boundary_paths
            ),
        )

        solved = solve_photo_sequence(
            (),
            scope,
            _plan(scope),
            2,
            _dimensions(100.0, 100.0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(
            solved.photo_apertures[0].trailing.position,
            PixelInterval(109.0, 111.0),
        )
        self.assertEqual(
            solved.photo_apertures[1].leading.position,
            PixelInterval(109.0, 111.0),
        )

    def test_measured_photo_edges_can_represent_overlap_without_separator(self) -> None:
        scope = _scope(
            width=220,
            height=120,
            leading=10.0,
            trailing=200.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0),
        )
        solved = solve_photo_sequence(
            (),
            scope,
            _plan(scope),
            2,
            _dimensions(100.0, 100.0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(solved.inter_photo_spacings[0].kind, "overlap")
        self.assertEqual(
            solved.inter_photo_spacings[0].basis,
            InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS,
        )

    def test_solver_prefers_nonoverlap_over_uncorroborated_overlap(self) -> None:
        scope = _scope(
            width=230,
            height=120,
            leading=10.0,
            trailing=220.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(20.0, 110.0, 120.0),
        )

        solved = solve_photo_sequence(
            (),
            scope,
            _plan(scope),
            2,
            _dimensions(100.0, 100.0),
            maximum_assignment_evaluations=10_000,
            maximum_solution_alternatives=8,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertNotEqual(solved.inter_photo_spacings[0].kind, "overlap")

    def test_measured_path_search_keeps_a_provisional_solution_before_truncation(self) -> None:
        scope = _scope(
            width=320,
            height=120,
            leading=0.0,
            trailing=320.0,
            top=10.0,
            bottom=110.0,
            internal_paths=tuple(float(value) for value in range(10, 320, 10)),
        )
        solved = solve_photo_sequence(
            (),
            scope,
            _plan(scope),
            3,
            _dimensions(100.0, 100.0),
            maximum_assignment_evaluations=200,
            maximum_solution_alternatives=1,
        )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertEqual(len(solved.photo_apertures), 3)
        self.assertTrue(solved.search_budget_exhausted)

    def test_exact_budget_consumption_does_not_hide_unexamined_cross_axis_hypotheses(self) -> None:
        scope = _scope(
            width=220,
            height=140,
            leading=10.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(110.0,),
        )
        scope = replace(
            scope,
            raw_boundary_paths=(
                *scope.raw_boundary_paths,
                _path(BoundaryAxis.SHORT, 120.0, "unexamined_cross_axis"),
            ),
        )
        plan = _plan(scope)
        self.assertGreater(len(plan.hypotheses), 1)

        solved = solve_photo_sequence(
            (),
            scope,
            plan,
            2,
            _dimensions(100.0, 100.0),
            maximum_assignment_evaluations=16,
            maximum_solution_alternatives=8,
        )

        self.assertTrue(solved.search_budget_exhausted)


if __name__ == "__main__":
    unittest.main()
