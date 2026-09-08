from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import math
import unittest

import numpy as np
from scipy.optimize import linprog

from tools.regression.report_validation import (
    _validate_sequence_output_line_provenance,
    _validate_sequence_physical_line_regions,
)
from x5crop.report.read_models import typed_read_model
from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryTransition
from x5crop.detection.photo_geometry.measurement_points import TransitionPoint
from x5crop.detection.photo_geometry.robust_line_fit import (
    physical_line_region as compile_physical_line_region,
    physical_line_region_at_positions,
    physical_slope_interval,
)
from x5crop.detection.photo_geometry.observations import build_sequence_edge_observations
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile, BoundaryEdgeMeasurementBasis, ProfileRun,
)


def _points(
    traces: tuple[int, ...],
    intervals: tuple[tuple[float, float], ...],
) -> tuple[TransitionPoint, ...]:
    result = []
    for ordinal, (trace, bounds) in enumerate(zip(traces, intervals, strict=True)):
        interval = FiniteInterval(*bounds)
        transition = PhotoBoundaryTransition(
            transition_id=ObservationId(f"physical-line:{ordinal}"),
            query_id="query:physical-line",
            trace_ordinal=ordinal,
            trace_coordinate_px=trace,
            canonical_coordinate_px=interval.center,
            localization_interval_px=FiniteInterval.exact(interval.center),
            physical_position_interval_px=interval,
            gradient_z=10.0,
            tone_z=10.0,
            texture_z=1.0,
            left_tone_mean=10.0,
            right_tone_mean=30.0,
            left_texture_mean=1.0,
            right_texture_mean=5.0,
            polarity=1,
            peak_width_px=1.0,
            prominence=10.0,
            local_noise=0.0,
        )
        result.append(TransitionPoint(transition, float(trace), interval.center))
    return tuple(result)


def physical_line_region(points, maximum_slope, reference_trace_px):
    return compile_physical_line_region(
        tuple((point.trace, point.transition.physical_position_interval_px) for point in points),
        maximum_slope, reference_trace_px,
    )


