from __future__ import annotations

import math
import random
import unittest

from x5crop.detection.photo_geometry.template_adjacency_coverage import (
    AdjacencyTraceCoverage,
    _trace_coverage,
)
from x5crop.domain import FiniteInterval


def _oracle_integer_bounds(interval: FiniteInterval) -> tuple[int, int] | None:
    minimum = int(math.ceil(interval.minimum))
    maximum = int(math.floor(interval.maximum))
    return None if maximum < minimum else (minimum, maximum)


def _oracle_trace_coverage(
    trace_position_px: int,
    required: FiniteInterval,
    intervals: tuple[tuple[FiniteInterval, str], ...],
) -> AdjacencyTraceCoverage:
    """Independent closed-integer set oracle for one registered trace."""

    required_bounds = _oracle_integer_bounds(required)
    required_count = (
        0
        if required_bounds is None
        else required_bounds[1] - required_bounds[0] + 1
    )
    covered_coordinates: set[int] = set()
    covering_query_ids: set[str] = set()
    if required_bounds is not None:
        required_start, required_end = required_bounds
        for interval, query_id in intervals:
            bounds = _oracle_integer_bounds(interval)
            if bounds is None:
                continue
            start = max(required_start, bounds[0])
            end = min(required_end, bounds[1])
            if start <= end:
                covered_coordinates.update(range(start, end + 1))
                covering_query_ids.add(query_id)

    query_ids = tuple(sorted(covering_query_ids))
    coordinates = sorted(covered_coordinates)
    runs: list[tuple[int, int]] = []
    if coordinates:
        start = previous = coordinates[0]
        for coordinate in coordinates[1:]:
            if coordinate == previous + 1:
                previous = coordinate
                continue
            runs.append((start, previous))
            start = previous = coordinate
        runs.append((start, previous))
    count = min(required_count, len(coordinates))
    complete = required_count > 0 and count == required_count
    return AdjacencyTraceCoverage(
        trace_position_px=trace_position_px,
        covering_query_ids=query_ids,
        covered_intervals_px=tuple(
            FiniteInterval(float(start), float(end)) for start, end in runs
        ),
        required_coordinate_count=required_count,
        covered_coordinate_count=count,
        complete=complete,
    )


class AdjacencyCoverageIntegerContractTest(unittest.TestCase):
    def _assert_oracle_equivalent(
        self,
        trace_position_px: int,
        required: FiniteInterval,
        intervals: tuple[tuple[FiniteInterval, str], ...],
    ) -> None:
        try:
            expected = _oracle_trace_coverage(
                trace_position_px, required, intervals
            )
        except Exception as expected_error:
            with self.assertRaises(type(expected_error)) as actual_context:
                _trace_coverage(trace_position_px, required, intervals)
            self.assertEqual(str(actual_context.exception), str(expected_error))
            return

        actual = _trace_coverage(trace_position_px, required, intervals)
        self.assertIsInstance(actual, AdjacencyTraceCoverage)
        self.assertEqual(actual, expected)
        self.assertEqual(
            actual.covering_query_ids,
            tuple(sorted(set(actual.covering_query_ids))),
        )
        self.assertTrue(
            all(isinstance(interval, FiniteInterval)
                for interval in actual.covered_intervals_px)
        )

    def test_closed_integer_rounding_and_union_edge_cases_match_oracle(self):
        cases = (
            (
                FiniteInterval(-4.75, 4.25),
                (
                    (FiniteInterval(-6.2, -3.2), "negative"),
                    (FiniteInterval(-3.0, -1.2), "left"),
                    (FiniteInterval(-2.4, 0.0), "left"),
                    (FiniteInterval(0.8, 2.9), "right"),
                    (FiniteInterval(4.0, 4.9), "tail"),
                ),
            ),
            (
                FiniteInterval(0.1, 0.9),
                ((FiniteInterval(-2.0, 2.0), "empty-required"),),
            ),
            (
                FiniteInterval(0.0, 6.0),
                (
                    (FiniteInterval(0.0, 1.0), "q2"),
                    (FiniteInterval(1.0, 3.0), "q1"),
                    (FiniteInterval(5.0, 6.0), "q3"),
                    (FiniteInterval(2.0, 5.0), "q1"),
                ),
            ),
            (
                FiniteInterval(-0.9, -0.1),
                (
                    (FiniteInterval(-4.0, 4.0), "no-integer-required"),
                ),
            ),
        )
        for required, intervals in cases:
            with self.subTest(required=required, intervals=intervals):
                self._assert_oracle_equivalent(7, required, intervals)

    def test_fixed_seed_random_interval_unions_match_oracle(self):
        generator = random.Random(20261020)
        for case_index in range(256):
            required_start = generator.uniform(-40.0, 40.0)
            required = FiniteInterval(
                required_start,
                required_start + generator.uniform(0.0, 35.0),
            )
            intervals = []
            for _index in range(generator.randrange(0, 24)):
                start = generator.uniform(-55.0, 55.0)
                intervals.append(
                    (
                        FiniteInterval(
                            start,
                            start + generator.uniform(0.0, 25.0),
                        ),
                        f"query:{generator.randrange(0, 9)}",
                    )
                )
            with self.subTest(case_index=case_index):
                self._assert_oracle_equivalent(
                    case_index,
                    required,
                    tuple(intervals),
                )

    def test_invalid_query_id_rejection_matches_oracle(self):
        self._assert_oracle_equivalent(
            3,
            FiniteInterval(-1.0, 2.0),
            ((FiniteInterval(-1.0, 2.0), ""),),
        )


if __name__ == "__main__":
    unittest.main()
