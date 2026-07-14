from __future__ import annotations

from dataclasses import replace
from inspect import signature
import unittest

from tools.tests.photo_aperture_solver_support import (
    dimensions as _dimensions,
    path as _path,
    scope as _scope,
)
from x5crop.detection.physical.sequence_solver import (
    photo_aperture_cross_axis_plan,
)
from x5crop.domain import BoundaryAxis, PixelInterval


class PhotoApertureCrossAxisContractTest(unittest.TestCase):
    def test_boundary_measurement_exhaustion_reaches_cross_axis_plan(self) -> None:
        search_scope = replace(
            _scope(
                width=320,
                height=120,
                leading=0.0,
                trailing=320.0,
                top=10.0,
                bottom=110.0,
            ),
            measurement_budget_exhausted=True,
        )

        plan = photo_aperture_cross_axis_plan(
            search_scope,
            _dimensions(1.0, 1.0),
            1,
            maximum_hypotheses=8,
        )

        self.assertTrue(plan.search_budget_exhausted)

    def test_cross_axis_planning_does_not_enumerate_separator_sequences(self) -> None:
        scope = _scope(
            width=320,
            height=120,
            leading=0.0,
            trailing=320.0,
            top=10.0,
            bottom=110.0,
        )
        plan = photo_aperture_cross_axis_plan(
            scope,
            _dimensions(1.0, 1.0),
            1,
            maximum_hypotheses=8,
        )

        self.assertEqual(
            tuple(signature(photo_aperture_cross_axis_plan).parameters),
            ("search_scope", "dimensions", "count", "maximum_hypotheses"),
        )
        self.assertTrue(plan.hypotheses)
        self.assertEqual(plan.assignment_evaluations, 0)
        self.assertFalse(plan.search_budget_exhausted)

    def test_cross_axis_budget_prioritizes_visible_aperture_extent(self) -> None:
        search_scope = _scope(
            width=320,
            height=120,
            leading=0.0,
            trailing=320.0,
            top=10.0,
            bottom=110.0,
        )
        bottom = next(
            item
            for item in search_scope.raw_boundary_paths
            if item.axis == BoundaryAxis.SHORT
            and item.position == PixelInterval.exact(110.0)
        )
        lower_quality_bottom = replace(
            bottom,
            lower_appearance=replace(
                bottom.lower_appearance,
                spatial_continuity=0.6,
            ),
            upper_appearance=replace(
                bottom.upper_appearance,
                spatial_continuity=0.6,
            ),
        )
        internal = _path(
            BoundaryAxis.SHORT,
            20.0,
            "high_quality_internal_transition",
        )
        search_scope = replace(
            search_scope,
            raw_boundary_paths=tuple(
                lower_quality_bottom if item is bottom else item
                for item in search_scope.raw_boundary_paths
            )
            + (internal,),
        )

        plan = photo_aperture_cross_axis_plan(
            search_scope,
            _dimensions(1.0, 1.0),
            1,
            maximum_hypotheses=1,
        )

        self.assertEqual(plan.hypotheses[0].height_px, PixelInterval.exact(100.0))
        self.assertTrue(plan.search_budget_exhausted)

    def test_cross_axis_budget_prioritizes_nonoverlap_feasible_dimensions(self) -> None:
        search_scope = _scope(
            width=320,
            height=300,
            leading=0.0,
            trailing=320.0,
            top=20.0,
            bottom=170.0,
        )
        infeasible_bottom = _path(
            BoundaryAxis.SHORT,
            270.0,
            "overlap_required_bottom_transition",
        )
        search_scope = replace(
            search_scope,
            raw_boundary_paths=(
                *search_scope.raw_boundary_paths,
                infeasible_bottom,
            ),
        )

        plan = photo_aperture_cross_axis_plan(
            search_scope,
            _dimensions(1.0, 1.0),
            2,
            maximum_hypotheses=1,
        )

        self.assertEqual(plan.hypotheses[0].height_px, PixelInterval.exact(150.0))
        self.assertTrue(plan.search_budget_exhausted)


if __name__ == "__main__":
    unittest.main()