class PhysicalLineRegionContractTest(unittest.TestCase):
    def test_output_line_provenance_rejects_family_and_width_substitution(self) -> None:
        edge = {
            "observation_id": "registered-line",
            "reference_trace_px": 50.0,
            "fit_position_interval_px": {"minimum": 99.0, "maximum": 101.0},
            "fit_direction_interval_degrees": {"minimum": -1.0, "maximum": 1.0},
            "physical_line_region": {
                "reference_trace_px": 50.0,
                "vertices": [[99.0, 0.0], [100.0, 0.02], [101.0, 0.0]],
            },
        }
        for direction in (-1, 1):
            evidence = {**deepcopy(edge), "physical_position_offset_px": {
                "minimum": 0.0, "maximum": 0.0,
            }}
            binding = {"observation_id": edge["observation_id"], "line_evidence": evidence}
            fit = {"role_bindings": [binding, None],
                   "pitch_fit": {"frame_width_px": {"minimum": 90.0, "maximum": 110.0}},
                   "template": {"direction": direction}}
            inferred = deepcopy(evidence)
            shifts = sorted((90.0 * direction, 110.0 * direction))
            for field in ("fit_position_interval_px", "physical_position_offset_px"):
                inferred[field]["minimum"] += shifts[0]
                inferred[field]["maximum"] += shifts[1]
            lane = {
                "observations": {"sequence_edges": [edge], "cross_height_edges": [],
                                 "broad_material_edges": []},
                "phase_competition": {"best": fit, "runner_up": None},
                "placement_competition": {"placements": [{"sequence_fit": fit, "frames": [{
                    "start": {"line_evidence": evidence}, "end": {"line_evidence": inferred},
                    "top": {"line_evidence": None}, "bottom": {"line_evidence": None},
                }]}]},
            }
            _validate_sequence_output_line_provenance(lane)
            for mutation in ("raw_family", "width_twice", "fixed_departure"):
                changed = deepcopy(lane)
                frame = changed["placement_competition"]["placements"][0]["frames"][0]
                if mutation == "raw_family":
                    frame["end"]["line_evidence"]["physical_line_region"]["vertices"].pop()
                elif mutation == "width_twice":
                    frame["end"]["line_evidence"]["physical_position_offset_px"]["maximum"] += 90.0
                else:
                    frame["start"]["local_outward_departure_px"] = 0.0
                with self.subTest(direction=direction, mutation=mutation), self.assertRaises(ValueError):
                    _validate_sequence_output_line_provenance(changed)

    def test_position_offset_and_reachable_slice_keep_correlated_slopes(self) -> None:
        raw = PhysicalLineRegion(260.0, ((190.0, 0.0), (200.0, -0.04),
                                         (210.0, 0.0), (200.0, 0.04)))
        clipped = physical_line_region_at_positions(raw, FiniteInterval.exact(0.0),
                                                     FiniteInterval.exact(200.0))
        self.assertIsNotNone(clipped)
        assert clipped is not None
        self.assertAlmostEqual(clipped.project(510.0).maximum, 210.0)
        self.assertAlmostEqual(clipped.project(10.0).minimum, 190.0)
        # At the outermost reachable shifted position only p=210,W=110
        # survives; the independent slope maximum cannot accompany it.
        shifted = physical_line_region_at_positions(raw, FiniteInterval(90.0, 110.0),
                                                     FiniteInterval.exact(320.0))
        self.assertIsNotNone(shifted)
        assert shifted is not None
        self.assertEqual(shifted.project(510.0), FiniteInterval.exact(320.0))
        self.assertIsNone(physical_line_region_at_positions(
            raw, FiniteInterval.exact(0.0), FiniteInterval(300.0, 400.0),
        ))

    def test_sequence_full_position_retains_asymmetric_physical_states(self) -> None:
        points = _points((0, 50, 100), ((99.0, 120.0),) * 3)
        transitions = tuple(
            replace(point.transition, canonical_coordinate_px=100.0,
                    localization_interval_px=FiniteInterval(99.0, 101.0))
            for point in points
        )
        run = ProfileRun(
            run_id="asymmetric-physical-line",
            coordinate_interval_px=FiniteInterval(80.0, 130.0),
            transition_ids=tuple(item.transition_id for item in transitions),
            trace_coordinates_px=(0, 50, 100),
            role_hint=None,
            qualified_anchor_roles=(),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=10.0,
        )
        edges = build_sequence_edge_observations(
            BasicAxisProfile("sequence", 200, (0, 50, 100), (run,)),
            {str(item.transition_id): item for item in transitions},
            reference_trace_px=50.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_basis=BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        self.assertEqual(len(edges), 1)
        edge = edges[0]
        self.assertTrue(edge.full_position_interval_px.contains(119.0))
        self.assertAlmostEqual(edge.canonical_position_px, 100.0)
        self.assertLess(edge.fit_position_interval_px.width, 2.0)
        self.assertIsNotNone(edge.physical_line_region)
        assert edge.physical_line_region is not None
        self.assertAlmostEqual(edge.physical_line_region.project(50.0).maximum, 120.0)
        lane = {"lane_id": "line-test", "observations": {
            "sequence_edges": [typed_read_model(edge)],
            "cross_height_edges": [], "broad_material_edges": [],
        }}
        queries = [{"query": {"lane_id": "line-test"},
                    "transitions": typed_read_model(transitions),
                    "cross_height_transitions": [], "broad_material_transitions": []}]
        _validate_sequence_physical_line_regions(lane, queries)
        for mutation in ("missing_vertex", "missing_region", "narrowed_position", "undirected"):
            changed = deepcopy(lane)
            target = changed["observations"]["sequence_edges"][0]
            if mutation == "missing_vertex":
                target["physical_line_region"]["vertices"].pop()
            elif mutation == "missing_region":
                target["physical_line_region"] = None
            elif mutation == "narrowed_position":
                target["full_position_interval_px"] = {"minimum": 97.0, "maximum": 103.0}
            else:
                target["canonical_direction_degrees"] = None
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _validate_sequence_physical_line_regions(changed, queries)

    def test_projection_keeps_position_and_slope_correlated(self) -> None:
        points = _points((0, 100), ((100.0, 101.0), (100.0, 101.0)))
        region = physical_line_region(points, 0.1, 0.0)
        self.assertIsNotNone(region)
        assert region is not None
        for trace in (0.0, 25.0, 50.0, 100.0):
            projection = region.project(trace)
            self.assertAlmostEqual(projection.minimum, 100.0)
            self.assertAlmostEqual(projection.maximum, 101.0)
        # Marginal position=101 and slope=.01 would wrongly export x=102.
        self.assertLess(region.project(100.0).maximum, 102.0)
        self.assertAlmostEqual(region.project(200.0).minimum, 99.0)
        self.assertAlmostEqual(region.project(200.0).maximum, 102.0)

    def test_point_segment_and_empty_sets_have_distinct_meaning(self) -> None:
        point = physical_line_region(
            _points((0, 100), ((100.0, 100.0), (101.0, 101.0))),
            0.1,
            0.0,
        )
        self.assertIsNotNone(point)
        assert point is not None
        self.assertAlmostEqual(point.project(50.0).minimum, 100.5)
        self.assertAlmostEqual(point.project(50.0).maximum, 100.5)
        segment = physical_line_region(
            _points((0, 100), ((100.0, 100.0), (100.0, 101.0))),
            0.1,
            0.0,
        )
        self.assertIsNotNone(segment)
        assert segment is not None
        self.assertAlmostEqual(segment.project(50.0).minimum, 100.0)
        self.assertAlmostEqual(segment.project(50.0).maximum, 100.5)
        impossible = _points(
            (0, 50, 100), ((100.0, 101.0), (102.0, 103.0), (100.0, 101.0))
        )
        self.assertIsNone(physical_line_region(impossible, 0.1, 0.0))
        self.assertIsNone(physical_slope_interval(impossible, 0.1))

    def test_touching_constraints_keep_a_point_after_large_coordinate_cancellation(self) -> None:
        points = _points(
            (719, 899, 1259, 1439, 1619, 1799),
            ((10469.5, 10510.5), (10474.5, 10506.5),
             (10484.5, 10487.5), (10482.5, 10483.5),
             (10470.5, 10493.5), (10464.5, 10472.5)),
        )
        region = physical_line_region(points, math.tan(math.radians(4.0)), 1398.0)
        self.assertIsNotNone(region)
        assert region is not None
        for position, slope in region.vertices:
            self.assertAlmostEqual(position, 10483.638888888889)
            self.assertAlmostEqual(slope, -1.0 / 36.0)

    def test_projection_is_reference_invariant_and_matches_independent_lp(self) -> None:
        rng = np.random.default_rng(20260908)
        maximum_slope = math.tan(math.radians(4.0))
        for case in range(12):
            traces = tuple(int(value) for value in sorted(rng.choice(1000, 10, replace=False)))
            slope = rng.uniform(-0.03, 0.03)
            intervals = tuple(
                (500.0 + slope * trace - rng.uniform(0.0, 25.0),
                 500.0 + slope * trace + rng.uniform(0.0, 25.0))
                for trace in traces
            )
            points = _points(traces, intervals)
            rows, limits = [], []
            for trace, (minimum, maximum) in zip(traces, intervals, strict=True):
                rows.extend(((1.0, float(trace)), (-1.0, -float(trace))))
                limits.extend((maximum, -minimum))
            slopes = physical_slope_interval(points, maximum_slope)
            assert slopes is not None
            for reference in (0.0, 500.0, 1300.0):
                region = physical_line_region(points, maximum_slope, reference)
                self.assertIsNotNone(region)
                assert region is not None
                self.assertLessEqual(len(region.vertices), 2 * len(points) + 4)
                self.assertAlmostEqual(min(s for _, s in region.vertices), slopes.minimum)
                self.assertAlmostEqual(max(s for _, s in region.vertices), slopes.maximum)
                for trace in (-200.0, 250.0, 800.0, 1300.0):
                    actual = region.project(trace)
                    for sign, endpoint in ((1.0, actual.minimum), (-1.0, actual.maximum)):
                        result = linprog(
                            (sign, sign * trace), A_ub=rows, b_ub=limits,
                            bounds=((None, None), (-maximum_slope, maximum_slope)),
                            method="highs",
                        )
                        with self.subTest(case=case, reference=reference, trace=trace, sign=sign):
                            self.assertTrue(result.success)
                            self.assertAlmostEqual(endpoint, sign * result.fun, places=7)


if __name__ == "__main__":
    unittest.main()
