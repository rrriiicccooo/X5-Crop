from __future__ import annotations

from dataclasses import fields
import itertools
import math
import random
import sys
import unittest

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.broad_material_association import (
    BroadAssociationResult,
    BroadAssociationState,
    BroadAssociationWork,
    associate_broad_material,
    broad_family_sources_supported,
)
from x5crop.detection.photo_geometry.cross_height_transition_measurement import (
    spatial_region_trace_ordinals,
)
from x5crop.detection.photo_geometry.measurement_model import (
    BroadMaterialTraceObservation,
    MaterialBackgroundSide,
)
from x5crop.detection.photo_geometry.measurement_points import TransitionPoint
from x5crop.detection.photo_geometry.model import spatial_support_region_index
from tools.tests.measurement_fixture_support import _broad_point


def _path_sets(result: BroadAssociationResult) -> set[frozenset[ObservationId]]:
    return {frozenset(path) for path in result.paths}


def _physical_slope_feasible(
    points: tuple[TransitionPoint, ...],
    maximum_slope: float,
) -> bool:
    """Independent pairwise interval-slope oracle.

    For a fixed slope, each raw interval induces an intercept interval.  These
    intervals are one-dimensional, so pairwise intersection is sufficient.
    The pairwise slope bounds below are therefore independent of the runtime
    polygon clipping implementation.
    """

    lower, upper = -maximum_slope, maximum_slope
    ordered = tuple(sorted(points, key=lambda point: point.transition.trace_ordinal))
    for first, second in itertools.combinations(ordered, 2):
        left = first.transition.physical_position_interval_px
        right = second.transition.physical_position_interval_px
        delta_trace = float(second.trace - first.trace)
        if delta_trace <= 0.0:
            return False
        lower = max(lower, (right.minimum - left.maximum) / delta_trace)
        upper = min(upper, (right.maximum - left.minimum) / delta_trace)
    return lower <= upper + 1.0e-10


def _oracle_maximal_sets(
    points: tuple[TransitionPoint, ...],
    queried_traces: tuple[int, ...],
    *,
    connection_px: float,
    maximum_slope: float,
    maximum_missing_lattice_steps: int,
) -> set[frozenset[ObservationId]]:
    """Enumerate one-or-none raw choices, including same-trace competition."""

    by_ordinal: dict[int, list[TransitionPoint]] = {}
    for point in points:
        ordinal = point.transition.trace_ordinal
        by_ordinal.setdefault(ordinal, []).append(point)
    qualified: list[frozenset[ObservationId]] = []
    for choice in itertools.product(*((None, *by_ordinal.get(index, ())) for index in range(len(queried_traces)))):
        selected = tuple(point for point in choice if point is not None)
        if not selected:
            continue
        selected = tuple(sorted(selected, key=lambda point: point.transition.trace_ordinal))
        if any(
            selected[index + 1].transition.trace_ordinal
            - selected[index].transition.trace_ordinal
            > maximum_missing_lattice_steps + 1
            for index in range(len(selected) - 1)
        ):
            continue
        if len({
            (point.transition.polarity, point.transition.background_side)
            for point in selected
        }) != 1:
            continue
        if any(
            abs(second.coordinate - first.coordinate)
            > abs(second.trace - first.trace) * maximum_slope
            + connection_px
            + 1.0e-12
            for first, second in zip(selected, selected[1:])
        ):
            continue
        regions = spatial_region_trace_ordinals(queried_traces)
        if not regions or any(
            sum(point.transition.trace_ordinal in region for point in selected)
            <= len(region) // 2
            for region in regions
        ):
            continue
        if not _physical_slope_feasible(selected, maximum_slope):
            continue
        qualified.append(frozenset(point.transition.transition_id for point in selected))
    return {
        candidate
        for candidate in qualified
        if not any(candidate < other for other in qualified)
    }


