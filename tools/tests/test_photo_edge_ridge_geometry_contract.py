from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from x5crop.configuration.photo_edges import PhotoEdgeDetectionParameters
from x5crop.detection.evidence.photo_edges import (
    LocalTransitionState,
    NumericInterval,
    PhotoEdgeObservation,
    PhotoEdgeSideStatistics,
)
from x5crop.detection.physical.photo_edge_geometry import (
    GeometryWorkBudget,
    GeometryWorkStatistics,
    PhotoEdgeGeometryResult,
    _GeometrySchedulerDiagnostics,
    _PixelLineFeasibleRegion,
    _cell_work_upper_bound,
    _observations_for_fragments,
    _run_region_searches,
    _shared_slope_intervals,
    join_dual_lane_hypotheses,
    solve_image_only_lane_geometry,
)
from x5crop.detection.physical.photo_edge_observation import (
    PhotoEdgeFragment,
    PhotoEdgeRidgeEdge,
    PhotoEdgeRidgeGraph,
    PhotoEdgeRidgeNode,
    _ChannelScaleSupport,
    _MeasurementDomain,
    _channel_supports_for_scale,
    _group_channel_scale_supports,
    _local_noise_at_positions,
)
from x5crop.domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.formats import FrameSizeMm


SOURCE_SHA256 = "0" * 64


def _side_statistics(value: float) -> PhotoEdgeSideStatistics:
    return PhotoEdgeSideStatistics(
        intensity_median_u8=value,
        intensity_mad_u8=1.0,
        texture_median_u8=2.0,
        gradient_median_u8=3.0,
    )


def _observation(
    identity: str,
    long_minimum: float,
    long_maximum: float,
    short_minimum: float,
    short_maximum: float,
) -> PhotoEdgeObservation:
    observation_id = ObservationId(identity)
    interval = PixelInterval(short_minimum, short_maximum)
    return PhotoEdgeObservation(
        observation_id=observation_id,
        source_sha256=SOURCE_SHA256,
        long_axis_footprint=PixelInterval(long_minimum, long_maximum),
        short_axis_position_interval=interval,
        negative_side_statistics=_side_statistics(20.0),
        positive_side_statistics=_side_statistics(200.0),
        absolute_intensity_effect=180.0,
        absolute_texture_effect=0.0,
        absolute_gradient_effect=0.0,
        local_noise_u8=1.0,
        multiscale_position_interval=interval,
        state=LocalTransitionState.SUPPORTED,
        measurement_channels=("intensity",),
        measurement_scales=(1.0,),
        censored=False,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=observation_id,
            dependencies=(MeasurementIdentity.GRAY_WORK,),
            description="ridge graph contract observation",
        ),
    )


def _node(
    identity: str,
    long_minimum: float,
    long_maximum: float,
    short_minimum: float,
    short_maximum: float,
) -> PhotoEdgeRidgeNode:
    observation = _observation(
        identity,
        long_minimum,
        long_maximum,
        short_minimum,
        short_maximum,
    )
    return PhotoEdgeRidgeNode(
        node_id=observation.observation_id,
        observation=observation,
    )


