from __future__ import annotations

from dataclasses import replace
import math
import unittest

import numpy as np
from scipy.optimize import linprog

from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry.constructed_enclosure import (
    construct_cross_enclosure,
)


def _construct(traces, lower, upper, *, reference=0.0, guard=0.0, slopes=(-0.1, 0.1)):
    return construct_cross_enclosure(
        tuple(zip(traces, lower, strict=True)),
        tuple(zip(traces, upper, strict=True)),
        reference_trace_px=reference,
        slope_interval=FiniteInterval(*slopes),
        outward_guard_px=guard,
    )


class ConstructedEnclosureContractTest(unittest.TestCase):
    def test_flat_minimum_selects_zero_without_claiming_a_measured_direction(self):
        result = _construct([0., 10., 20.], [0., 0., 0.], [100., 100., 100.])
        self.assertEqual(result.slope, 0.)
        self.assertEqual(result.minimizing_slope_interval, FiniteInterval.exact(0.))
        self.assertFalse(hasattr(result, 'observation_id'))
        self.assertFalse(hasattr(result, 'role_authorized'))
        self.assertFalse(hasattr(result, 'physical_line_region'))
        for x in (0., 10., 20.):
            self.assertLessEqual(result.at_trace(x).minimum, 0.)
            self.assertGreaterEqual(result.at_trace(x).maximum, 100.)

    def test_wide_flat_minimum_keeps_the_whole_minimizing_interval(self):
        result = _construct([0., 10., 20.], [10., 0., 10.], [90., 100., 90.],
                            reference=10., slopes=(-2., 2.))
        self.assertEqual(result.minimizing_slope_interval, FiniteInterval(-1., 1.))
        self.assertEqual(result.slope, 0.)
        positive = _construct([0., 10., 20.], [10., 0., 10.], [90., 100., 90.],
                              reference=10., slopes=(.2, .7))
        self.assertEqual(positive.slope, .2)

    def test_different_interior_trace_sets_preserve_both_sides(self):
        result = construct_cross_enclosure(
            ((0., 5.), (4., 0.), (10., 5.)), ((0., 100.), (7., 120.), (10., 100.)),
            reference_trace_px=5., slope_interval=FiniteInterval(-1., 1.), outward_guard_px=2.,
        )
        self.assertLessEqual(result.at_trace(4.).minimum, -2.)
        self.assertGreaterEqual(result.at_trace(7.).maximum, 122.)
        self.assertEqual(result.work.raw_recheck_count, 6)

    def test_complete_enclosure_matches_independent_linear_program_and_symmetries(self):
        rng = np.random.default_rng(27491)
        for _ in range(100):
            n = int(rng.integers(3, 101))
            traces = np.cumsum(rng.uniform(1., 50., n))
            reference = float(rng.uniform(-2000., 2000.))
            slope = float(rng.uniform(-.05, .05))
            lower = 100. + slope*(traces-reference) + rng.normal(0., 12., n)
            upper = 1000. + slope*(traces-reference) + rng.normal(0., 12., n)
            guard = float(rng.uniform(0., 20.))
            cap = .07
            result = _construct(traces, lower, upper, reference=reference, guard=guard, slopes=(-cap, cap))
            delta = traces-reference
            a = np.r_[np.column_stack((np.ones(n), np.zeros(n), delta)),
                      np.column_stack((np.zeros(n), -np.ones(n), -delta))]
            b = np.r_[lower-guard, -upper-guard]
            oracle = linprog([-1., 1., 0.], A_ub=a, b_ub=b,
                             bounds=[(None,None), (None,None), (-cap,cap)], method='highs')
            self.assertTrue(oracle.success, oracle.message)
            actual = result.maximum_position_px-result.minimum_position_px
            self.assertAlmostEqual(actual, oracle.fun, delta=1e-8)
            self.assertTrue(np.all(result.minimum_position_px+result.slope*delta <= lower-guard))
            self.assertTrue(np.all(result.maximum_position_px+result.slope*delta >= upper+guard))
            work = result.work
            self.assertEqual(work.input_constraint_count, 2*n)
            self.assertEqual(work.hull_line_count+work.hull_pop_count, 2*n)
            self.assertLessEqual(work.evaluated_slope_count, 2*n+2)
            mirrored = _construct(-traces[::-1], lower[::-1], upper[::-1],
                                  reference=-reference, guard=guard, slopes=(-cap,cap))
            flipped = _construct(traces, -upper, -lower, reference=reference, guard=guard, slopes=(-cap,cap))
            translated = _construct(traces+200., lower-37., upper-37.,
                                    reference=reference+200., guard=guard, slopes=(-cap,cap))
            self.assertAlmostEqual(mirrored.slope, -result.slope, delta=1e-10)
            self.assertAlmostEqual(flipped.slope, -result.slope, delta=1e-10)
            self.assertAlmostEqual(translated.slope, result.slope, delta=1e-10)
            self.assertAlmostEqual(mirrored.minimum_position_px, result.minimum_position_px, delta=1e-8)
            self.assertAlmostEqual(flipped.minimum_position_px, -result.maximum_position_px, delta=1e-8)
            self.assertAlmostEqual(translated.maximum_position_px, result.maximum_position_px-37., delta=1e-8)

    def test_fixed_direction_and_small_coordinate_roundoff_do_not_admit_inward_epsilon(self):
        for offset in (0., 1e6, -1e6):
            traces = np.array([0., 1234.5, 1e5]) + offset
            lower = np.array([-.00001, .005, -.00002])
            upper = lower+3.
            result = _construct(traces, lower, upper, reference=offset+1e4, slopes=(.01,.01))
            for trace, low, high in zip(traces,lower,upper,strict=True):
                interval = result.at_trace(float(trace))
                self.assertLessEqual(interval.minimum, low)
                self.assertGreaterEqual(interval.maximum, high)

    def test_invalid_or_incomplete_constraint_domains_are_rejected(self):
        valid = ((0.,0.),(1.,0.))
        for bad in ((), ((0.,0.),), ((0.,0.),(0.,1.)), ((1.,0.),(0.,0.)),
                    ((0.,0.),(1.,math.nan)), ((0.,0.),(math.inf,0.))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                construct_cross_enclosure(bad, valid, reference_trace_px=0.,
                    slope_interval=FiniteInterval(-.1,.1), outward_guard_px=0.)
        with self.assertRaises(ValueError):
            construct_cross_enclosure(valid, ((0.,100.),(2.,100.)), reference_trace_px=0.,
                slope_interval=FiniteInterval(-.1,.1), outward_guard_px=0.)
        with self.assertRaises(ValueError):
            _construct([0.,1.],[0.,0.],[1.,1.], guard=-1.)
        result = _construct([0.,1.],[0.,0.],[1.,1.])
        with self.assertRaises(ValueError):
            replace(result.work, raw_recheck_count=0)
        with self.assertRaises(ValueError):
            replace(result, slope=math.inf)


if __name__ == '__main__':
    unittest.main()
