from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.optimize import LinearConstraint, minimize

from tools.tests.photo_geometry_support import make_side_measurement_set
from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.detection.photo_geometry.boundary_fitting import fit_format_bound_boundary_observation
from x5crop.detection.photo_geometry.line_observations import (
    CompleteTransitionLineFailureKind as Failure,
    CompleteTransitionLineWork,
    PhysicalLineRegion,
)
from x5crop.detection.photo_geometry.measurement_points import TransitionPoint
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis, BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC,
)
from x5crop.detection.photo_geometry.robust_line_fit import (
    LINE_REGION_ARITHMETIC_EPSILON_PX,
    _clip_line_region,
    _huber_edge_minimum,
    _physical_line_region,
    fit_complete_transition_line,
    fit_transition_line,
    physical_line_region,
)


def points_for(values, *, half_width=0.25):
    measurement = make_side_measurement_set(tuple((float(value),) for value in values),
                                           transition_half_width_px=half_width)
    return tuple(TransitionPoint(item, float(item.trace_coordinate_px), item.coordinate_px)
                 for item in measurement.transitions)


def empty_work():
    return {name: 0 for name in CompleteTransitionLineWork.__dataclass_fields__}


def analytic_seed(points, slope, intercept):
    # A test-only candidate: the new kernel must recompute every statistic and
    # must not trust the old receipt or residual vector to certify this line.
    return replace(fit_transition_line(points, 10.0, SPEC), slope=slope, intercept=intercept)


def huber_cost(residuals, delta):
    return math.fsum(0.5 * r * r if abs(r) <= delta else delta * (abs(r) - delta / 2)
                     for r in residuals)