class ChannelLocalSupportContract(unittest.TestCase):
    def test_vectorized_channel_noise_matches_the_exact_window_mad(
        self,
    ) -> None:
        values = np.asarray(
            [0.0, 1.0, 4.0, 4.0, 9.0, 10.0, 16.0, 17.0, 20.0],
            dtype=np.float64,
        )
        positions = np.asarray([3, 4, 5], dtype=np.int64)

        def first_difference_mad(window: np.ndarray) -> float:
            differences = np.abs(np.diff(window))
            median = float(np.median(differences))
            return float(np.median(np.abs(differences - median)))

        expected = np.asarray(
            [
                max(
                    0.5,
                    first_difference_mad(values[position - 3 : position]),
                    first_difference_mad(values[position : position + 3]),
                )
                for position in positions
            ]
        )
        np.testing.assert_allclose(
            _local_noise_at_positions(
                values,
                positions,
                depth=3,
                floor=0.5,
            ),
            expected,
            rtol=0.0,
            atol=0.0,
        )
        np.testing.assert_allclose(
            _local_noise_at_positions(
                values,
                positions,
                depth=1,
                floor=0.5,
            ),
            np.full(positions.shape, 0.5),
            rtol=0.0,
            atol=0.0,
        )

    def test_each_channel_uses_own_noise_and_forms_multiscale_evidence(
        self,
    ) -> None:
        noisy_intensity = np.asarray(
            [
                0.0,
                30.0,
                5.0,
                40.0,
                0.0,
                35.0,
                5.0,
                45.0,
                0.0,
                40.0,
                5.0,
                45.0,
                0.0,
                35.0,
                5.0,
                40.0,
                0.0,
                30.0,
                5.0,
                35.0,
                0.0,
            ],
            dtype=np.float64,
        )
        transition = np.asarray(
            [0.0] * 10 + [20.0] * 11,
            dtype=np.float64,
        )
        neutral = np.zeros_like(transition)
        parameters = PhotoEdgeDetectionParameters(
            minimum_supporting_scales=2,
            multiscale_factors=(0.5, 1.0),
        )
        domains = (
            _MeasurementDomain(
                PixelInterval(0.0, 20.0),
                PixelInterval(0.0, 20.0),
            ),
        )
        for channel in ("intensity", "texture", "gradient"):
            with self.subTest(channel=channel):
                profiles = {
                    "intensity": (
                        transition
                        if channel == "intensity"
                        else noisy_intensity
                    ),
                    "texture": (
                        transition if channel == "texture" else neutral
                    ),
                    "gradient": (
                        transition if channel == "gradient" else neutral
                    ),
                }
                supports = tuple(
                    support
                    for depth, scale in ((3, 0.5), (4, 1.0))
                    for support in _channel_supports_for_scale(
                        profiles["intensity"],
                        profiles["texture"],
                        profiles["gradient"],
                        domains,
                        depth=depth,
                        scale=scale,
                        parameters=parameters,
                    )
                    if support.channel == channel
                )
                self.assertEqual(
                    {support.scale for support in supports},
                    {0.5, 1.0},
                )
                transitions, _ = _group_channel_scale_supports(
                    supports,
                    profiles["intensity"],
                    profiles["texture"],
                    profiles["gradient"],
                    base_depth=4,
                    minimum_scales=2,
                    position_tolerance_ratio=1.0,
                    footprint=PixelInterval(0.0, 20.0),
                )
                self.assertTrue(
                    any(
                        item.channels == (channel,)
                        and item.scales == (0.5, 1.0)
                        for item in transitions
                    )
                )

    def test_transitive_overlap_does_not_bridge_transitions(self) -> None:
        supports = (
            _ChannelScaleSupport(
                channel="intensity",
                scale=0.5,
                depth=2,
                position=1.0,
                support_interval=PixelInterval(0.0, 2.0),
                effect=8.0,
                local_noise=1.0,
                censored=False,
            ),
            _ChannelScaleSupport(
                channel="texture",
                scale=1.0,
                depth=2,
                position=2.5,
                support_interval=PixelInterval(1.0, 4.0),
                effect=8.0,
                local_noise=1.0,
                censored=False,
            ),
            _ChannelScaleSupport(
                channel="gradient",
                scale=2.0,
                depth=2,
                position=4.0,
                support_interval=PixelInterval(3.0, 5.0),
                effect=8.0,
                local_noise=1.0,
                censored=False,
            ),
        )
        profiles = np.arange(8, dtype=np.float64)
        transitions, _ = _group_channel_scale_supports(
            supports,
            profiles,
            profiles,
            profiles,
            base_depth=2,
            minimum_scales=1,
            position_tolerance_ratio=1.0,
            footprint=PixelInterval(0.0, 7.0),
        )
        self.assertEqual(len(transitions), 2)
        self.assertEqual(
            tuple(item.position_interval for item in transitions),
            (PixelInterval(0.0, 4.0), PixelInterval(3.0, 5.0)),
        )


