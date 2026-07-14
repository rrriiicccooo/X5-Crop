from __future__ import annotations

from dataclasses import replace
from itertools import permutations
import unittest
from unittest.mock import patch

from tools.tests.photo_aperture_solver_support import (
    dimensions as _dimensions,
    plan as _plan,
    scope as _scope,
    separator as _separator,
)
from x5crop.detection.physical import sequence_solver
from x5crop.detection.physical.sequence_solver import (
    PhotoSequenceSolveResult,
    solve_photo_sequence,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryPathFit,
    GrayBoundaryPathObservation,
    PixelInterval,
)
from x5crop.image.content import ContentRegionObservation


def _single_photo_build() -> sequence_solver._SequenceBuild:
    scope = _scope(
        width=120,
        height=120,
        leading=10.0,
        trailing=110.0,
        top=10.0,
        bottom=110.0,
    )
    cross_axis = _plan(scope).hypotheses[0]
    solved = solve_photo_sequence(
        (),
        scope,
        _plan(scope),
        1,
        _dimensions(100.0, 100.0),
        ContentRegionObservation(scope.holder_span.box, (), 0),
        maximum_assignment_evaluations=100,
        maximum_solution_alternatives=8,
    )
    if not isinstance(solved, PhotoSequenceSolveResult):
        raise AssertionError("single-photo solver fixture must resolve")
    return sequence_solver._SequenceBuild(
        apertures=solved.photo_apertures,
        edge_assignments=solved.aperture_edge_assignments,
        separator_assignments=solved.separator_assignments,
        spacings=solved.inter_photo_spacings,
        photo_width_px=solved.photo_width_constraint_px,
        cross_axis=cross_axis,
        residuals=solved.residuals,
        objectives=sequence_solver._SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=0.0,
            supported_separator_count=0,
            internal_boundary_measurement_quality=0.0,
            dimension_residual=0.0,
            external_boundary_measurement_quality=0.0,
            boundary_uncertainty_ratio=0.0,
        ),
    )


def _with_uncertainty(
    build: sequence_solver._SequenceBuild,
    uncertainty: float,
) -> sequence_solver._SequenceBuild:
    return replace(
        build,
        objectives=replace(
            build.objectives,
            boundary_uncertainty_ratio=uncertainty,
        ),
    )


def _with_leading_interval(
    build: sequence_solver._SequenceBuild,
    interval: PixelInterval,
) -> sequence_solver._SequenceBuild:
    aperture = build.apertures[0]
    return replace(
        build,
        apertures=(
            replace(
                aperture,
                leading=replace(aperture.leading, position=interval),
            ),
        ),
    )