def _live_broad_index_storage(frame, module_name: str, *,
                             temporary_masks=(), temporary_mask_slots=0,
                             returned_required=None):
    """Count live index containers without consulting the association receipt."""
    slots, seen, entries, receipt = 0, set(), [], None

    def count_container(container):
        if not isinstance(container, (list, tuple, set)) or id(container) in seen:
            return 0
        seen.add(id(container))
        return len(container)

    def count_numeric(value):
        if not isinstance(value, int) or id(value) in seen:
            return 0
        seen.add(id(value))
        digits = (value.bit_length() + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit
        return (digits * sys.int_info.sizeof_digit + 7) // 8

    def count_ranges(ranges):
        if not isinstance(ranges, dict) or id(ranges) in seen:
            return 0
        seen.add(id(ranges))
        return len(ranges) + sum(count_container(value) for value in ranges.values())

    def count_bounds(bounds):
        if not isinstance(bounds, tuple) or id(bounds) in seen:
            return 0
        seen.add(id(bounds))
        return 2 + sum(count_container(value) for value in bounds[2:])

    def count_updated(updated):
        if not isinstance(updated, tuple) or len(updated) != 2:
            return 0
        return count_container(updated[0]) + count_bounds(updated[1])

    cursor = frame
    while cursor:
        if cursor.f_globals.get("__name__") == module_name:
            values = cursor.f_locals
            if cursor.f_code.co_name == "visit":
                entry_count = values.get("entry_count")
                scratch_references = values.get("scratch_references")
                current_mask = values.get("mask")
                if isinstance(entry_count, int) and isinstance(scratch_references, int):
                    entries.append((entry_count, scratch_references,
                                    current_mask.bit_count() if isinstance(current_mask, int) else None))
                for name in ("required", "pool", "filtered", "required_set",
                             "duplicates", "forced", "optional", "conflict", "indices",
                             "region_counts"):
                    slots += count_container(values.get(name))
                for name in ("mask", "new_mask", "base", "removed", "difference", "child_mask"):
                    slots += count_numeric(values.get(name))
                slots += count_ranges(values.get("ranges"))
                slots += count_ranges(values.get("child_ranges"))
                slots += count_updated(values.get("updated"))
                groups = values.get("by_trace")
                if isinstance(groups, dict) and id(groups) not in seen:
                    seen.add(id(groups))
                    slots += len(groups)
                    slots += sum(count_container(value) for value in groups.values())
                slots += count_bounds(values.get("bounds"))
            elif cursor.f_code.co_name == "descend":
                slots += count_numeric(values.get("child_mask"))
                slots += count_container(values.get("child_required"))
                slots += count_bounds(values.get("child_bounds"))
                slots += count_ranges(values.get("child_ranges"))
            elif cursor.f_code.co_name == "propagate":
                for name in ("pool", "required", "required_set", "additions"):
                    slots += count_container(values.get(name))
                for name in ("mask", "result_mask"):
                    slots += count_numeric(values.get(name))
                slots += count_ranges(values.get("ranges"))
                slots += count_ranges(values.get("result"))
                slots += count_bounds(values.get("bounds"))
                slots += count_container(values.get("old"))
            elif cursor.f_code.co_name == "add_required":
                for name in ("required", "changed", "changed_set", "additions",
                             "lower_owners", "upper_owners"):
                    slots += count_container(values.get(name))
                slots += count_ranges(values.get("ranges"))
                slots += count_bounds(values.get("bounds"))
                slots += count_container(values.get("cached"))
            elif cursor.f_code.co_name == "members":
                slots += count_numeric(values.get("mask"))
                slots += count_container(values.get("result"))
                data = values.get("data")
                if isinstance(data, bytes) and id(data) not in seen:
                    seen.add(id(data))
                    slots += (len(data) + 7) // 8
            elif cursor.f_code.co_name == "viability":
                for name in ("pool", "forward", "backward", "result"):
                    slots += count_container(values.get(name))
            elif cursor.f_code.co_name == "associate_broad_material":
                # The fixed 64P + 80T input-index contract is checked
                # separately; count only the global completed path storage
                # that remains live across DFS frames here.
                completed = values.get("completed")
                if isinstance(completed, list) and id(completed) not in seen:
                    seen.add(id(completed))
                    slots += len(completed)
                    for item in completed:
                        if isinstance(item, tuple) and len(item) == 2:
                            slots += count_container(item[0])
                            slots += count_numeric(item[1])
                slots += count_ranges(values.get("physical_cache"))
                slots += count_numeric(values.get("initial_mask"))
                physical_cache = values.get("physical_cache", ())
                receipt = (values.get("completed_references", 0)
                           + values.get("frame_references", 0)
                           + 3 * len(physical_cache))
        cursor = cursor.f_back
    slots += sum(count_numeric(value) for value in temporary_masks)
    slots += temporary_mask_slots + count_updated(returned_required)
    return slots, tuple(entries), receipt


def _broad_storage_snapshot(frame, event, argument, module_name):
    """Include returned objects and the binary result beside a bit operand."""
    temporary_masks, temporary_slots, returned_required = (), 0, None
    if event == "return" and frame.f_code.co_name == "bit":
        temporary_masks = (argument,)
        raw_count = len(frame.f_locals["ranks"])
        digits = (raw_count + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit
        # At the binary operation the old operand, returned bit and new
        # result can coexist. Reserve the result's full component width;
        # this is independent of the implementation's receipt reservation.
        temporary_slots = (digits * sys.int_info.sizeof_digit + 7) // 8
    elif event == "return" and frame.f_code.co_name == "add_required":
        returned_required = argument
    return _live_broad_index_storage(
        frame, module_name, temporary_masks=temporary_masks,
        temporary_mask_slots=temporary_slots, returned_required=returned_required,
    )


class BroadMaterialAssociationContractTest(unittest.TestCase):
    def test_batched_pair_predicate_preserves_scalar_paths_and_work(self) -> None:
        class ScalarFloat(float):
            pass

        traces = tuple(range(9))
        rng = random.Random(1731)
        for trial in range(36):
            limit = 0.25 + 1.0e-12
            coordinates = (100.0, 100.0 + math.nextafter(limit, -math.inf),
                           100.0 + limit, 100.0 + math.nextafter(limit, math.inf))
            points = tuple(
                _broad_point(
                    traces, ordinal, rng.choice(coordinates),
                    identity=f"batch:{ordinal}:{peak}",
                    polarity=rng.choice((-1, 1)),
                    background=rng.choice(tuple(MaterialBackgroundSide)),
                )
                for ordinal in range(len(traces))
                for peak in range(rng.randint(1, 3))
            )
            with self.subTest(trial=trial):
                vector = self._associate(points, traces, maximum_slope=0.0, connection_px=0.25)
                scalar = self._associate(points, traces, maximum_slope=ScalarFloat(0.0), connection_px=0.25)
                for field in fields(BroadAssociationResult):
                    if field.name != "work":
                        self.assertEqual(getattr(vector, field.name), getattr(scalar, field.name))
                for field in fields(BroadAssociationWork):
                    if field.name != "peak_point_reference_count":
                        self.assertEqual(getattr(vector.work, field.name), getattr(scalar.work, field.name))
                self.assertGreaterEqual(vector.work.peak_point_reference_count,
                                        scalar.work.peak_point_reference_count)
                self.assertLessEqual(vector.work.peak_point_reference_count,
                                     2 * len(points) * len(traces) + 2 * len(traces))

    def test_batched_pair_connection_respects_one_ulp_boundary(self) -> None:
        traces = tuple(range(9))
        limit = 1.0 + 1.0e-12
        for coordinate, expected_count in ((math.nextafter(limit, -math.inf), 9),
                                            (limit, 9), (math.nextafter(limit, math.inf), 8)):
            points = tuple(_broad_point(traces, ordinal, 0.0 if ordinal == 0 else coordinate,
                                        physical=(-1.0, 2.0)) for ordinal in range(9))
            result = self._associate(points, traces, maximum_slope=0.0, connection_px=1.0)
            self.assertEqual(result.state, BroadAssociationState.COMPLETE)
            self.assertEqual(tuple(map(len, result.paths)), (expected_count,))

    def test_same_trace_pair_charges_span_multiple_blocks(self) -> None:
        traces = tuple(range(9))
        points = tuple(_broad_point(traces, 4, 100.0 + peak * 0.1,
                                    identity=f"same-trace:{peak}") for peak in range(300))
        result = self._associate(points, traces)
        self.assertEqual(result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(result.paths, ())
        self.assertEqual(result.work.point_pair_check_count, len(points) * (len(points) - 1) // 2)
        self.assertEqual(result.work.seed_count, len(points))

    def test_family_union_preserves_whole_registered_regions(self) -> None:
        paths = (("a", "b", "c", "x"), ("y", "b", "c", "d"))
        regions = (("a", "b", "c"), ("b", "c", "d"))
        self.assertTrue(broad_family_sources_supported(("a", "b", "c", "d"), paths, regions))
        self.assertTrue(broad_family_sources_supported(("a", "b", "c"), paths, ()))
        self.assertFalse(broad_family_sources_supported(("a", "b", "d"), paths, regions))
        self.assertFalse(broad_family_sources_supported(("a", "b", "c", "d"), paths, regions[:1]))
        self.assertFalse(broad_family_sources_supported(("a", "b", "c", "d"), paths,
                                                       (("a", "b", "d"), ("b", "c", "d"))))

    @staticmethod
    def _straight(
        queried_traces: tuple[int, ...],
        *,
        slope: float = 0.1,
        start: float = 100.0,
        identity_prefix: str = "straight",
        physical_half_width: float = 0.05,
    ) -> tuple[TransitionPoint, ...]:
        return tuple(
            _broad_point(
                queried_traces,
                ordinal,
                start + slope * trace,
                identity=f"{identity_prefix}:{ordinal:03d}",
                physical=(
                    start + slope * trace - physical_half_width,
                    start + slope * trace + physical_half_width,
                ),
            )
            for ordinal, trace in enumerate(queried_traces)
        )

    @staticmethod
    def _associate(
        points: tuple[TransitionPoint, ...],
        queried_traces: tuple[int, ...],
        *,
        connection_px: float = 0.05,
        maximum_slope: float = 0.5,
        maximum_missing_lattice_steps: int = 1,
    ) -> BroadAssociationResult:
        return associate_broad_material(
            points,
            queried_traces,
            reference_trace_px=(queried_traces[0] + queried_traces[-1]) / 2.0,
            connection_px=connection_px,
            maximum_slope=maximum_slope,
            maximum_missing_lattice_steps=maximum_missing_lattice_steps,
        )

    def test_one_straight_path_completes_for_all_supported_lattice_lengths(self) -> None:
        for trace_count in (6, 9, 11, 15, 21):
            queried_traces = tuple(range(trace_count))
            points = self._straight(queried_traces, identity_prefix=f"line{trace_count}")
            with self.subTest(trace_count=trace_count):
                result = self._associate(points, queried_traces)
                self.assertEqual(result.state, BroadAssociationState.COMPLETE)
                self.assertEqual(
                    _path_sets(result),
                    {frozenset(point.transition.transition_id for point in points)},
                )
                self.assertIsNone(result.failure_reason)
                self.assertLessEqual(result.work.charged_work, 5 * len(points) ** 2)

    def test_complete_results_match_independent_small_bruteforce_oracle(self) -> None:
        queried_traces = tuple(range(9))
        straight = self._straight(queried_traces, identity_prefix="oracle-straight")
        missing = tuple(point for point in straight if point.transition.trace_ordinal != 1)
        connection_break = tuple(
            _broad_point(
                queried_traces,
                ordinal,
                101.0 if ordinal == 4 else 100.0,
                identity=f"oracle-connection:{ordinal:03d}",
                physical=(
                    (101.0 if ordinal == 4 else 100.0) - 0.05,
                    (101.0 if ordinal == 4 else 100.0) + 0.05,
                ),
            )
            for ordinal in range(9)
        )
        physical_break = tuple(
            _broad_point(
                queried_traces,
                ordinal,
                101.0 if ordinal == 4 else 100.0,
                identity=f"oracle-physical:{ordinal:03d}",
                physical=(
                    (101.0 if ordinal == 4 else 100.0) - 0.05,
                    (101.0 if ordinal == 4 else 100.0) + 0.05,
                ),
            )
            for ordinal in range(9)
        )
        cases = (
            (straight, 0.05, 0.5, 0),
            (missing, 0.05, 0.5, 1),
            (missing, 0.05, 0.5, 0),
            (connection_break, 0.05, 0.0, 0),
            (physical_break, 1.0, 0.01, 0),
        )
        for points, connection_px, maximum_slope, maximum_missing in cases:
            with self.subTest(ids=points[0].transition.transition_id):
                result = self._associate(
                    points,
                    queried_traces,
                    connection_px=connection_px,
                    maximum_slope=maximum_slope,
                    maximum_missing_lattice_steps=maximum_missing,
                )
                self.assertEqual(result.state, BroadAssociationState.COMPLETE)
                expected = _oracle_maximal_sets(
                    points,
                    queried_traces,
                    connection_px=connection_px,
                    maximum_slope=maximum_slope,
                    maximum_missing_lattice_steps=maximum_missing,
                )
                self.assertEqual(_path_sets(result), expected)

    def test_same_trace_competition_keeps_qualifying_shorter_non_subset(self) -> None:
        queried_traces = tuple(range(15))
        points: list[TransitionPoint] = []
        for ordinal in range(15):
            if ordinal == 12:
                points.append(
                    _broad_point(
                        queried_traces,
                        ordinal,
                        99.0,
                        identity="competition:12:a",
                        physical=(98.5, 99.5),
                    )
                )
                points.append(
                    _broad_point(
                        queried_traces,
                        ordinal,
                        100.25,
                        identity="competition:12:b",
                        physical=(99.75, 100.75),
                    )
                )
                continue
            coordinate = 100.0 if ordinal <= 11 else 99.0
            points.append(
                _broad_point(
                    queried_traces,
                    ordinal,
                    coordinate,
                    identity=f"competition:{ordinal:02d}",
                    physical=(coordinate - 0.5, coordinate + 0.5),
                )
            )
        points_tuple = tuple(points)
        result = self._associate(
            points_tuple,
            queried_traces,
            connection_px=0.2,
            maximum_slope=1.0,
            maximum_missing_lattice_steps=0,
        )
        self.assertEqual(result.state, BroadAssociationState.COMPLETE)
        long_ids = frozenset(
            point.transition.transition_id
            for point in points_tuple
            if point.transition.transition_id != ObservationId("competition:12:b")
        )
        short_ids = frozenset(
            point.transition.transition_id
            for point in points_tuple
            if point.transition.trace_ordinal <= 11
            or point.transition.transition_id == ObservationId("competition:12:b")
        )
        self.assertIn(long_ids, _path_sets(result))
        self.assertIn(short_ids, _path_sets(result))
        self.assertNotIn(
            next(
                point.transition.transition_id
                for point in points_tuple
                if point.transition.transition_id == ObservationId("competition:12:a")
            ),
            short_ids,
        )
        self.assertEqual(len(short_ids), 13)
        self.assertEqual(len(long_ids), 15)
        self.assertEqual(len(_path_sets(result)), 2)

    def test_missing_registered_traces_keep_their_full_region_denominator(self) -> None:
        queried_traces = tuple(range(9))
        incomplete = tuple(
            _broad_point(
                queried_traces,
                ordinal,
                100.0 + 0.1 * ordinal,
                identity=f"denominator:missing:{ordinal:02d}",
            )
            for ordinal in (0, 1, 3, 6, 7, 8)
        )
        complete = incomplete + (
            _broad_point(
                queried_traces,
                4,
                100.4,
                identity="denominator:middle:04",
            ),
        )
        missing_result = self._associate(
            incomplete,
            queried_traces,
            connection_px=0.05,
            maximum_slope=0.5,
            maximum_missing_lattice_steps=2,
        )
        complete_result = self._associate(
            complete,
            queried_traces,
            connection_px=0.05,
            maximum_slope=0.5,
            maximum_missing_lattice_steps=2,
        )
        self.assertEqual(missing_result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(_path_sets(missing_result), set())
        self.assertEqual(complete_result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(
            _path_sets(complete_result),
            {frozenset(point.transition.transition_id for point in complete)},
        )

    def test_polarity_and_background_side_are_link_contracts(self) -> None:
        queried_traces = tuple(range(9))
        for field, value in (
            ("polarity", -1),
            ("background", MaterialBackgroundSide.RIGHT),
        ):
            points = []
            for ordinal in range(9):
                kwargs = {"polarity": 1, "background": MaterialBackgroundSide.LEFT}
                if ordinal == 4:
                    kwargs[field] = value
                points.append(
                    _broad_point(
                        queried_traces,
                        ordinal,
                        100.0 + 0.1 * ordinal,
                        identity=f"state:{field}:{ordinal:02d}",
                        **kwargs,
                    )
                )
            with self.subTest(field=field):
                result = self._associate(tuple(points), queried_traces)
                self.assertEqual(result.state, BroadAssociationState.COMPLETE)
                self.assertEqual(_path_sets(result), {frozenset(
                    point.transition.transition_id for point in points
                    if point.transition.trace_ordinal != 4
                )})

    def test_asymmetric_fork_matches_full_multi_peak_oracle(self) -> None:
        traces = tuple(257 * index for index in range(11))
        # Numeric association counterexample only, not a human reference:
        # one legal branch ends after eight peaks; the other retains nine.
        rows = (
            (1, 16, -20.5, 51.5), (2, 7, -27.5, 32.5),
            (3, 5.5, -9.5, 20.5), (3, 39.5, 29.5, 49.5), (3, 56, 55.5, 56.5),
            (4, 56.5, 10.5, 76.5), (5, 17.5, -13.5, 45.5),
            (5, 51.5, 48.5, 54.5), (5, 74, 56.5, 90.5),
            (6, 25, -10.5, 56.5), (7, 39.5, -16.5, 66.5),
            (8, -13.5, -31.5, 4.5), (8, 11, 10.5, 11.5),
            (8, 48.5, 30.5, 75.5), (9, 19, -24.5, 42.5), (10, 3.5, -30.5, 32.5),
        )
        points = tuple(_broad_point(traces, ordinal, coordinate, identity=f"fork:{index:02}",
                                    physical=(low, high))
                       for index, (ordinal, coordinate, low, high) in enumerate(rows))
        bounds = dict(connection_px=13.85152760407361, maximum_slope=math.tan(math.radians(4)),
                      maximum_missing_lattice_steps=1)
        result = self._associate(points, traces, **bounds)
        self.assertEqual(result.state, BroadAssociationState.COMPLETE)
        expected = {frozenset(ObservationId(f"fork:{index:02}") for index in indices)
                    for indices in ((0, 1, 2, 6, 9, 10, 13, 14), (0, 1, 2, 6, 9, 10, 12, 14, 15))}
        self.assertEqual(_path_sets(result), expected)
        self.assertEqual(_oracle_maximal_sets(points, traces, **bounds), expected)
        for reverse, mirror in ((True, False), (False, True), (True, True)):
            transformed = tuple(_broad_point(
                traces, 10 - point.transition.trace_ordinal if reverse else point.transition.trace_ordinal,
                -point.coordinate if mirror else point.coordinate,
                identity=str(point.transition.transition_id),
                physical=(-point.transition.physical_position_interval_px.maximum,
                          -point.transition.physical_position_interval_px.minimum) if mirror else
                         (point.transition.physical_position_interval_px.minimum,
                          point.transition.physical_position_interval_px.maximum),
            ) for point in points)
            with self.subTest(reverse=reverse, mirror=mirror):
                changed = self._associate(transformed, traces, **bounds)
                self.assertEqual(changed.state, BroadAssociationState.COMPLETE)
                self.assertEqual(_path_sets(changed), expected)

    def test_exhausted_tail_forks_never_return_partial_explanations(self) -> None:
        traces = tuple(183 * index for index in range(13))
        # Actual-peak mechanism counterexample, translated in both axes.
        # Incompatible tails must not force re-enumeration of every subset,
        # but both shorter non-subset explanations must survive.
        rows = (
            (0, -6, -14.5, 2.5, 1, "left"),
            (0, 13.5, 5.5, 22.5, -1, "right"),
            (1, 9.5, -0.5, 21.5, -1, "right"),
            (2, 6.5, -3.5, 16.5, -1, "right"),
            (3, 4, -5.5, 15.5, -1, "right"),
            (4, 2, -7.5, 11.5, -1, "right"),
            (5, -9, -9.5, -8.5, 1, "right"),
            (5, 0.5, -8.5, 13.5, -1, "right"),
            (6, -0.5, -9.5, 9.5, -1, "right"),
            (8, 6, -2.5, 14.5, -1, "right"),
            (9, 8, -0.5, 20.5, -1, "right"),
            (10, -5.5, -7.5, -3.5, 1, "left"),
            (10, -2, -3.5, 0.5, 1, "right"),
            (10, 6.5, 4.5, 8.5, -1, "right"),
            (10, 15, 10.5, 24.5, -1, "right"),
            (11, 7, 4.5, 8.5, -1, "left"),
            (11, 18.5, 14.5, 28.5, -1, "right"),
            (12, 21, 17.5, 31.5, -1, "right"),
        )
        points = tuple(_broad_point(
            traces, ordinal, coordinate, identity=f"tail:{index:02}",
            physical=(low, high), polarity=polarity,
            background=MaterialBackgroundSide(background),
        ) for index, (ordinal, coordinate, low, high, polarity, background) in enumerate(rows))
        bounds = dict(connection_px=14.0, maximum_slope=math.tan(math.radians(4)),
                      maximum_missing_lattice_steps=1)
        expected = _oracle_maximal_sets(points, traces, **bounds)
        self.assertEqual(sorted(map(len, expected)), [10, 10, 11])
        result = self._associate(points, traces, **bounds)
        self.assertEqual(result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(_path_sets(result), expected)

    def test_propagated_upper_set_completes_without_redecoding_or_filtering(self) -> None:
        traces = tuple(180 * index for index in range(11))
        # A numeric fork counterexample, translated away from source pixels.
        # Repeatedly decoding and filtering the un-tightened parent masks
        # exhausted the original 5P² cap before this search was complete.
        rows = (
            (0, 0, -12.5, 17.5), (1, -3.5, -15.5, 10.5),
            (2, -22.5, -24.5, -20.5), (2, -4, -18.5, 10.5),
            (3, 5.5, -0.5, 14.5), (4, 3, -8.5, 22.5),
            (5, -3.5, -14.5, 7.5), (6, -30, -30.5, -29.5),
            (6, -23, -26.5, -19.5), (6, -11.5, -13.5, -9.5),
            (6, -5, -5.5, -4.5), (6, 0, -2.5, 2.5),
            (6, 14, 11.5, 16.5), (7, -12.5, -13.5, -11.5),
            (7, -1, -7.5, 5.5), (7, 10, 6.5, 14.5),
            (8, 1, -2.5, 4.5), (9, -6, -18.5, 6.5),
        )
        bounds = dict(connection_px=10.0, maximum_slope=math.tan(math.radians(4)),
                      maximum_missing_lattice_steps=1)
        module_name = associate_broad_material.__module__
        storage_cases = set()
        for reverse, mirror, polarity, input_reversed in itertools.product(
                (False, True), (False, True), (-1, 1), (False, True)):
            points = tuple(_broad_point(
                traces, 10 - ordinal if reverse else ordinal,
                100 - coordinate if mirror else 100 + coordinate,
                identity=f"propagated:{index:02d}",
                physical=(100 - high, 100 - low) if mirror else (100 + low, 100 + high),
                polarity=polarity,
                background=(MaterialBackgroundSide.RIGHT if polarity == 1
                            else MaterialBackgroundSide.LEFT),
            ) for index, (ordinal, coordinate, low, high) in enumerate(rows))
            if input_reversed:
                points = tuple(reversed(points))
            observations, synchronized, propagated_pairs = [], [], []

            def inspect_live(frame, event, argument):
                if (event not in ("line", "return", "call")
                        or frame.f_globals.get("__name__") != module_name):
                    return inspect_live
                slots, entries, _receipt = _broad_storage_snapshot(
                    frame, event, argument, module_name)
                if entries:
                    observations.append(slots)
                cursor, child = frame, None
                while cursor:
                    if cursor.f_globals.get("__name__") == module_name:
                        values = cursor.f_locals
                        if cursor.f_code.co_name == "propagate" and values.get("ranges") and values.get("result"):
                            storage_cases.add("old_and_new_ranges")
                        elif cursor.f_code.co_name == "visit":
                            child = values
                        elif cursor.f_code.co_name == "descend" and child is not None:
                            if (isinstance(child.get("ranges"), dict)
                                    and child["ranges"] is not values.get("child_ranges")):
                                storage_cases.add("stale_descend_ranges")
                            if child.get("mask") != values.get("child_mask"):
                                storage_cases.add("stale_descend_mask")
                    cursor = cursor.f_back
                if event == "return" and frame.f_code.co_name == "propagate" and argument is not None:
                    mask, ranges = argument
                    component = frame.f_back.f_locals["component"]
                    selected = {index for rank, index in enumerate(component) if mask & (1 << rank)}
                    synchronized.append(set(ranges) == selected)
                if (event == "call" and frame.f_code.co_name == "pair_bounds"
                        and frame.f_back.f_code.co_name == "propagate"):
                    parent = frame.f_back
                    component = parent.f_back.f_locals["component"]
                    rank = component.index(parent.f_locals["index"])
                    propagated_pairs.append(bool(parent.f_locals["mask"] & (1 << rank)))
                return inspect_live

            previous_trace = sys.gettrace()
            sys.settrace(inspect_live)
            try:
                result = self._associate(points, traces, **bounds)
            finally:
                sys.settrace(previous_trace)
            with self.subTest(reverse=reverse, mirror=mirror, polarity=polarity,
                              input_reversed=input_reversed):
                expected = _oracle_maximal_sets(points, traces, **bounds)
                self.assertEqual(sorted(map(len, expected)), [9, 10])
                self.assertEqual(result.state, BroadAssociationState.COMPLETE)
                self.assertEqual(_path_sets(result), expected)
                self.assertLess(result.work.charged_work, 5 * len(points) ** 2)
                self.assertTrue(synchronized)
                self.assertTrue(all(synchronized))
                self.assertTrue(propagated_pairs)
                self.assertTrue(all(propagated_pairs))
                self.assertTrue(observations)
                self.assertLessEqual(max(observations), result.work.peak_point_reference_count)
                self.assertLessEqual(result.work.peak_point_reference_count,
                                     2 * len(points) * len(traces) + 2 * len(traces))
        self.assertEqual(storage_cases, {
            "old_and_new_ranges", "stale_descend_ranges", "stale_descend_mask",
        })

    def test_pairwise_physical_fits_do_not_replace_common_line_feasibility(self) -> None:
        traces = tuple(range(12))
        points = tuple(_broad_point(
            traces, ordinal, 101.0 if 4 <= ordinal < 8 else 100.0,
            identity=f"common-empty:{ordinal:02d}",
            physical=(100.95, 101.05) if 4 <= ordinal < 8 else (99.95, 100.05),
        ) for ordinal in range(12))
        bounds = dict(connection_px=1.0, maximum_slope=1.0,
                      maximum_missing_lattice_steps=1)
        self.assertTrue(all(_physical_slope_feasible(pair, 1.0)
                            for pair in itertools.combinations(points, 2)))
        self.assertFalse(_physical_slope_feasible(points, 1.0))
        expected = _oracle_maximal_sets(points, traces, **bounds)
        self.assertEqual(expected, set())
        result = self._associate(points, traces, **bounds)
        self.assertEqual(result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(_path_sets(result), expected)
        self.assertGreater(result.work.polygon_clip_count, 0)

    def test_curved_full_universes_keep_all_non_subset_explanations(self) -> None:
        traces = tuple(261 * index for index in range(13))
        # Two materials share several traces. Within the qualifying material,
        # a curved full universe contains multiple straight physical subsets.
        # A completed superset may constrain later search, never remove a
        # different non-subset explanation or shrink registered denominators.
        cases = (
            (
                (0, 2, -10.5, 6.5, "left"), (0, 18, 13.5, 31.5, "right"),
                (1, 7, 2.5, 19.5, "right"), (2, 3, -1.5, 16.5, "right"),
                (3, -1, -5.5, 12.5, "right"), (4, -1.5, -6.5, 11.5, "right"),
                (5, -1, -5.5, 11.5, "right"), (6, -4.5, -9.5, 9.5, "right"),
                (7, 3.5, -1.5, 16.5, "right"), (8, -8, -13.5, -3.5, "left"),
                (8, 7.5, 2.5, 21.5, "right"), (9, 5, 0.5, 18.5, "right"),
                (10, -5, -13.5, -0.5, "left"), (10, 11, 6.5, 24.5, "right"),
                (11, -2, -13.5, 2.5, "left"), (11, 14, 9.5, 27.5, "right"),
                (12, -3, -13.5, 1.5, "left"), (12, 14, 9.5, 26.5, "right"),
            ),
            (
                (0, 5.5, -10.5, 10.5, "left"), (0, 20.5, 15.5, 34.5, "right"),
                (1, -7, -13.5, -2.5, "left"), (1, 10, 5.5, 22.5, "right"),
                (2, 5.5, 0.5, 18.5, "right"), (3, 2, -2.5, 15.5, "right"),
                (4, 0.5, -4.5, 14.5, "right"), (5, 0.5, -4.5, 14.5, "right"),
                (6, -2, -7.5, 12.5, "right"), (7, 6, 0.5, 20.5, "right"),
                (8, -2.5, -13.5, 2.5, "left"), (8, 12.5, 7.5, 27.5, "right"),
                (9, 7.5, 2.5, 20.5, "right"), (10, -2, -13.5, 2.5, "left"),
                (10, 14.5, 9.5, 27.5, "right"), (11, 1, -13.5, 5.5, "left"),
                (11, 17, 12.5, 30.5, "right"), (12, 1, -13.5, 5.5, "left"),
                (12, 17, 12.5, 30.5, "right"),
            ),
        )
        bounds = dict(connection_px=7.527321315395724,
                      maximum_slope=math.tan(math.radians(4)), maximum_missing_lattice_steps=1)
        for case_index, rows in enumerate(cases):
            for reverse, mirror in ((False, False), (True, False), (False, True), (True, True)):
                points = tuple(_broad_point(
                    traces, 12 - ordinal if reverse else ordinal,
                    -coordinate if mirror else coordinate,
                    identity=f"curved:{case_index}:{index:02}",
                    physical=(-high, -low) if mirror else (low, high),
                    polarity=-1, background=MaterialBackgroundSide(background),
                ) for index, (ordinal, coordinate, low, high, background) in enumerate(rows))
                with self.subTest(case=case_index, reverse=reverse, mirror=mirror):
                    expected = _oracle_maximal_sets(points, traces, **bounds)
                    # Reversing this 13-trace lattice moves raw support
                    # between the fixed 4/4/5 regions. Keep those denominators;
                    # the 11-point interpretation then loses regional quota.
                    expected_lengths = ([12] if case_index == 0 else [12, 12]) if reverse else (
                        [11, 12] if case_index == 0 else [11, 12, 12])
                    self.assertEqual(sorted(map(len, expected)), expected_lengths)
                    result = self._associate(points, traces, **bounds)
                    self.assertEqual(result.state, BroadAssociationState.COMPLETE)
                    self.assertEqual(_path_sets(result), expected)
                    self.assertLessEqual(result.work.charged_work, 5 * len(points) ** 2)

    def test_tiny_random_lattices_match_independent_full_choice_oracle(self) -> None:
        traces = tuple(range(6))
        bounds = dict(connection_px=0.4, maximum_slope=0.5,
                      maximum_missing_lattice_steps=1)
        for seed in range(48):
            rng = random.Random(seed)
            points = []
            for ordinal in range(len(traces)):
                if rng.random() < 0.12:
                    continue
                for choice in range(1 + (rng.random() < 0.18)):
                    coordinate = 100.0 + rng.choice((-0.5, 0.0, 0.5))
                    points.append(_broad_point(traces, ordinal, coordinate,
                        identity=f"random:{seed}:{ordinal}:{choice}",
                        physical=(coordinate - 0.55, coordinate + 0.55)))
            raw = tuple(points)
            with self.subTest(seed=seed):
                result = self._associate(raw, traces, **bounds)
                if result.state == BroadAssociationState.COMPLETE:
                    self.assertEqual(_path_sets(result),
                        _oracle_maximal_sets(raw, traces, **bounds))
                else:
                    self.assertEqual(result.paths, ())

    def test_mirror_and_reversed_trace_coordinates_preserve_raw_sets(self) -> None:
        queried_traces = tuple(range(9))
        base = self._straight(queried_traces, identity_prefix="symmetry")
        mirrored = tuple(
            _broad_point(
                queried_traces,
                point.transition.trace_ordinal,
                -point.coordinate,
                identity=str(point.transition.transition_id),
                physical=(
                    -point.transition.physical_position_interval_px.maximum,
                    -point.transition.physical_position_interval_px.minimum,
                ),
            )
            for point in base
        )
        reversed_traces = tuple(
            _broad_point(
                queried_traces,
                queried_traces[-1] - point.transition.trace_ordinal,
                point.coordinate,
                identity=str(point.transition.transition_id),
                physical=(
                    point.transition.physical_position_interval_px.minimum,
                    point.transition.physical_position_interval_px.maximum,
                ),
            )
            for point in base
        )
        base_result = self._associate(base, queried_traces)
        mirrored_result = self._associate(mirrored, queried_traces)
        reversed_result = self._associate(reversed_traces, queried_traces)
        self.assertEqual(base_result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(mirrored_result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(reversed_result.state, BroadAssociationState.COMPLETE)
        self.assertEqual(_path_sets(base_result), _path_sets(mirrored_result))
        self.assertEqual(_path_sets(base_result), _path_sets(reversed_result))

    def test_dense_branching_returns_typed_bound_without_partial_paths(self) -> None:
        queried_traces = tuple(range(9))
        points = tuple(
            _broad_point(
                queried_traces,
                ordinal,
                100.0 + 0.01 * branch,
                identity=f"dense:{ordinal:02d}:{branch}",
                physical=(95.0, 105.0),
            )
            for ordinal in range(9)
            for branch in range(2)
        )
        result = self._associate(
            points,
            queried_traces,
            connection_px=0.25,
            maximum_slope=1.0,
        )
        self.assertEqual(result.state, BroadAssociationState.BOUND_EXCEEDED)
        self.assertEqual(result.paths, ())
        self.assertIsInstance(result.failure_reason, str)
        self.assertTrue(result.failure_reason)
        self.assertLessEqual(result.work.charged_work, 5 * len(points) ** 2)
        self.assertLessEqual(result.work.peak_search_depth, len(queried_traces))
        self.assertLessEqual(result.work.peak_completed_path_count, len(points))
        self.assertLessEqual(
            result.work.peak_point_reference_count,
            2 * len(points) * len(queried_traces) + 2 * len(queried_traces),
        )
        self.assertLessEqual(
            result.work.peak_polygon_vertex_count,
            min(len(points), len(queried_traces)) * (2 * len(queried_traces) + 4) + 4 * len(queried_traces) + 10,
        )

    def test_work_ledger_is_typed_nonnegative_and_within_bound(self) -> None:
        queried_traces = tuple(range(9))
        points = self._straight(queried_traces, identity_prefix="ledger")
        result = self._associate(points, queried_traces)
        self.assertEqual(result.state, BroadAssociationState.COMPLETE)
        for item in fields(result.work):
            value = getattr(result.work, item.name)
            self.assertIs(type(value), int, item.name)
            self.assertGreaterEqual(value, 0, item.name)
        self.assertLessEqual(result.work.charged_work, 5 * len(points) ** 2)
        self.assertLessEqual(result.work.seed_count, len(points))
        self.assertLessEqual(result.work.created_path_count, len(points) ** 2)

    def test_entry_mask_scratch_recovers_general_search_and_matches_oracle(self) -> None:
        traces = tuple(range(11))
        # A connected component with a dead-end branch.  The branch is linked
        # into the component, but the DAG viability pass removes two raw
        # points before DFS.  Later conflict/tail updates make still smaller
        # entry masks while stale parent containers remain live.
        rows = (
            (1, 100.2, 99.2, 101.2), (4, 99.9, 95.9, 103.9),
            (5, 100.5, 99.5, 101.5), (10, 100.9, 92.9, 108.9),
            (8, 98.8, 94.8, 102.8), (9, 101.0, 100.8, 101.2),
            (2, 102.2, 102.15, 102.25), (3, 99.3, 91.3, 107.3),
            (0, 99.75, 99.25, 100.25), (0, 99.96, 91.96, 107.96),
            (7, 100.66, 100.61, 100.71), (7, 100.5, 96.5, 104.5),
            (2, 100.7, 98.7, 102.7), (8, 99.8, 91.8, 107.8),
            (6, 100.8, 99.8, 101.8),
        )
        base = tuple(
            _broad_point(traces, ordinal, coordinate,
                         identity=f"entry-mask:{index:02d}",
                         physical=(low, high))
            for index, (ordinal, coordinate, low, high) in enumerate(rows)
        )
        module_name = associate_broad_material.__module__

        def run_case(points, bounds, *, expect_sparse, expect_full, expect_legacy_overflow):
            cap = 2 * len(points) * len(traces) + 2 * len(traces)
            observed = []
            legacy_values = []

            def inspect_live(frame, event, _argument):
                if (event not in ("line", "return")
                        or frame.f_globals.get("__name__") != module_name
                        or frame.f_code.co_name not in (
                            "visit", "reference_peak", "propagate", "descend",
                            "add_required", "members", "viability", "bit")):
                    return inspect_live
                slots, entries, receipt = _broad_storage_snapshot(
                    frame, event, _argument, module_name)
                if entries:
                    observed.append((slots, receipt, entries))
                if frame.f_code.co_name == "reference_peak" and "value" in frame.f_locals:
                    # Estimate the old q-wide reservation independently from
                    # live frames. This is only a diagnostic contrast: the
                    # test's correctness proof is the live-object count and
                    # the independent exhaustive oracle below.
                    legacy_values.append(
                        frame.f_locals["value"]
                        + sum(8 * (len(points) - entry) for entry, _, _ in entries)
                    )
                return inspect_live

            previous_trace = sys.gettrace()
            sys.settrace(inspect_live)
            try:
                result = self._associate(points, traces, **bounds)
            finally:
                sys.settrace(previous_trace)

            expected = _oracle_maximal_sets(points, traces, **bounds)
            self.assertEqual(result.state, BroadAssociationState.COMPLETE)
            self.assertEqual(_path_sets(result), expected)
            self.assertTrue(observed)
            self.assertTrue(all(
                scratch == 8 * entry + 2 * len(traces)
                for _, _, entries in observed
                for entry, scratch, _ in entries
            ))
            max_live_slots = max(slots for slots, _, _ in observed)
            self.assertLessEqual(max_live_slots, cap)
            self.assertLessEqual(max_live_slots, result.work.peak_point_reference_count)
            receipts = [receipt for _, receipt, _ in observed if receipt is not None]
            self.assertTrue(receipts)
            self.assertLessEqual(max(receipts), result.work.peak_point_reference_count)
            self.assertLessEqual(result.work.peak_point_reference_count, cap)
            if expect_sparse:
                self.assertTrue(any(
                    current is not None and current < entry
                    for _, _, entries in observed
                    for entry, _, current in entries
                ))
            if expect_full:
                self.assertTrue(any(
                    entry == len(points) and current == entry
                    for _, _, entries in observed
                    for entry, _, current in entries
                ))
            if expect_legacy_overflow:
                self.assertGreater(max(legacy_values), cap)
            return result

        bounds = dict(connection_px=2.0, maximum_slope=0.03,
                      maximum_missing_lattice_steps=0)
        for reverse, mirror in ((False, False), (True, False),
                                (False, True), (True, True)):
            transformed = tuple(_broad_point(
                traces,
                traces[-1] - point.transition.trace_ordinal if reverse
                else point.transition.trace_ordinal,
                -point.coordinate if mirror else point.coordinate,
                identity=str(point.transition.transition_id),
                physical=(-point.transition.physical_position_interval_px.maximum,
                          -point.transition.physical_position_interval_px.minimum)
                if mirror else (
                    point.transition.physical_position_interval_px.minimum,
                    point.transition.physical_position_interval_px.maximum,
                ),
            ) for point in base)
            with self.subTest(reverse=reverse, mirror=mirror):
                run_case(
                    transformed,
                    bounds,
                    expect_sparse=True,
                    expect_full=False,
                    expect_legacy_overflow=not reverse and not mirror,
                )

        full_points = self._straight(traces, slope=0.01,
                                     identity_prefix="entry-mask-full")
        run_case(
            full_points,
            dict(connection_px=0.05, maximum_slope=0.5,
                 maximum_missing_lattice_steps=1),
            expect_sparse=False,
            expect_full=True,
            expect_legacy_overflow=False,
        )

    def test_live_parent_index_storage_stays_within_original_budget(self) -> None:
        # Inspect actual live containers independently of the receipt counter.
        # These dense forks exposed suspended parent scratch omitted from the
        # old ledger. Units match the numeric/index proxy, not Python heap/RSS.
        for trace_count in (10, 21):
            traces = tuple(range(trace_count))
            points = tuple(_broad_point(traces, ordinal, 100.0 + 0.01 * branch,
                identity=f"live-storage:{trace_count}:{ordinal}:{branch}",
                physical=(95.0, 105.0))
                for ordinal in range(trace_count) for branch in range(2))
            cap = 2 * len(points) * trace_count + 2 * trace_count
            observed = []
            entry_states = []

            def inspect_live(frame, event, _argument):
                if (event not in ("line", "return")
                        or frame.f_code.co_name not in (
                            "visit", "reference_peak", "propagate", "descend",
                            "add_required", "members", "viability", "bit")
                        or frame.f_globals.get("__name__")
                        != associate_broad_material.__module__):
                    return inspect_live
                slots, entries, _receipt = _broad_storage_snapshot(
                    frame, event, _argument, associate_broad_material.__module__)
                observed.append(slots)
                entry_states.extend(entries)
                return inspect_live

            previous_trace = sys.gettrace()
            sys.settrace(inspect_live)
            try:
                result = self._associate(points, traces, connection_px=0.25)
            finally:
                sys.settrace(previous_trace)
            with self.subTest(trace_count=trace_count):
                self.assertTrue(observed)
                self.assertLessEqual(max(observed), cap)
                self.assertTrue(entry_states)
                self.assertTrue(all(
                    scratch == 8 * entry + 2 * trace_count
                    for entry, scratch, _ in entry_states
                ))
                self.assertEqual(result.state, BroadAssociationState.BOUND_EXCEEDED)
                self.assertEqual(result.paths, ())

    def test_malformed_identity_and_result_states_are_rejected(self) -> None:
        queried_traces = tuple(range(9))
        first = _broad_point(queried_traces, 0, 100.0, identity="malformed:a")
        duplicate = _broad_point(queried_traces, 1, 100.1, identity="malformed:a")
        with self.assertRaises(ValueError):
            self._associate((first, duplicate), queried_traces)

        with self.assertRaises(ValueError):
            self._associate(
                (
                    TransitionPoint(
                        first.transition,
                        trace=999.0,
                        coordinate=first.coordinate,
                    ),
                ),
                queried_traces,
            )

        work = BroadAssociationWork()
        identity_a = ObservationId("malformed:a")
        identity_b = ObservationId("malformed:b")
        with self.assertRaises(ValueError):
            BroadAssociationResult(
                BroadAssociationState.COMPLETE,
                (identity_b, identity_a),
                queried_traces,
                4.0,
                (),
                work,
            )
        with self.assertRaises(ValueError):
            BroadAssociationResult(
                BroadAssociationState.BOUND_EXCEEDED,
                (identity_a,),
                queried_traces,
                4.0,
                ((identity_a,),),
                work,
                "bound",
            )
        with self.assertRaises(ValueError):
            BroadAssociationResult(
                BroadAssociationState.COMPLETE,
                (identity_a,),
                queried_traces,
                4.0,
                ((identity_b,),),
                work,
            )
        with self.assertRaises(ValueError):
            BroadAssociationWork(point_pair_check_count=-1)


if __name__ == "__main__":
    unittest.main()