class RidgeGraphContract(unittest.TestCase):
    def test_branch_paths_reference_shared_nodes_without_copying(self) -> None:
        nodes = (
            _node("root", 0.0, 7.0, 10.0, 11.0),
            _node("branch_a", 4.0, 11.0, 10.0, 10.5),
            _node("branch_b", 4.0, 11.0, 10.5, 11.0),
            _node("sink", 8.0, 15.0, 10.25, 10.75),
        )
        graph = PhotoEdgeRidgeGraph(
            nodes=nodes,
            edges=(
                PhotoEdgeRidgeEdge(
                    ObservationId("root"),
                    ObservationId("branch_a"),
                ),
                PhotoEdgeRidgeEdge(
                    ObservationId("root"),
                    ObservationId("branch_b"),
                ),
                PhotoEdgeRidgeEdge(
                    ObservationId("branch_a"),
                    ObservationId("sink"),
                ),
                PhotoEdgeRidgeEdge(
                    ObservationId("branch_b"),
                    ObservationId("sink"),
                ),
            ),
        )
        paths = tuple(graph.iter_fragments("contract"))
        self.assertEqual(len(paths), 2)
        self.assertEqual(
            {path.node_ids for path in paths},
            {
                (
                    ObservationId("root"),
                    ObservationId("branch_a"),
                    ObservationId("sink"),
                ),
                (
                    ObservationId("root"),
                    ObservationId("branch_b"),
                    ObservationId("sink"),
                ),
            },
        )
        self.assertEqual(
            len({node.observation.observation_id for node in graph.nodes}),
            len(graph.nodes),
        )
        fragment_map = {
            fragment.fragment_id: fragment for fragment in paths
        }
        self.assertEqual(
            len(
                _observations_for_fragments(
                    tuple(fragment_map),
                    fragment_map,
                    graph,
                )
            ),
            len(graph.nodes),
        )

    def test_real_gap_remains_separate_components(self) -> None:
        graph = PhotoEdgeRidgeGraph(
            nodes=(
                _node("left", 0.0, 7.0, 10.0, 11.0),
                _node("right", 16.0, 23.0, 10.0, 11.0),
            ),
            edges=(),
        )
        self.assertEqual(
            tuple(fragment.node_ids for fragment in graph.iter_fragments("gap")),
            (
                (ObservationId("left"),),
                (ObservationId("right"),),
            ),
        )

    def test_unbranched_curve_is_one_complete_path(self) -> None:
        graph = PhotoEdgeRidgeGraph(
            nodes=(
                _node("curve_1", 0.0, 7.0, 10.0, 11.0),
                _node("curve_2", 4.0, 11.0, 10.5, 11.5),
                _node("curve_3", 8.0, 15.0, 11.0, 12.0),
            ),
            edges=(
                PhotoEdgeRidgeEdge(
                    ObservationId("curve_1"),
                    ObservationId("curve_2"),
                ),
                PhotoEdgeRidgeEdge(
                    ObservationId("curve_2"),
                    ObservationId("curve_3"),
                ),
            ),
        )
        fragments = tuple(graph.iter_fragments("curve"))
        self.assertEqual(len(fragments), 1)
        self.assertEqual(
            fragments[0].node_ids,
            (
                ObservationId("curve_1"),
                ObservationId("curve_2"),
                ObservationId("curve_3"),
            ),
        )
        with self.assertRaisesRegex(ValueError, "source-to-sink"):
            graph.observations_for(
                PhotoEdgeFragment(
                    fragment_id=ObservationId("partial"),
                    node_ids=(ObservationId("curve_2"),),
                )
            )


class ExactSetAndBudgetContract(unittest.TestCase):
    def test_work_statistics_is_an_immutable_final_snapshot(self) -> None:
        self.assertTrue(
            GeometryWorkStatistics.__dataclass_params__.frozen
        )
        self.assertFalse(
            any(
                name.startswith(("consume_", "register_"))
                for name in vars(GeometryWorkStatistics)
            )
        )

    def test_disconnected_polygon_slopes_remain_disconnected(self) -> None:
        top = _PixelLineFeasibleRegion(
            (
                ((-0.04, 1.0), (-0.03, 1.0), (-0.03, 2.0), (-0.04, 2.0)),
                ((0.03, 1.0), (0.04, 1.0), (0.04, 2.0), (0.03, 2.0)),
            )
        )
        bottom = _PixelLineFeasibleRegion(
            (
                ((-0.05, 3.0), (-0.02, 3.0), (-0.02, 4.0), (-0.05, 4.0)),
                ((0.02, 3.0), (0.05, 3.0), (0.05, 4.0), (0.02, 4.0)),
            )
        )
        self.assertEqual(
            _shared_slope_intervals(top, bottom),
            (
                NumericInterval(-0.04, -0.03),
                NumericInterval(0.03, 0.04),
            ),
        )

    def test_full_binary_work_bound_is_fixed(self) -> None:
        self.assertEqual(
            _cell_work_upper_bound(
                NumericInterval(0.0, 1.0),
                resolution=0.25,
                maximum_depth=64,
            ),
            7,
        )
        self.assertEqual(
            _cell_work_upper_bound(
                NumericInterval(0.0, 0.25),
                resolution=0.25,
                maximum_depth=64,
            ),
            1,
        )

    def test_work_budget_counts_unique_consensus_and_executed_cells(self) -> None:
        budget = GeometryWorkBudget(
            maximum_region_cells=2,
            maximum_consensus_states=2,
        )
        self.assertTrue(budget.register_consensus_state(("pair", "a")))
        self.assertTrue(budget.register_consensus_state(("pair", "a")))
        self.assertEqual(budget.consumed_consensus_states, 1)
        self.assertTrue(budget.register_consensus_state(("pair", "b")))
        self.assertFalse(budget.register_consensus_state(("pair", "c")))
        self.assertEqual(budget.consumed_consensus_states, 2)

        self.assertTrue(budget.consume_region_cell())
        self.assertTrue(budget.consume_region_cell())
        self.assertFalse(budget.consume_region_cell())
        self.assertEqual(budget.consumed_region_cells, 2)

    def test_narrow_search_completes_before_wide_search_is_rejected(
        self,
    ) -> None:
        class Search:
            def __init__(
                self,
                identity: str,
                upper_bounds: list[int],
            ) -> None:
                self.order_key = (upper_bounds[0], identity, "", 0)
                self.upper_bounds = upper_bounds
                self.evaluations = 0
                self.incomplete = False

            @property
            def complete(self) -> bool:
                return not self.upper_bounds

            @property
            def pending_cell_count(self) -> int:
                return 0 if self.complete else 1

            def remaining_cell_upper_bound(self) -> int:
                return 0 if self.complete else self.upper_bounds[0]

            def step(self) -> None:
                self.evaluations += 1
                self.upper_bounds.pop(0)

            def mark_incomplete(self) -> None:
                self.incomplete = True
                self.upper_bounds.clear()

        wide = Search("wide", [7])
        narrow = Search("narrow", [1])
        budget = GeometryWorkBudget(
            maximum_region_cells=2,
            maximum_consensus_states=2,
        )
        diagnostics = _GeometrySchedulerDiagnostics()
        admitted = _run_region_searches(
            (wide, narrow),
            budget,
            diagnostics,
        )
        self.assertEqual(admitted, (narrow,))
        self.assertEqual(narrow.evaluations, 1)
        self.assertFalse(narrow.incomplete)
        self.assertEqual(wide.evaluations, 0)
        self.assertTrue(wide.incomplete)
        self.assertEqual(budget.consumed_region_cells, 1)
        self.assertTrue(budget.region_search_incomplete)
        self.assertEqual(diagnostics.peak_active_searches, 1)
        self.assertEqual(diagnostics.peak_pending_cells, 1)
        self.assertEqual(diagnostics.unsearched_hypothesis_count, 1)


