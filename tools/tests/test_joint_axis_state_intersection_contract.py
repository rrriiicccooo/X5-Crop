from __future__ import annotations

from dataclasses import dataclass
import math
import random
from types import SimpleNamespace
import unittest

from scipy.optimize import linprog

from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.detector import _shared_geometry
from x5crop.detection.photo_geometry.joint_axis_geometry import JointAxisGeometry
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry


@dataclass(frozen=True)
class _Operation:
    kind: str
    interval: FiniteInterval
    q_coefficient: float = 0.0
    scale_coefficient: float = 0.0
    observation_ids: tuple[ObservationId, ...] = ()


@dataclass(frozen=True)
class _LinearOracle:
    """Independent two-variable LP constraints for one joint axis state."""

    rows: tuple[tuple[tuple[float, float], float], ...]

    @classmethod
    def base(
        cls,
        *,
        scale_interval: PositiveInterval,
        factor_interval: PositiveInterval,
    ) -> "_LinearOracle":
        scale_minimum, scale_maximum = (
            scale_interval.minimum,
            scale_interval.maximum,
        )
        factor_minimum, factor_maximum = (
            factor_interval.minimum,
            factor_interval.maximum,
        )
        # x is scale and y is normalized physical extent.  Every row is
        # constructed directly from the source constraints, independently of
        # the production polygon representation.
        return cls(
            (
                ((-1.0, 0.0), -scale_minimum),
                ((1.0, 0.0), scale_maximum),
                ((factor_minimum, -1.0), 0.0),
                ((-factor_maximum, 1.0), 0.0),
            )
        )

    def with_affine_interval(
        self,
        interval: FiniteInterval,
        *,
        q_coefficient: float,
        scale_coefficient: float,
    ) -> "_LinearOracle":
        rows = (
            ((-scale_coefficient, -q_coefficient), -interval.minimum),
            ((scale_coefficient, q_coefficient), interval.maximum),
        )
        return _LinearOracle(self.rows + rows)

    def objective(self, direction: tuple[float, float]) -> float | None:
        result = linprog(
            direction,
            A_ub=[row for row, _ in self.rows],
            b_ub=[limit for _, limit in self.rows],
            bounds=((None, None), (None, None)),
            method="highs",
        )
        if result.status == 2:
            return None
        if not result.success:
            raise AssertionError(
                f"independent LP failed unexpectedly: {result.message}"
            )
        return float(sum(coefficient * value for coefficient, value in zip(
            direction, result.x, strict=True
        )))

    def feasible(self) -> bool:
        return self.objective((0.0, 0.0)) is not None

    def merged(self, other: "_LinearOracle") -> "_LinearOracle":
        return _LinearOracle(self.rows + other.rows)


_DIRECTIONS: tuple[tuple[float, float], ...] = tuple(
    (math.cos(index * math.pi / 8.0), math.sin(index * math.pi / 8.0))
    for index in range(16)
)


def _build_axis(
    operations: tuple[_Operation, ...],
    *,
    axis_name: str = "height",
    design_extent_mm: float = 24.0,
    scale_interval: PositiveInterval = PositiveInterval(10.0, 11.0),
    factor_interval: PositiveInterval = PositiveInterval(0.9, 1.1),
) -> tuple[JointAxisGeometry, _LinearOracle]:
    state = JointAxisGeometry.create(
        axis_name=axis_name,
        design_extent_mm=design_extent_mm,
        scale_interval_px_per_mm=scale_interval,
        factor_interval=factor_interval,
    )
    oracle = _LinearOracle.base(
        scale_interval=scale_interval,
        factor_interval=factor_interval,
    )
    for operation in operations:
        if operation.kind == "inferred":
            state = state.intersect_inferred_extent(operation.interval)
            oracle = oracle.with_affine_interval(
                operation.interval,
                q_coefficient=design_extent_mm,
                scale_coefficient=0.0,
            )
        elif operation.kind == "observed":
            state = state.intersect_observed_extent(
                operation.interval,
                observation_ids=operation.observation_ids,
            )
            oracle = oracle.with_affine_interval(
                operation.interval,
                q_coefficient=design_extent_mm,
                scale_coefficient=0.0,
            )
        elif operation.kind == "affine":
            state = state.intersect_affine_observation(
                operation.interval,
                q_coefficient=operation.q_coefficient,
                scale_coefficient=operation.scale_coefficient,
                observation_ids=operation.observation_ids,
            )
            oracle = oracle.with_affine_interval(
                operation.interval,
                q_coefficient=operation.q_coefficient,
                scale_coefficient=operation.scale_coefficient,
            )
        else:
            raise AssertionError(f"unknown operation kind: {operation.kind}")
    return state, oracle