class PhotoApertureSolverEfficiencyContractTest(unittest.TestCase):
    def test_pairwise_dominance_does_not_rebuild_global_consensus(self) -> None:
        template = _single_photo_build()

        with patch.object(
            sequence_solver,
            "_conflicting_photo_indexes",
            side_effect=AssertionError("pairwise dominance rebuilt consensus"),
        ):
            self.assertTrue(
                sequence_solver._build_dominates(
                    _with_uncertainty(template, 0.0),
                    _with_uncertainty(template, 0.1),
                )
            )

    def test_dominated_bridge_cannot_erase_disjoint_geometry(self) -> None:
        template = _single_photo_build()
        left = _with_uncertainty(
            _with_leading_interval(template, PixelInterval(0.0, 4.0)),
            0.2,
        )
        bridge = _with_uncertainty(
            _with_leading_interval(template, PixelInterval(0.0, 10.0)),
            0.1,
        )
        right = _with_leading_interval(template, PixelInterval(6.0, 10.0))

        self.assertEqual(
            sequence_solver._non_dominated_builds((left, bridge, right)),
            (left, right),
        )

    def test_lower_uncorroborated_overlap_cannot_erase_disjoint_geometry(self) -> None:
        template = _single_photo_build()
        no_overlap = _with_leading_interval(
            template,
            PixelInterval(0.0, 4.0),
        )
        distinct_overlap = replace(
            _with_leading_interval(template, PixelInterval(6.0, 10.0)),
            objectives=replace(
                template.objectives,
                uncorroborated_overlap_extent_px=1.0,
            ),
        )

        self.assertEqual(
            sequence_solver._non_dominated_builds(
                (no_overlap, distinct_overlap)
            ),
            (no_overlap, distinct_overlap),
        )

    def test_frontier_matches_exhaustive_reduction_for_every_input_order(self) -> None:
        template = _single_photo_build()
        builds = (
            _with_uncertainty(
                _with_leading_interval(template, PixelInterval(0.0, 4.0)),
                0.2,
            ),
            _with_uncertainty(
                _with_leading_interval(template, PixelInterval(0.0, 10.0)),
                0.1,
            ),
            _with_leading_interval(template, PixelInterval(6.0, 10.0)),
            _with_uncertainty(
                _with_leading_interval(template, PixelInterval(1.0, 3.0)),
                0.1,
            ),
            _with_uncertainty(
                _with_leading_interval(template, PixelInterval(7.0, 9.0)),
                0.1,
            ),
            _with_uncertainty(template, 0.3),
        )

        for ordered in permutations(builds):
            expected = tuple(
                build
                for index, build in enumerate(ordered)
                if not any(
                    other_index != index
                    and sequence_solver._build_dominates(other, build)
                    for other_index, other in enumerate(ordered)
                )
            )
            self.assertEqual(
                sequence_solver._non_dominated_builds(ordered),
                expected,
            )

    def test_non_dominated_search_compares_only_active_frontier(self) -> None:
        alternatives = tuple(range(64))

        with patch.object(
            sequence_solver,
            "_build_dominates",
            side_effect=lambda left, right: left > right,
        ) as dominates:
            surviving = sequence_solver._non_dominated_builds(alternatives)

        self.assertEqual(surviving, (63,))
        self.assertLessEqual(dominates.call_count, len(alternatives) * 2)

    def test_solver_canonicalizes_long_axis_paths_once(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0),
        )
        cross_axis_plan = _plan(scope)

        with patch.object(
            sequence_solver,
            "_axis_paths",
            wraps=sequence_solver._axis_paths,
        ) as canonical_paths:
            solve_photo_sequence(
                (_separator(100.0, 110.0, supported=True),),
                scope,
                cross_axis_plan,
                2,
                _dimensions(100.0, 100.0),
                ContentRegionObservation(scope.holder_span.box, (), 0),
                maximum_assignment_evaluations=2_000,
                maximum_solution_alternatives=16,
            )

        self.assertEqual(canonical_paths.call_count, 1)
        self.assertEqual(canonical_paths.call_args.args[1], BoundaryAxis.LONG)

    def test_solver_queries_precomputed_boundary_path_fits(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0),
        )
        cross_axis_plan = _plan(scope)

        with patch.object(
            GrayBoundaryPathObservation,
            "position_within",
            side_effect=AssertionError("solver refitted a boundary path"),
        ):
            solved = solve_photo_sequence(
                (_separator(100.0, 110.0, supported=True),),
                scope,
                cross_axis_plan,
                2,
                _dimensions(100.0, 100.0),
                ContentRegionObservation(scope.holder_span.box, (), 0),
                maximum_assignment_evaluations=2_000,
                maximum_solution_alternatives=16,
            )

        self.assertIsInstance(solved, PhotoSequenceSolveResult)

    def test_boundary_path_fit_is_bound_to_one_observation(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
        )
        path = scope.raw_boundary_paths[0]

        fit = BoundaryPathFit(path)

        self.assertIs(fit.observation, path)
        self.assertEqual(
            fit.observation_id,
            path.provenance.observation_id,
        )

    def test_distinct_paths_cannot_share_one_observation_identity(self) -> None:
        scope = _scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
        )
        path = scope.raw_boundary_paths[0]
        duplicate_identity = replace(
            path,
            samples=tuple(
                replace(
                    sample,
                    position=PixelInterval(
                        sample.position.minimum + 1.0,
                        sample.position.maximum + 1.0,
                    ),
                )
                for sample in path.samples
            ),
        )
        conflicting_scope = replace(
            scope,
            raw_boundary_paths=(*scope.raw_boundary_paths, duplicate_identity),
        )

        with self.assertRaisesRegex(ValueError, "observation identity"):
            sequence_solver._axis_paths(conflicting_scope, BoundaryAxis.LONG)


if __name__ == "__main__":
    unittest.main()
