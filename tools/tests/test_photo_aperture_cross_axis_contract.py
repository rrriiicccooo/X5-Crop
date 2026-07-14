from __future__ import annotations

from dataclasses import replace
from inspect import signature
import unittest

from tools.tests.photo_aperture_solver_support import (
    appearance as _appearance,
    dimensions as _dimensions,
    path as _path,
    provenance as _provenance,
    scope as _scope,
)
import x5crop.domain as domain
from x5crop.detection.physical.sequence_solver import (
    _short_axis_resolution,
    photo_aperture_cross_axis_plan,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundarySide,
    GrayBoundaryPathObservation,
    MeasurementIdentity,
    PixelInterval,
)


class PhotoApertureCrossAxisContractTest(unittest.TestCase):
    def test_sloped_path_resolves_each_photo_at_its_own_long_axis_extent(self) -> None:
        sample_type = getattr(domain, "BoundaryPathSample", None)
        self.assertIsNotNone(sample_type)
        measurement_provenance = _provenance(
            MeasurementIdentity.BOUNDARY_PATHS,
            "sloped_short_axis_path",
        )
        path = GrayBoundaryPathObservation(
            axis=BoundaryAxis.SHORT,
            kind=BoundaryKind.TEXTURE_TRANSITION,
            samples=(
                sample_type(PixelInterval(0.0, 50.0), PixelInterval(10.0, 12.0)),
                sample_type(PixelInterval(50.0, 100.0), PixelInterval(20.0, 22.0)),
            ),
            lower_appearance=_appearance(measurement_provenance),
            upper_appearance=_appearance(measurement_provenance),
            provenance=measurement_provenance,
        )

        left, _ = _short_axis_resolution(
            1,
            BoundarySide.TOP,
            path,
            PixelInterval(0.0, 50.0),
        )
        right, _ = _short_axis_resolution(
            2,
            BoundarySide.TOP,
            path,
            PixelInterval(50.0, 100.0),
        )

        self.assertLess(left.position.minimum, right.position.minimum)
        self.assertLess(left.position.maximum, right.position.maximum)

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

    def test_equivalent_gray_paths_do_not_multiply_physical_hypotheses(self) -> None:
        search_scope = _scope(
            width=320,
            height=120,
            leading=0.0,
            trailing=320.0,
            top=10.0,
            bottom=110.0,
        )
        search_scope = replace(
            search_scope,
            raw_boundary_paths=(
                *search_scope.raw_boundary_paths,
                _path(
                    BoundaryAxis.SHORT,
                    10.0,
                    "equivalent_top_texture_path",
                    kind=BoundaryKind.TEXTURE_TRANSITION,
                ),
                _path(
                    BoundaryAxis.SHORT,
                    110.0,
                    "equivalent_bottom_texture_path",
                    kind=BoundaryKind.TEXTURE_TRANSITION,
                ),
            ),
        )

        plan = photo_aperture_cross_axis_plan(
            search_scope,
            _dimensions(1.0, 1.0),
            1,
            maximum_hypotheses=8,
        )

        self.assertEqual(len(plan.hypotheses), 1)
        self.assertFalse(plan.search_budget_exhausted)


if __name__ == "__main__":
    unittest.main()