def _support(
    state: JointAxisGeometry,
    direction: tuple[float, float],
) -> tuple[float, float]:
    values = tuple(
        direction[0] * scale + direction[1] * normalized
        for scale, normalized in state.vertices
    )
    return min(values), max(values)


def _assert_matches_oracle(
    testcase: unittest.TestCase,
    state: JointAxisGeometry,
    oracle: _LinearOracle,
    *,
    directions: tuple[tuple[float, float], ...] = _DIRECTIONS,
) -> None:
    testcase.assertTrue(oracle.feasible())
    for direction in directions:
        expected_minimum = oracle.objective(direction)
        expected_maximum = oracle.objective(tuple(-value for value in direction))
        testcase.assertIsNotNone(expected_minimum)
        testcase.assertIsNotNone(expected_maximum)
        actual_minimum, actual_maximum = _support(state, direction)
        testcase.assertTrue(
            math.isclose(
                actual_minimum,
                expected_minimum,
                rel_tol=5.0e-9,
                abs_tol=5.0e-8,
            ),
            msg=(
                f"minimum support mismatch for direction {direction}: "
                f"actual={actual_minimum}, expected={expected_minimum}"
            ),
        )
        testcase.assertTrue(
            math.isclose(
                actual_maximum,
                -expected_maximum,
                rel_tol=5.0e-9,
                abs_tol=5.0e-8,
            ),
            msg=(
                f"maximum support mismatch for direction {direction}: "
                f"actual={actual_maximum}, expected={-expected_maximum}"
            ),
        )


def _assert_geometrically_equal(
    testcase: unittest.TestCase,
    left: JointAxisGeometry,
    right: JointAxisGeometry,
) -> None:
    for direction in _DIRECTIONS:
        left_minimum, left_maximum = _support(left, direction)
        right_minimum, right_maximum = _support(right, direction)
        testcase.assertTrue(
            math.isclose(left_minimum, right_minimum, rel_tol=5.0e-9, abs_tol=5.0e-8)
        )
        testcase.assertTrue(
            math.isclose(left_maximum, right_maximum, rel_tol=5.0e-9, abs_tol=5.0e-8)
        )


