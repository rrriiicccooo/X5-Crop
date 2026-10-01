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


def _broad_point(
    queried_traces: tuple[int, ...],
    ordinal: int,
    coordinate: float,
    *,
    identity: str | None = None,
    physical: tuple[float, float] | None = None,
    polarity: int = 1,
    background: MaterialBackgroundSide = MaterialBackgroundSide.LEFT,
    query_id: str = "query:association-contract",
) -> TransitionPoint:
    """Build an actual production broad observation at one lattice trace."""

    trace = queried_traces[ordinal]
    coordinate = float(coordinate)
    if physical is None:
        physical = (coordinate - 0.05, coordinate + 0.05)
    physical_interval = FiniteInterval(*map(float, physical))
    localization = FiniteInterval(coordinate - 0.02, coordinate + 0.02)
    if not physical_interval.contains(localization.minimum) or not physical_interval.contains(
        localization.maximum
    ):
        raise ValueError("test physical interval must contain localization interval")
    transition = BroadMaterialTraceObservation(
        transition_id=ObservationId(identity or f"assoc:{ordinal:03d}"),
        query_id=query_id,
        spatial_region_index=spatial_support_region_index(queried_traces, trace),
        trace_ordinal=ordinal,
        trace_coordinate_px=trace,
        canonical_coordinate_px=coordinate,
        localization_interval_px=localization,
        physical_position_interval_px=physical_interval,
        window_scales_mm=(1.0, 2.0),
        scale_tone_contrasts=(5.0, 4.0),
        material_contrast_z=5.0,
        material_contrast_lower_bound=4.0,
        background_uniformity_upper_bound=1.0,
        left_tone_mean=10.0,
        right_tone_mean=30.0,
        left_texture_mean=1.0,
        right_texture_mean=4.0,
        polarity=polarity,
        background_side=background,
        peak_width_px=1.0,
        prominence=5.0,
        local_noise=0.1,
    )
    return TransitionPoint(transition, float(trace), coordinate)


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


class BroadMaterialAssociationContractTest(unittest.TestCase):
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

            def inspect_live(frame, event, _argument):
                if (event != "line" or frame.f_code.co_name != "visit"
                        or frame.f_globals.get("__name__")
                        != associate_broad_material.__module__):
                    return inspect_live
                slots, seen = 0, set()

                def count_container(container):
                    if not isinstance(container, (list, tuple, set)) or id(container) in seen:
                        return 0
                    seen.add(id(container))
                    return len(container)

                cursor = frame
                while cursor:
                    if cursor.f_globals.get("__name__") == associate_broad_material.__module__:
                        values = cursor.f_locals
                        if cursor.f_code.co_name == "visit":
                            for name in ("required", "pool", "filtered", "required_set",
                                         "duplicates", "forced", "optional", "conflict"):
                                slots += count_container(values.get(name))
                            for name in ("mask", "new_mask", "base", "removed", "difference"):
                                value = values.get(name)
                                if isinstance(value, int) and id(value) not in seen:
                                    seen.add(id(value))
                                    digits = (value.bit_length() + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit
                                    slots += (digits * sys.int_info.sizeof_digit + 7) // 8
                            ranges = values.get("ranges")
                            if isinstance(ranges, dict) and id(ranges) not in seen:
                                seen.add(id(ranges))
                                slots += len(ranges)
                                slots += sum(count_container(value) for value in ranges.values())
                            groups = values.get("by_trace")
                            if isinstance(groups, dict) and id(groups) not in seen:
                                seen.add(id(groups))
                                slots += len(groups)
                                slots += sum(count_container(value) for value in groups.values())
                            bounds = values.get("bounds")
                            if isinstance(bounds, tuple) and id(bounds) not in seen:
                                seen.add(id(bounds))
                                slots += 2 + sum(count_container(value) for value in bounds[2:])
                        elif cursor.f_code.co_name == "associate_broad_material":
                            slots += 3 * len(values.get("physical_cache", ()))
                    cursor = cursor.f_back
                observed.append(slots)
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