class CompleteFamilyHuberContractTest(unittest.TestCase):
    def check_solution(self, evaluation, points, scale=10.0, spec=SPEC):
        self.assertIsNone(evaluation.failure_kind)
        solution = evaluation.solution
        self.assertIsNotNone(solution)
        assert solution is not None
        expected = tuple(point.coordinate - math.fsum((solution.slope * point.trace, solution.intercept))
                         for point in points)
        self.assertEqual(solution.residuals, expected)
        self.assertEqual(solution.cost, huber_cost(expected, spec.robust_loss_minimum_scale_mm * scale))
        self.assertLessEqual(solution.optimality_gap, spec.robust_fit_tolerance * solution.cost)
        self.assertLessEqual(abs(solution.slope), math.tan(math.radians(spec.maximum_measurable_line_angle_degrees)))
        for point in points:
            interval = point.transition.physical_position_interval_px
            allowance = spec.inlier_minimum_threshold_mm * scale
            value = math.fsum((solution.slope * point.trace, solution.intercept))
            self.assertGreaterEqual(value, interval.minimum - allowance - LINE_REGION_ARITHMETIC_EPSILON_PX)
            self.assertLessEqual(value, interval.maximum + allowance + LINE_REGION_ARITHMETIC_EPSILON_PX)
        if solution.cost == 0:
            self.assertEqual(solution.optimality_gap, 0)
            self.assertTrue(all(r == 0 for r in solution.residuals))
        return solution

    def check_work_bound(self, work):
        n = work.input_point_count
        v = work.polygon_vertex_count
        self.assertTrue(all(type(value) is int and value >= 0 for value in asdict(work).values()))
        self.assertLessEqual(work.raw_constraint_count, 2 * n)
        self.assertLessEqual(work.polygon_clip_count, 2 * n)
        self.assertLessEqual(v, 2 * n + 4)
        self.assertLessEqual(work.polygon_vertex_evaluation_count, 2 * n * (2 * n + 5))
        self.assertLessEqual(work.edge_count, v)
        self.assertLessEqual(work.event_count, 2 * n * work.edge_count)
        self.assertLessEqual(work.event_visit_count, work.event_count)
        self.assertLessEqual(work.candidate_count, work.edge_count + 1)
        self.assertLessEqual(work.loss_point_evaluation_count, n * (work.candidate_count + 1))
        self.assertLessEqual(work.gradient_point_evaluation_count, n * (work.edge_count + 2))
        self.assertLessEqual(work.gap_vertex_evaluation_count, 2 * v)
        self.assertLessEqual(work.raw_recheck_point_count, 2 * n)

    def test_complete_eleven_points_recovers_only_the_feasible_raw_family(self):
        for tail in (102.0, 103.0):
            points = points_for((100.0,) * 9 + (tail,) * 2)
            initial = fit_transition_line(points, 10.0, SPEC)
            initial_residuals = initial.residuals.copy()
            measured = make_side_measurement_set(tuple((point.coordinate,) for point in points))
            original = fit_format_bound_boundary_observation(
                measured, transition_ids=tuple(item.transition_id for item in measured.transitions),
                role=BoundaryRole.TOP, source_axis_long=BoundaryAxis.X,
                boundary_axis_scale_px_per_mm=PositiveInterval.exact(10.0),
            )
            self.assertIsNotNone(original)
            assert original is not None
            self.assertEqual(original.trace_support_count, 9)
            with patch('x5crop.detection.photo_geometry.robust_line_fit.least_squares', side_effect=AssertionError):
                evaluation = fit_complete_transition_line(points, 10.0, SPEC, initial_fit=initial)
            if tail == 102:
                solution = self.check_solution(evaluation, points)
                self.assertEqual(len(solution.residuals), 11)
                self.assertGreater(evaluation.work.edge_count, 0)
                self.assertEqual(evaluation.work.raw_recheck_point_count, 22)
            else:
                self.assertIsNone(evaluation.solution)
                self.assertEqual(evaluation.failure_kind, Failure.PHYSICAL_REGION_UNAVAILABLE)
                self.assertGreater(evaluation.work.polygon_clip_count, 0)
                self.assertEqual(evaluation.work.edge_count, 0)
            self.check_work_bound(evaluation.work)
            np.testing.assert_array_equal(initial.residuals, initial_residuals)
            self.assertFalse(initial.residuals.flags.writeable)
            self.assertIs(initial, fit_transition_line(points, 10.0, SPEC))

    def test_same_trace_distinct_raw_rejected_before_any_fit(self):
        measurement = make_side_measurement_set(((100.0, 101.0), (100.0,)))
        points = tuple(TransitionPoint(item, float(item.trace_coordinate_px), item.coordinate_px)
                       for item in measurement.transitions)
        initial = fit_transition_line(points, 10.0, SPEC)
        with patch('x5crop.detection.photo_geometry.robust_line_fit.least_squares', side_effect=AssertionError):
            result = fit_complete_transition_line(points, 10.0, SPEC, initial_fit=initial)
        self.assertEqual(result.failure_kind, Failure.TRACE_IDENTITY_CONFLICT)
        self.assertEqual(result.work.input_point_count, 3)
        self.assertEqual(result.work.raw_constraint_count, 0)
        self.assertEqual(result.work.initial_fit_point_check_count, 0)
        self.assertEqual(len(points), 3)
        self.assertEqual(len(initial.selected_points), 2)

    def test_input_validation_and_frozen_results(self):
        for points, scale in (((), 10.0), (points_for((100,)), 10.0), (points_for((100, 100)), 0.0)):
            result = fit_complete_transition_line(points, scale, SPEC)
            self.assertEqual(result.failure_kind, Failure.INVALID_INPUT)
            self.check_work_bound(result.work)
            with self.assertRaises(FrozenInstanceError):
                result.solution = None
        points = points_for((100, 100))
        result = fit_complete_transition_line((points[0], points[0]), 10, SPEC)
        self.assertEqual(result.failure_kind, Failure.INVALID_INPUT)

    def test_edge_endpoints_interior_kinks_repeated_events_and_flat_loss(self):
        cases = (
            ((2.0,), (1.0,), 0.5, 0.0),
            ((-2.0,), (1.0,), 0.5, 1.0),
            ((-0.25,), (1.0,), 1.0, 0.25),
            ((-1.5, 0.5), (1.0, 1.0), 1.0, 0.5),
            ((-1.5, -1.5, 0.5, 0.5), (1.0,) * 4, 1.0, 0.5),
            ((-2.0, 2.0), (1.0, 1.0), 0.5, 0.0),
            ((5.0, -3.0), (0.0, 0.0), 0.5, 0.0),
            ((2.0, 0.0), (-4.0, 0.0), 0.5, 0.5),
        )
        for residuals, changes, delta, expected in cases:
            with self.subTest(residuals=residuals, changes=changes):
                work = empty_work()
                fraction = _huber_edge_minimum(residuals, changes, delta, work)
                self.assertAlmostEqual(fraction, expected, places=14)
                value = huber_cost(tuple(a + fraction * b for a, b in zip(residuals, changes)), delta)
                for endpoint in (0.0, 1.0):
                    self.assertLessEqual(value, huber_cost(tuple(a + endpoint * b for a, b in zip(residuals, changes)), delta))
                self.assertEqual(work['edge_count'], 1)
                self.assertEqual(work['gradient_point_evaluation_count'], len(residuals))
                self.assertLessEqual(work['event_visit_count'], work['event_count'])
                self.assertLessEqual(work['event_count'], 2 * len(residuals))

    def test_independent_piecewise_edge_enumeration(self):
        rng = np.random.default_rng(171)
        for _ in range(60):
            a = tuple(rng.normal(size=7))
            b = tuple(rng.normal(size=7))
            delta = 0.6
            events = sorted({0.0, 1.0, *(float(t) for r, d in zip(a, b)
                for t in ((-delta-r)/d, (delta-r)/d) if 0 < t < 1)})
            candidates = list(events)
            for left, right in zip(events, events[1:]):
                middle = (left + right) / 2
                active = [i for i in range(len(a)) if abs(a[i] + middle*b[i]) < delta]
                curvature = math.fsum(b[i]**2 for i in active)
                if curvature:
                    derivative = math.fsum(d * max(-delta, min(delta, r+middle*d)) for r,d in zip(a,b))
                    candidates.append(min(right, max(left, middle-derivative/curvature)))
            expected = min(huber_cost(tuple(r+t*d for r,d in zip(a,b)), delta) for t in candidates)
            actual = _huber_edge_minimum(a, b, delta, empty_work())
            self.assertAlmostEqual(huber_cost(tuple(r+actual*d for r,d in zip(a,b)), delta), expected, places=12)

    def test_small_slsqp_reference_and_angle_cap(self):
        for values in ((100.0,) * 9 + (102.0,) * 2, tuple(100.0 + 0.08 * i * 10 for i in range(8))):
            points = points_for(values)
            result = fit_complete_transition_line(points, 10.0, SPEC)
            solution = self.check_solution(result, points)
            reference = float(np.median([point.trace for point in points]))
            design = np.array([[1.0, point.trace-reference] for point in points])
            target = np.array(values)
            low = target - 1.25
            high = target + 1.25
            cap = math.tan(math.radians(4.0))
            optimum = minimize(
                lambda x: huber_cost(tuple(design @ x-target), 0.5),
                np.array((float(np.mean(target)), 0.0)),
                jac=lambda x: design.T @ np.clip(design @ x-target, -0.5, 0.5),
                bounds=((None, None), (-cap, cap)),
                constraints=(LinearConstraint(design, low, high),),
                method='SLSQP', options={'ftol': 1e-12, 'maxiter': 100},
            )
            self.assertTrue(optimum.success, optimum.message)
            self.assertAlmostEqual(solution.cost, optimum.fun, places=10)
            self.check_work_bound(result.work)
            if len(values) == 8:
                self.assertAlmostEqual(solution.slope, cap, places=13)

    def test_initial_interior_zero_cost_and_identity_validation(self):
        points = points_for((100, 100, 100, 100))
        initial = analytic_seed(points, 0.0, 100.0)
        result = fit_complete_transition_line(points, 10.0, SPEC, initial_fit=initial)
        solution = self.check_solution(result, points)
        self.assertEqual(solution.cost, 0)
        self.assertEqual(result.work.edge_count, 0)
        self.assertEqual(result.work.initial_fit_point_check_count, 4)
        self.assertEqual(result.work.raw_recheck_point_count, 4)
        self.assertEqual(result.work.candidate_count, 1)
        self.assertEqual(result.work.loss_point_evaluation_count, 4)
        self.assertEqual(result.work.gradient_point_evaluation_count, 4)
        self.assertEqual(result.work.gap_vertex_evaluation_count, result.work.polygon_vertex_count)
        for bad in (replace(initial, selected_points=points[:-1]), replace(initial, slope=float('nan'))):
            failed = fit_complete_transition_line(points, 10.0, SPEC, initial_fit=bad)
            self.assertIsNone(failed.solution)
            self.assertEqual(failed.failure_kind, Failure.NUMERICAL_OPTIMALITY_UNAVAILABLE)
        # The receipt/residual vector is not an authority shortcut.
        wrong = replace(initial, intercept=100.0 + 1e-10)
        failed = fit_complete_transition_line(points, 10.0, SPEC, initial_fit=wrong)
        self.assertEqual(failed.failure_kind, Failure.NUMERICAL_OPTIMALITY_UNAVAILABLE)
        self.check_work_bound(failed.work)

    def test_interior_nonzero_cost_initial_candidate(self):
        points = points_for((100.1, 99.9, 99.9, 100.1))
        result = fit_complete_transition_line(points, 10, SPEC, initial_fit=analytic_seed(points, 0.0, 100.0))
        solution = self.check_solution(result, points)
        self.assertGreater(solution.cost, 0)
        self.assertEqual(result.work.edge_count, 0)

    def test_initial_same_ids_with_changed_raw_are_not_reused(self):
        points = points_for((100.0,) * 9 + (102.0,) * 2)
        initial = fit_transition_line(points, 10, SPEC)
        changed = replace(points[0], transition=replace(points[0].transition,
            physical_position_interval_px=FiniteInterval(99.0, 101.0)))
        mismatched = replace(initial, selected_points=(changed, *points[1:]))
        result = fit_complete_transition_line(points, 10, SPEC, initial_fit=mismatched)
        self.check_solution(result, points)
        self.assertEqual(result.work.initial_fit_point_check_count, len(points))
        self.assertEqual(result.work.candidate_count, result.work.edge_count)
        self.assertEqual(result.work.raw_recheck_point_count, len(points))
        self.assertEqual(points[0].transition.physical_position_interval_px, FiniteInterval(99.75, 100.25))

    def test_point_segment_and_thin_polygon_edge_degeneracies(self):
        # Isolate the numerical domain traversal. Physical clipping itself is
        # checked separately below and by test_physical_line_region_contract.
        points = points_for((100.0, 100.0, 100.0))
        regions = (
            PhysicalLineRegion(10.0, ((100.0, 0.0),)),
            PhysicalLineRegion(10.0, ((99.0, 0.0), (101.0, 0.0))),
            PhysicalLineRegion(10.0, ((99.0, 0.0), (101.0, 0.0), (101.0, 1e-14), (99.0, 1e-14))),
        )
        for region in regions:
            with patch('x5crop.detection.photo_geometry.robust_line_fit._physical_line_region', return_value=region):
                result = fit_complete_transition_line(points, 10.0, SPEC)
            solution = self.check_solution(result, points)
            self.assertEqual(solution.cost, 0.0)
            self.assertEqual(result.work.edge_count, len(region.vertices))
            self.assertEqual(result.work.raw_recheck_point_count, len(points))

    def test_raw_recheck_rejects_an_invalid_numerical_domain(self):
        points = points_for((100.0, 100.0, 100.0))
        region = PhysicalLineRegion(10.0, ((150.0, 0.0),))
        with patch('x5crop.detection.photo_geometry.robust_line_fit._physical_line_region', return_value=region):
            result = fit_complete_transition_line(points, 10.0, SPEC)
        self.assertEqual(result.failure_kind, Failure.RAW_CONSTRAINT_RECHECK_FAILED)
        self.assertEqual(result.work.raw_recheck_point_count, 3)
        self.assertEqual(result.work.loss_point_evaluation_count, 6)
        self.assertEqual(result.work.gap_vertex_evaluation_count, 1)

    def test_nonfinite_numerical_attempt_retains_work_without_retry(self):
        points = points_for((100.0,) * 9 + (102.0,) * 2)
        with patch('x5crop.detection.photo_geometry.robust_line_fit._huber_edge_minimum', return_value=float('nan')) as edge:
            result = fit_complete_transition_line(points, 10.0, SPEC)
        self.assertEqual(result.failure_kind, Failure.NONFINITE_NUMERICAL_RESULT)
        self.assertEqual(edge.call_count, 1)
        self.assertGreater(result.work.polygon_clip_count, 0)
        self.assertEqual(result.work.raw_recheck_point_count, 0)
        self.assertIsNone(result.solution)

    def test_solution_and_evaluation_reject_tampered_data(self):
        points = points_for((100.0, 100.0, 100.0))
        result = fit_complete_transition_line(points, 10, SPEC, initial_fit=analytic_seed(points, 0.0, 100.0))
        solution = self.check_solution(result, points)
        for changed in ({'slope': float('inf')}, {'intercept': float('nan')},
                        {'residuals': ()}, {'residuals': (float('nan'),)},
                        {'cost': -1.0}, {'cost': float('inf')}, {'optimality_gap': -1.0}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                replace(solution, **changed)
        with self.assertRaises(ValueError):
            replace(result, work=replace(result.work, input_point_count=2))
        with self.assertRaises(ValueError):
            replace(result, failure_kind=Failure.NUMERICAL_OPTIMALITY_UNAVAILABLE)

    def test_translation_and_input_permutation_preserve_the_line(self):
        points = points_for((100.0,) * 9 + (102.0,) * 2)
        original = self.check_solution(fit_complete_transition_line(points, 10, SPEC), points)
        for dx, dy in ((0, 0), (1000, 200), (-1000, -200)):
            moved = []
            for point in reversed(points):
                transition = replace(point.transition,
                    trace_coordinate_px=int(point.trace + dx),
                    canonical_coordinate_px=point.coordinate + dy,
                    localization_interval_px=FiniteInterval(point.transition.localization_interval_px.minimum+dy,
                                                            point.transition.localization_interval_px.maximum+dy),
                    physical_position_interval_px=FiniteInterval(point.transition.physical_position_interval_px.minimum+dy,
                                                                 point.transition.physical_position_interval_px.maximum+dy))
                moved.append(TransitionPoint(transition, point.trace+dx, point.coordinate+dy))
            moved = tuple(moved)
            solution = self.check_solution(fit_complete_transition_line(moved, 10, SPEC), moved)
            self.assertAlmostEqual(solution.slope, original.slope, places=12)
            self.assertAlmostEqual(solution.intercept, original.intercept+dy-original.slope*dx, places=10)
            self.assertAlmostEqual(solution.cost, original.cost, places=11)

    def test_physical_region_instrumentation_preserves_exact_output(self):
        cases = (
            (((0.0, FiniteInterval(1, 2)), (10.0, FiniteInterval(1, 2))), 0.1),
            (((0.0, FiniteInterval.exact(1)), (10.0, FiniteInterval.exact(1))), 0.1),
            (((0.0, FiniteInterval.exact(1)),), 0.1),
            (((0.0, FiniteInterval(1, 2)), (10.0, FiniteInterval(20, 30))), 0.1),
        )
        for intervals, cap in cases:
            work = empty_work()
            expected = physical_line_region(intervals, cap, 5.0)
            self.assertEqual(_physical_line_region(intervals, cap, 5.0, work=work), expected)
            self.assertGreater(work['polygon_clip_count'], 0)
            self.assertGreater(work['polygon_vertex_evaluation_count'], 0)
            self.assertLessEqual(work['polygon_clip_count'], 2*len(intervals))

    def test_polygon_counts_are_actual_calls_including_failed_clipping(self):
        for tail in (102.0, 103.0):
            points = points_for((100.0,) * 9 + (tail,) * 2)
            with patch('x5crop.detection.photo_geometry.robust_line_fit._clip_line_region', wraps=_clip_line_region) as clip:
                result = fit_complete_transition_line(points, 10.0, SPEC)
            self.assertEqual(result.work.polygon_clip_count, clip.call_count)
            actual_distances = sum(len(call.args[0])+1 if call.args[0] else 0 for call in clip.call_args_list)
            self.assertEqual(result.work.polygon_vertex_evaluation_count, actual_distances)
            self.check_work_bound(result.work)


if __name__ == '__main__':
    unittest.main()