class JointAxisStateIntersectionContractTest(unittest.TestCase):
    def test_self_intersection_is_idempotent_and_keeps_derived_provenance(self) -> None:
        affine_id = ObservationId("typed-affine:height")
        operations = (
            _Operation("inferred", FiniteInterval(245.0, 250.0)),
            _Operation(
                "affine",
                FiniteInterval(238.0, 243.0),
                q_coefficient=24.0,
                scale_coefficient=-1.0,
                observation_ids=(affine_id,),
            ),
        )
        state, oracle = _build_axis(operations)
        self.assertEqual(state.observation_ids, (affine_id,))
        self.assertIsNone(state.observed_normalized_extent)

        intersected = state.intersect_state(state)

        _assert_matches_oracle(self, intersected, oracle)
        _assert_geometrically_equal(self, state, intersected)
        self.assertEqual(intersected.observation_ids, (affine_id,))
        self.assertIsNone(intersected.observed_normalized_extent)

    def test_metadata_intersection_and_each_input_constraint_are_retained(self) -> None:
        left_id = ObservationId("direct:height:left")
        right_id = ObservationId("direct:height:right")
        left, left_oracle = _build_axis(
            (
                _Operation(
                    "observed",
                    FiniteInterval(245.0, 270.0),
                    observation_ids=(left_id,),
                ),
                _Operation("inferred", FiniteInterval(250.0, 275.0)),
            )
        )
        right, right_oracle = _build_axis(
            (
                _Operation(
                    "observed",
                    FiniteInterval(255.0, 280.0),
                    observation_ids=(right_id,),
                ),
                _Operation(
                    "affine",
                    FiniteInterval(255.0, 270.0),
                    q_coefficient=24.0,
                    scale_coefficient=1.0,
                    observation_ids=(right_id,),
                ),
            )
        )
        shared = left.intersect_state(right)
        merged_oracle = left_oracle.merged(right_oracle)

        _assert_matches_oracle(self, shared, merged_oracle)
        self.assertEqual(
            shared.observed_normalized_extent,
            FiniteInterval(255.0 / 24.0, 270.0 / 24.0),
        )
        self.assertEqual(shared.observation_ids, (left_id, right_id))
        for direction in _DIRECTIONS:
            shared_minimum, shared_maximum = _support(shared, direction)
            for input_state in (left, right):
                input_minimum, input_maximum = _support(input_state, direction)
                self.assertGreaterEqual(shared_minimum + 1.0e-8, input_minimum)
                self.assertLessEqual(shared_maximum - 1.0e-8, input_maximum)

    def test_correlated_disjoint_polygons_rejected_when_marginals_overlap(self) -> None:
        left, left_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(0.2, 0.3),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("band:left"),),
                ),
            )
        )
        right, right_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(0.4, 0.5),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("band:right"),),
                ),
            )
        )
        self.assertTrue(left_oracle.feasible())
        self.assertTrue(right_oracle.feasible())
        self.assertEqual(left.feasible_scale_interval(), right.feasible_scale_interval())
        left_extent = left.extent_projection_px()
        right_extent = right.extent_projection_px()
        self.assertLess(
            max(left_extent.minimum, right_extent.minimum),
            min(left_extent.maximum, right_extent.maximum),
        )
        self.assertFalse(left_oracle.merged(right_oracle).feasible())

        with self.assertRaises(ValueError):
            left.intersect_state(right)

    def test_closed_tangent_affine_bands_are_not_dropped(self) -> None:
        left, left_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(0.2, 0.3),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("tangent:left"),),
                ),
            )
        )
        right, right_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(0.3, 0.4),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("tangent:right"),),
                ),
            )
        )
        oracle = left_oracle.merged(right_oracle)
        self.assertTrue(oracle.feasible())
        tangent = left.intersect_state(right)
        _assert_matches_oracle(self, tangent, oracle)
        self.assertTrue(
            all(math.isclose(normalized - scale, 0.3, abs_tol=1.0e-8)
                for scale, normalized in tangent.vertices)
        )

    def test_point_line_and_exact_factor_states_remain_closed(self) -> None:
        point_left, point_left_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(0.2, 0.3),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("point:left"),),
                ),
            ),
            scale_interval=PositiveInterval.exact(10.5),
        )
        point_right, point_right_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(0.3, 0.4),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("point:right"),),
                ),
            ),
            scale_interval=PositiveInterval.exact(10.5),
        )
        point = point_left.intersect_state(point_right)
        _assert_matches_oracle(self, point, point_left_oracle.merged(point_right_oracle))
        point_scale = point.feasible_scale_interval()
        point_extent = point.normalized_extent_projection()
        self.assertAlmostEqual(point_scale.minimum, 10.5)
        self.assertAlmostEqual(point_scale.maximum, 10.5)
        self.assertAlmostEqual(point_extent.minimum, 10.8)
        self.assertAlmostEqual(point_extent.maximum, 10.8)
        self.assertTrue(
            all(
                math.isclose(scale, 10.5, abs_tol=1.0e-8)
                and math.isclose(normalized, 10.8, abs_tol=1.0e-8)
                for scale, normalized in point.vertices
            )
        )

        line_scale, line_scale_oracle = _build_axis(
            (), scale_interval=PositiveInterval.exact(10.5)
        )
        line_scale = line_scale.intersect_state(line_scale)
        _assert_matches_oracle(self, line_scale, line_scale_oracle)
        self.assertEqual(line_scale.feasible_scale_interval(), PositiveInterval.exact(10.5))
        self.assertAlmostEqual(line_scale.normalized_extent_projection().minimum, 9.45)
        self.assertAlmostEqual(line_scale.normalized_extent_projection().maximum, 11.55)

        line_factor, line_factor_oracle = _build_axis(
            (), factor_interval=PositiveInterval.exact(1.0)
        )
        line_factor = line_factor.intersect_state(line_factor)
        _assert_matches_oracle(self, line_factor, line_factor_oracle)
        for scale, normalized in line_factor.vertices:
            self.assertAlmostEqual(normalized, scale)

        point_state, point_oracle = _build_axis(
            (),
            scale_interval=PositiveInterval.exact(10.5),
            factor_interval=PositiveInterval.exact(1.0),
        )
        point_state = point_state.intersect_state(point_state)
        _assert_matches_oracle(self, point_state, point_oracle)
        self.assertTrue(
            all(
                math.isclose(scale, 10.5, abs_tol=1.0e-8)
                and math.isclose(normalized, 10.5, abs_tol=1.0e-8)
                for scale, normalized in point_state.vertices
            )
        )

    def test_nonidentical_segment_and_point_intersections_match_lp_in_both_orders(self) -> None:
        full, full_oracle = _build_axis(())
        diagonal, diagonal_oracle = _build_axis(
            (), factor_interval=PositiveInterval.exact(1.05)
        )
        diagonal_oracle = full_oracle.merged(diagonal_oracle)
        for left, right in ((full, diagonal), (diagonal, full)):
            with self.subTest(right_kind="diagonal-segment", left_first=left is full):
                result = left.intersect_state(right)
                _assert_matches_oracle(self, result, diagonal_oracle)
                self.assertEqual(
                    result.feasible_scale_interval(),
                    PositiveInterval(10.0, 11.0),
                )
                self.assertTrue(
                    all(
                        math.isclose(normalized, 1.05 * scale, abs_tol=1.0e-8)
                        for scale, normalized in result.vertices
                    )
                )

        point, point_oracle = _build_axis(
            (),
            scale_interval=PositiveInterval.exact(10.5),
            factor_interval=PositiveInterval.exact(1.05),
        )
        point_oracle = full_oracle.merged(point_oracle)
        for left, right in ((full, point), (point, full)):
            with self.subTest(right_kind="point", left_first=left is full):
                result = left.intersect_state(right)
                _assert_matches_oracle(self, result, point_oracle)
                self.assertAlmostEqual(result.feasible_scale_interval().minimum, 10.5)
                self.assertAlmostEqual(result.feasible_scale_interval().maximum, 10.5)
                self.assertTrue(
                    all(
                        math.isclose(scale, 10.5, abs_tol=1.0e-8)
                        and math.isclose(normalized, 11.025, abs_tol=1.0e-8)
                        for scale, normalized in result.vertices
                    )
                )

        narrow_strip, strip_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(-0.1, 0.1),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("separated-strip"),),
                ),
            )
        )
        separated_point, separated_point_oracle = _build_axis(
            (),
            scale_interval=PositiveInterval.exact(10.5),
            factor_interval=PositiveInterval.exact(22.0 / 21.0),
        )
        self.assertFalse(strip_oracle.merged(separated_point_oracle).feasible())
        for left, right in (
            (narrow_strip, separated_point),
            (separated_point, narrow_strip),
        ):
            with self.assertRaises(ValueError):
                left.intersect_state(right)

    def test_random_slanted_bands_match_independent_lp_oracle(self) -> None:
        rng = random.Random(20261124)
        tested = 0
        feasible_cases = 0
        infeasible_cases = 0
        for case_index in range(40):
            def random_operations(prefix: str) -> tuple[_Operation, ...]:
                scale = rng.uniform(10.1, 10.9)
                factor = rng.uniform(0.93, 1.07)
                normalized = scale * factor
                result = [
                    _Operation(
                        "affine",
                        FiniteInterval(
                            24.0 * normalized - 1.0 * scale - rng.uniform(0.3, 1.2),
                            24.0 * normalized - 1.0 * scale + rng.uniform(0.3, 1.2),
                        ),
                        q_coefficient=24.0,
                        scale_coefficient=-1.0,
                        observation_ids=(ObservationId(f"{prefix}:slanted"),),
                    )
                ]
                for ordinal in range(rng.randint(1, 3)):
                    if rng.random() < 0.45:
                        half_width = rng.uniform(0.5, 5.0)
                        result.append(
                            _Operation(
                                "inferred",
                                FiniteInterval(
                                    24.0 * normalized - half_width,
                                    24.0 * normalized + half_width,
                                ),
                            )
                        )
                    else:
                        q_coefficient = rng.choice((1.0, 12.0, 24.0, -8.0))
                        scale_coefficient = rng.choice((-2.0, -1.0, 0.5, 1.0, 2.0))
                        expression = q_coefficient * normalized + scale_coefficient * scale
                        lower = rng.uniform(0.3, 1.8)
                        upper = rng.uniform(0.3, 1.8)
                        result.append(
                            _Operation(
                                "affine",
                                FiniteInterval(expression - lower, expression + upper),
                                q_coefficient=q_coefficient,
                                scale_coefficient=scale_coefficient,
                                observation_ids=(ObservationId(f"{prefix}:affine:{ordinal}"),),
                            )
                        )
                return tuple(result)

            left, left_oracle = _build_axis(random_operations(f"random:{case_index}:left"))
            right, right_oracle = _build_axis(random_operations(f"random:{case_index}:right"))
            merged_oracle = left_oracle.merged(right_oracle)
            tested += 1
            if merged_oracle.feasible():
                feasible_cases += 1
                shared = left.intersect_state(right)
                _assert_matches_oracle(
                    self,
                    shared,
                    merged_oracle,
                    directions=_DIRECTIONS[:10],
                )
            else:
                infeasible_cases += 1
                with self.assertRaises(ValueError):
                    left.intersect_state(right)
        self.assertEqual(tested, 40)
        self.assertGreater(feasible_cases, 0)
        self.assertGreater(infeasible_cases, 0)

    def test_intersection_order_and_association_preserve_feasible_geometry(self) -> None:
        a, a_oracle = _build_axis(
            (
                _Operation("inferred", FiniteInterval(245.0, 265.0)),
                _Operation(
                    "affine",
                    FiniteInterval(239.0, 244.0),
                    q_coefficient=24.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("order:a"),),
                ),
            )
        )
        b, b_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(260.0, 265.0),
                    q_coefficient=24.0,
                    scale_coefficient=1.0,
                    observation_ids=(ObservationId("order:b"),),
                ),
            )
        )
        c, c_oracle = _build_axis(
            (
                _Operation(
                    "affine",
                    FiniteInterval(-0.4, 0.4),
                    q_coefficient=1.0,
                    scale_coefficient=-1.0,
                    observation_ids=(ObservationId("order:c"),),
                ),
            )
        )
        oracle = a_oracle.merged(b_oracle).merged(c_oracle)
        self.assertTrue(oracle.feasible())
        ab = a.intersect_state(b)
        ba = b.intersect_state(a)
        abc_left = ab.intersect_state(c)
        abc_right = a.intersect_state(b.intersect_state(c))
        _assert_matches_oracle(self, ab, a_oracle.merged(b_oracle))
        _assert_matches_oracle(self, ba, a_oracle.merged(b_oracle))
        _assert_matches_oracle(self, abc_left, oracle)
        _assert_matches_oracle(self, abc_right, oracle)
        _assert_geometrically_equal(self, ab, ba)
        _assert_geometrically_equal(self, abc_left, abc_right)
        self.assertEqual(abc_left.observation_ids, abc_right.observation_ids)

    def test_two_source_lanes_keep_inferred_width_height_and_fixed_dimensions(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        shared_scale = PositiveInterval(10.0, 11.0)
        initial = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=shared_scale,
            height_scale_px_per_mm=shared_scale,
        )
        width_one, width_one_oracle = _build_axis(
            (_Operation("inferred", FiniteInterval(360.0, 370.0)),),
            axis_name="width",
            design_extent_mm=36.0,
            scale_interval=shared_scale,
            factor_interval=PositiveInterval(*frame.width_factor_bounds),
        )
        width_two, width_two_oracle = _build_axis(
            (_Operation("inferred", FiniteInterval(365.0, 375.0)),),
            axis_name="width",
            design_extent_mm=36.0,
            scale_interval=shared_scale,
            factor_interval=PositiveInterval(*frame.width_factor_bounds),
        )
        height_one, height_one_oracle = _build_axis(
            (_Operation("inferred", FiniteInterval(240.0, 250.0)),),
            axis_name="height",
            design_extent_mm=24.0,
            scale_interval=shared_scale,
            factor_interval=PositiveInterval(*frame.height_factor_bounds),
        )
        height_two, height_two_oracle = _build_axis(
            (_Operation("inferred", FiniteInterval(245.0, 255.0)),),
            axis_name="height",
            design_extent_mm=24.0,
            scale_interval=shared_scale,
            factor_interval=PositiveInterval(*frame.height_factor_bounds),
        )
        lane_one = SourceScanGeometry.from_axis_states(frame, width_one, height_one)
        lane_two = SourceScanGeometry.from_axis_states(frame, width_two, height_two)
        shared = lane_one.intersect_source_state(lane_two)

        _assert_matches_oracle(
            self,
            shared.width_state,
            width_one_oracle.merged(width_two_oracle),
        )
        _assert_matches_oracle(
            self,
            shared.height_state,
            height_one_oracle.merged(height_two_oracle),
        )
        self.assertEqual(shared.width_state.observation_ids, ())
        self.assertEqual(shared.height_state.observation_ids, ())
        fixed = shared.fixed_output_size
        self.assertAlmostEqual(
            fixed.frame_width_px,
            frame.frame_width_mm * shared.width_state.canonical_state()[1],
        )
        self.assertAlmostEqual(
            fixed.frame_height_px,
            frame.frame_height_mm * shared.height_state.canonical_state()[1],
        )
        self.assertGreater(fixed.frame_width_px, 0.0)
        self.assertGreater(fixed.frame_height_px, 0.0)
        self.assertNotEqual(lane_one.width_state.extent_projection_px(),
                            lane_two.width_state.extent_projection_px())
        self.assertNotEqual(lane_one.height_state.extent_projection_px(),
                            lane_two.height_state.extent_projection_px())
        self.assertIsNotNone(initial.fixed_output_size)

    def test_detector_drops_conflicting_inferred_lanes_without_rebuilding_metadata(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        shared_scale = PositiveInterval(10.0, 11.0)
        initial = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=shared_scale,
            height_scale_px_per_mm=shared_scale,
        )
        width_id = ObservationId("same-direct-width")
        height_id = ObservationId("same-direct-height")

        def lane(
            width_interval: FiniteInterval,
            height_interval: FiniteInterval,
        ) -> SourceScanGeometry:
            width = initial.width_state.intersect_observed_extent(
                FiniteInterval(350.0, 410.0),
                observation_ids=(width_id,),
            ).intersect_inferred_extent(width_interval)
            height = initial.height_state.intersect_observed_extent(
                FiniteInterval(230.0, 280.0),
                observation_ids=(height_id,),
            ).intersect_inferred_extent(height_interval)
            return SourceScanGeometry.from_axis_states(frame, width, height)

        conflicting_left = lane(
            FiniteInterval(360.0, 365.0),
            FiniteInterval(240.0, 245.0),
        )
        conflicting_right = lane(
            FiniteInterval(380.0, 385.0),
            FiniteInterval(260.0, 265.0),
        )
        for axis_name in ("width_state", "height_state"):
            left_state = getattr(conflicting_left, axis_name)
            right_state = getattr(conflicting_right, axis_name)
            self.assertEqual(
                left_state.observed_normalized_extent,
                right_state.observed_normalized_extent,
            )
            self.assertEqual(left_state.observation_ids, right_state.observation_ids)
        self.assertIsNone(
            _shared_geometry(
                (
                    SimpleNamespace(source_scan_geometry=conflicting_left),
                    SimpleNamespace(source_scan_geometry=conflicting_right),
                )
            )
        )

        common_left = lane(
            FiniteInterval(360.0, 380.0),
            FiniteInterval(240.0, 260.0),
        )
        common_right = lane(
            FiniteInterval(370.0, 390.0),
            FiniteInterval(250.0, 270.0),
        )
        shared = _shared_geometry(
            (
                SimpleNamespace(source_scan_geometry=common_left),
                SimpleNamespace(source_scan_geometry=common_right),
            )
        )
        self.assertIsNotNone(shared)
        assert shared is not None
        self.assertEqual(shared.width_state.observation_ids, (width_id,))
        self.assertEqual(shared.height_state.observation_ids, (height_id,))
        self.assertEqual(
            shared.width_state.observed_normalized_extent,
            common_left.width_state.observed_normalized_extent,
        )
        self.assertEqual(
            shared.height_state.observed_normalized_extent,
            common_left.height_state.observed_normalized_extent,
        )
        for shared_state, left_state, right_state in (
            (shared.width_state, common_left.width_state, common_right.width_state),
            (shared.height_state, common_left.height_state, common_right.height_state),
        ):
            shared_extent = shared_state.extent_projection_px()
            left_extent = left_state.extent_projection_px()
            right_extent = right_state.extent_projection_px()
            self.assertGreaterEqual(shared_extent.minimum, max(
                left_extent.minimum,
                right_extent.minimum,
            ) - 1.0e-8)
            self.assertLessEqual(shared_extent.maximum, min(
                left_extent.maximum,
                right_extent.maximum,
            ) + 1.0e-8)


if __name__ == "__main__":
    unittest.main()
