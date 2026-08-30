from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.detection.photo_geometry.cross_height_edge_support import (
    resolve_cross_height_edge_support,
)
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    CrossHeightEdgeResolutionFailureKind,
    CrossHeightEdgeResolutionKind,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryTransition,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.domain import FiniteInterval, ObservationId


def _edge(
    name: str,
    coordinate: float,
    traces: tuple[int, ...],
    basis: BoundaryEdgeMeasurementBasis,
) -> tuple[
    BoundaryEdgeObservation,
    tuple[PhotoBoundaryTransition, ...],
]:
    transition_values = tuple(
        PhotoBoundaryTransition(
            transition_id=ObservationId(f"transition:{name}:{trace}"),
            query_id="query:shared",
            trace_ordinal=ordinal,
            trace_coordinate_px=trace,
            canonical_coordinate_px=coordinate,
            localization_interval_px=FiniteInterval(
                coordinate - 0.2,
                coordinate + 0.2,
            ),
            physical_position_interval_px=FiniteInterval(
                coordinate - 0.5,
                coordinate + 0.5,
            ),
            gradient_z=4.0,
            tone_z=4.0,
            texture_z=0.0,
            left_tone_mean=10.0,
            right_tone_mean=20.0,
            left_texture_mean=1.0,
            right_texture_mean=5.0,
            polarity=1,
            peak_width_px=1.0,
            prominence=4.0,
            local_noise=0.0,
        )
        for ordinal, trace in enumerate(traces)
    )
    transition_ids = tuple(item.transition_id for item in transition_values)
    interval = FiniteInterval(coordinate - 0.5, coordinate + 0.5)
    run_id = f"run:{name}"
    return (
        BoundaryEdgeObservation(
            observation_id=ObservationId(f"edge:{name}"),
            run_id=run_id,
            discovery_interval_px=interval,
            reference_trace_px=40.0,
            canonical_position_px=coordinate,
            fit_position_interval_px=interval,
            full_position_interval_px=interval,
            transition_ids=transition_ids,
            trace_coordinates_px=traces,
            polarity=1,
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval(-0.2, 0.2),
            full_direction_interval_degrees=FiniteInterval(-0.5, 0.5),
            measurement_basis=basis,
            qualified_anchor_roles=(BoundaryRole.START,),
        ),
        transition_values,
    )


class CrossHeightEdgeSupportContractTest(unittest.TestCase):
    def _resolve(
        self,
        direct_values: tuple[
            tuple[
                BoundaryEdgeObservation,
                tuple[PhotoBoundaryTransition, ...],
            ],
            ...,
        ],
        aggregate_values: tuple[
            tuple[
                BoundaryEdgeObservation,
                tuple[PhotoBoundaryTransition, ...],
            ],
            ...,
        ],
    ):
        direct_edges = tuple(item[0] for item in direct_values)
        aggregate_edges = tuple(item[0] for item in aggregate_values)
        transitions = {
            str(item.transition_id): item
            for value in (*direct_values, *aggregate_values)
            for item in value[1]
        }
        return resolve_cross_height_edge_support(
            direct_edges,
            aggregate_edges,
            transitions,
            registered_trace_lattice=tuple(range(0, 81, 10)),
        )

    def test_unique_aggregate_enhances_one_short_direct_edge_once(self) -> None:
        direct = _edge(
            "direct-short",
            100.0,
            (0, 10),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        aggregate = _edge(
            "aggregate",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )

        edges, resolutions = self._resolve(
            (direct,),
            (aggregate,),
        )

        self.assertEqual(len(edges), 1)
        self.assertEqual(
            edges[0].measurement_basis,
            BoundaryEdgeMeasurementBasis.DIRECT_WITH_CROSS_HEIGHT,
        )
        self.assertEqual(
            edges[0].cross_height_support_id,
            aggregate[0].observation_id,
        )
        self.assertEqual(
            resolutions[0].kind,
            CrossHeightEdgeResolutionKind.BOUND_DIRECT_EDGE,
        )

    def test_standalone_aggregate_remains_a_non_placement_candidate(self) -> None:
        direct = _edge(
            "direct",
            100.0,
            (0, 10),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        aggregate = _edge(
            "aggregate-standalone",
            150.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )

        edges, resolutions = self._resolve(
            (direct,),
            (aggregate,),
        )

        self.assertEqual(edges, (direct[0],))
        self.assertEqual(
            resolutions[0].kind,
            CrossHeightEdgeResolutionKind.STANDALONE_CANDIDATE,
        )
        self.assertIsNone(resolutions[0].final_edge_observation_id)

    def test_multiple_direct_matches_remain_typed_ambiguous(self) -> None:
        direct_left = _edge(
            "direct-left",
            99.8,
            (0, 10),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        direct_right = _edge(
            "direct-right",
            100.2,
            (0, 10),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        aggregate = _edge(
            "aggregate-ambiguous",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )

        edges, resolutions = self._resolve(
            (direct_left, direct_right),
            (aggregate,),
        )

        self.assertEqual(len(edges), 2)
        self.assertEqual(
            resolutions[0].kind,
            CrossHeightEdgeResolutionKind.AMBIGUOUS_DIRECT_MATCH,
        )
        self.assertEqual(
            resolutions[0].failure_kind,
            CrossHeightEdgeResolutionFailureKind.MULTIPLE_COMPATIBLE_DIRECT_EDGES,
        )
        with self.assertRaises(ValueError):
            replace(
                resolutions[0],
                failure_kind=(
                    CrossHeightEdgeResolutionFailureKind
                    .MULTIPLE_SUPPORTS_FOR_ONE_DIRECT_EDGE
                ),
            )

    def test_source_wide_direct_edge_is_not_counted_twice(self) -> None:
        direct = _edge(
            "direct-wide",
            100.0,
            (0, 40, 80),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        aggregate = _edge(
            "aggregate-redundant",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )

        edges, resolutions = self._resolve(
            (direct,),
            (aggregate,),
        )

        self.assertEqual(edges, (direct[0],))
        self.assertEqual(
            resolutions[0].kind,
            CrossHeightEdgeResolutionKind.REDUNDANT_DIRECT_EDGE,
        )


if __name__ == "__main__":
    unittest.main()