class SharedLaneGeometryContract(unittest.TestCase):
    @staticmethod
    def _graph(
        prefix: str,
        top: float,
        bottom: float,
    ) -> PhotoEdgeRidgeGraph:
        paths: list[tuple[PhotoEdgeRidgeNode, ...]] = []
        for role, position in (("top", top), ("bottom", bottom)):
            paths.append(
                tuple(
                    _node(
                        f"{prefix}:{role}:{index}",
                        float(index * 4),
                        float(index * 4 + 7),
                        position - 0.5,
                        position + 0.5,
                    )
                    for index in range(5)
                )
            )
        return PhotoEdgeRidgeGraph(
            nodes=tuple(
                sorted(
                    (node for path in paths for node in path),
                    key=lambda node: (
                        node.observation.long_axis_footprint.minimum,
                        node.observation.short_axis_position_interval.minimum,
                        str(node.node_id),
                    ),
                )
            ),
            edges=tuple(
                sorted(
                    PhotoEdgeRidgeEdge(left.node_id, right.node_id)
                    for path in paths
                    for left, right in zip(
                        path,
                        path[1:],
                        strict=False,
                    )
                )
            ),
        )

    def _solve(
        self,
        prefix: str,
        top: float,
        bottom: float,
    ) -> PhotoEdgeGeometryResult:
        return solve_image_only_lane_geometry(
            self._graph(prefix, top, bottom),
            FrameSizeMm(36.0, 24.0),
            PhotoEdgeDetectionParameters(),
            observation_prefix=prefix,
            long_extent_px=24,
            short_extent_px=200,
        )

    def test_single_lane_can_form_formal_geometry(self) -> None:
        result = self._solve("single", 20.0, 140.0)
        self.assertFalse(result.budget_exhausted)
        self.assertFalse(result.search_unavailable)
        self.assertEqual(len(result.hypotheses), 1)
        self.assertEqual(
            result.hypotheses[0].state,
            EvidenceState.SUPPORTED,
        )

    def test_two_clear_lanes_join_and_any_ambiguous_lane_is_unavailable(
        self,
    ) -> None:
        first = self._solve("lane_1", 20.0, 140.0)
        second = self._solve("lane_2", 30.0, 150.0)
        joint = join_dual_lane_hypotheses(
            first.hypotheses,
            second.hypotheses,
        )
        self.assertEqual(joint.state, EvidenceState.SUPPORTED)

        competing_id = ObservationId("lane_2:competing")
        duplicate = replace(
            second.hypotheses[0],
            observation_id=competing_id,
            provenance=replace(
                second.hypotheses[0].provenance,
                observation_id=competing_id,
            ),
        )
        ambiguous = join_dual_lane_hypotheses(
            first.hypotheses,
            (*second.hypotheses, duplicate),
        )
        self.assertEqual(ambiguous.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(ambiguous.selected_pair_ids)

        missing = join_dual_lane_hypotheses(first.hypotheses, ())
        self.assertEqual(missing.state, EvidenceState.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
