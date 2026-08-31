from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.detection.photo_geometry.aggregate_edge_support import (
    placement_sequence_edges_with_aggregate_support,
    resolve_aggregate_edge_support,
    resolve_aggregate_separator_support,
)
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    AggregateEdgeResolutionFailureKind,
    AggregateEdgeResolutionKind,
    SeparatorBandMeasurementBasis,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryTransition,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.domain import FiniteInterval, ObservationId
from tools.tests.template_test_support import phase_separator


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


class AggregateEdgeSupportContractTest(unittest.TestCase):
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
        *,
        aggregate_basis: BoundaryEdgeMeasurementBasis = (
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        ),
        bind_direct_edge: bool = True,
    ):
        direct_edges = tuple(item[0] for item in direct_values)
        aggregate_edges = tuple(item[0] for item in aggregate_values)
        transitions = {
            str(item.transition_id): item
            for value in (*direct_values, *aggregate_values)
            for item in value[1]
        }
        return resolve_aggregate_edge_support(
            direct_edges,
            aggregate_edges,
            transitions,
            registered_trace_lattice=tuple(range(0, 81, 10)),
            aggregate_basis=aggregate_basis,
            bind_direct_edge=bind_direct_edge,
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
            BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE,
        )
        self.assertEqual(
            edges[0].aggregate_support_id,
            aggregate[0].observation_id,
        )
        self.assertEqual(
            resolutions[0].kind,
            AggregateEdgeResolutionKind.BOUND_DIRECT_EDGE,
        )

    def test_standalone_three_region_aggregate_enters_once(self) -> None:
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

        self.assertEqual(len(edges), 2)
        self.assertIn(aggregate[0], edges)
        self.assertEqual(
            resolutions[0].kind,
            AggregateEdgeResolutionKind.STANDALONE_EDGE,
        )
        self.assertEqual(
            resolutions[0].final_edge_observation_id,
            aggregate[0].observation_id,
        )

    def test_two_region_aggregate_is_typed_unavailable(self) -> None:
        aggregate = _edge(
            "aggregate-two-regions",
            150.0,
            (10, 40),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )

        edges, resolutions = self._resolve((), (aggregate,))

        self.assertEqual(edges, ())
        self.assertEqual(
            resolutions[0].state.value,
            "unavailable",
        )
        self.assertEqual(
            resolutions[0].kind,
            AggregateEdgeResolutionKind.INSUFFICIENT_SPATIAL_SUPPORT,
        )
        self.assertEqual(
            resolutions[0].failure_kind,
            AggregateEdgeResolutionFailureKind
            .INSUFFICIENT_INDEPENDENT_SPATIAL_SUPPORT,
        )

    def test_standalone_edges_enter_placement_only_as_verified_pair(
        self,
    ) -> None:
        left_value = _edge(
            "aggregate-left",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        right_value = _edge(
            "aggregate-right",
            120.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        left = (
            replace(
                left_value[0],
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            left_value[1],
        )
        right = right_value

        edges, resolutions = self._resolve((), (left, right))
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(edges, ()),
            (),
        )
        aggregate_band = replace(
            phase_separator(
                "aggregate-band",
                left[0],
                right[0],
                FiniteInterval(19.0, 21.0),
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )
        projected = resolve_aggregate_separator_support(
            (aggregate_band,),
            resolutions,
            edges,
            (),
            aggregate_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )

        self.assertEqual(len(projected), 1)
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(
                edges,
                projected,
            ),
            edges,
        )

    def test_two_region_material_does_not_admit_standalone_edges(self) -> None:
        left_value = _edge(
            "aggregate-left-partial-material",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        right = _edge(
            "aggregate-right-partial-material",
            120.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        left = (
            replace(
                left_value[0],
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            left_value[1],
        )
        edges, resolutions = self._resolve((), (left, right))
        partial_band = replace(
            phase_separator(
                "aggregate-partial-material-band",
                left[0],
                right[0],
                FiniteInterval(19.0, 21.0),
                region_count=2,
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )

        projected = resolve_aggregate_separator_support(
            (partial_band,),
            resolutions,
            edges,
            (),
            aggregate_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )

        self.assertEqual(projected, ())
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(
                edges,
                projected,
            ),
            (),
        )

    def test_broad_material_standalone_edges_require_one_verified_pair(
        self,
    ) -> None:
        left_value = _edge(
            "broad-left",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )
        right = _edge(
            "broad-right",
            120.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )
        left = (
            replace(
                left_value[0],
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            left_value[1],
        )
        edges, resolutions = self._resolve(
            (),
            (left, right),
            aggregate_basis=(
                BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(edges, ()),
            (),
        )
        broad_band = replace(
            phase_separator(
                "broad-band",
                left[0],
                right[0],
                FiniteInterval(19.0, 21.0),
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )

        projected = resolve_aggregate_separator_support(
            (broad_band,),
            resolutions,
            edges,
            (),
            aggregate_basis=(
                SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )

        self.assertEqual(len(projected), 1)
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(edges, projected),
            edges,
        )

    def test_broad_material_cannot_enhance_one_unpaired_direct_edge(
        self,
    ) -> None:
        direct = _edge(
            "direct-short-for-broad",
            100.0,
            (0, 10),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        broad = _edge(
            "broad-matched-direct",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )

        edges, resolutions = self._resolve(
            (direct,),
            (broad,),
            aggregate_basis=(
                BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
            bind_direct_edge=False,
        )

        self.assertEqual(edges, (direct[0],))
        self.assertEqual(
            edges[0].measurement_basis,
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        self.assertEqual(
            resolutions[0].kind,
            AggregateEdgeResolutionKind.MATCHED_EXISTING_EDGE,
        )

    def test_broad_material_pair_reuses_direct_edge_without_enhancing_it(
        self,
    ) -> None:
        direct_value = _edge(
            "direct-for-broad-pair",
            100.0,
            (0, 10),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        broad_left_value = _edge(
            "broad-pair-left",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )
        broad_right = _edge(
            "broad-pair-right",
            120.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )
        direct = (
            replace(
                direct_value[0],
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            direct_value[1],
        )
        broad_left = (
            replace(
                broad_left_value[0],
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            broad_left_value[1],
        )
        edges, resolutions = self._resolve(
            (direct,),
            (broad_left, broad_right),
            aggregate_basis=(
                BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
            bind_direct_edge=False,
        )
        band = replace(
            phase_separator(
                "broad-mixed-band",
                broad_left[0],
                broad_right[0],
                FiniteInterval(19.0, 21.0),
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )

        projected = resolve_aggregate_separator_support(
            (band,),
            resolutions,
            edges,
            (),
            aggregate_basis=(
                SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )

        self.assertEqual(len(projected), 1)
        self.assertEqual(
            projected[0].left_edge_observation_id,
            direct[0].observation_id,
        )
        self.assertEqual(
            edges[0].measurement_basis,
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(edges, projected),
            edges,
        )

    def test_broad_pair_cannot_reassign_one_canonical_separator_edge(
        self,
    ) -> None:
        direct_left_value = _edge(
            "canonical-left",
            100.0,
            (0, 40, 80),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        direct_right = _edge(
            "canonical-right",
            120.0,
            (0, 40, 80),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        broad_left_value = _edge(
            "broad-competing-left",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )
        broad_right = _edge(
            "broad-competing-right",
            130.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )
        direct_left = (
            replace(
                direct_left_value[0],
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            direct_left_value[1],
        )
        broad_left = (
            replace(
                broad_left_value[0],
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            broad_left_value[1],
        )
        edges, resolutions = self._resolve(
            (direct_left, direct_right),
            (broad_left, broad_right),
            aggregate_basis=(
                BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
            bind_direct_edge=False,
        )
        canonical = phase_separator(
            "canonical-band",
            direct_left[0],
            direct_right[0],
            FiniteInterval(19.0, 21.0),
        )
        competing = replace(
            phase_separator(
                "broad-competing-band",
                broad_left[0],
                broad_right[0],
                FiniteInterval(29.0, 31.0),
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )

        projected = resolve_aggregate_separator_support(
            (competing,),
            resolutions,
            edges,
            (canonical,),
            aggregate_basis=(
                SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )

        self.assertEqual(projected, ())

    def test_role_incompatible_pair_does_not_admit_standalone_edges(
        self,
    ) -> None:
        left_value = _edge(
            "aggregate-left-wrong-role",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        right = _edge(
            "aggregate-right-role-compatible",
            120.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        left = (
            replace(left_value[0], polarity=-1),
            left_value[1],
        )
        edges, resolutions = self._resolve((), (left, right))
        aggregate_band = replace(
            phase_separator(
                "aggregate-role-incompatible-band",
                left[0],
                right[0],
                FiniteInterval(19.0, 21.0),
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )

        projected = resolve_aggregate_separator_support(
            (aggregate_band,),
            resolutions,
            edges,
            (),
            aggregate_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )

        self.assertEqual(projected, ())
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(
                edges,
                projected,
            ),
            (),
        )

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
            AggregateEdgeResolutionKind.AMBIGUOUS_EXISTING_MATCH,
        )
        self.assertEqual(
            resolutions[0].failure_kind,
            AggregateEdgeResolutionFailureKind.MULTIPLE_COMPATIBLE_EXISTING_EDGES,
        )
        with self.assertRaises(ValueError):
            replace(
                resolutions[0],
                failure_kind=(
                    AggregateEdgeResolutionFailureKind
                    .MULTIPLE_AGGREGATES_FOR_ONE_EXISTING_EDGE
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
            AggregateEdgeResolutionKind.REDUNDANT_EXISTING_EDGE,
        )

    def test_missing_direct_direction_does_not_duplicate_same_edge(
        self,
    ) -> None:
        direct_value = _edge(
            "direct-wide-no-direction",
            100.0,
            (0, 40, 80),
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
        )
        direct = (
            replace(
                direct_value[0],
                canonical_direction_degrees=None,
                fit_direction_interval_degrees=None,
                full_direction_interval_degrees=None,
            ),
            direct_value[1],
        )
        aggregate = _edge(
            "aggregate-same-edge",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )

        edges, resolutions = self._resolve((direct,), (aggregate,))

        self.assertEqual(edges, (direct[0],))
        self.assertEqual(
            resolutions[0].kind,
            AggregateEdgeResolutionKind.REDUNDANT_EXISTING_EDGE,
        )

    def test_redundant_aggregate_does_not_admit_unpaired_existing_edge(
        self,
    ) -> None:
        existing = _edge(
            "cross-height-existing",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        broad = _edge(
            "broad-redundant",
            100.0,
            (10, 40, 70),
            BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
        )

        edges, resolutions = self._resolve(
            (existing,),
            (broad,),
            aggregate_basis=(
                BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE
            ),
        )

        self.assertEqual(edges, (existing[0],))
        self.assertEqual(
            resolutions[0].kind,
            AggregateEdgeResolutionKind.REDUNDANT_EXISTING_EDGE,
        )
        self.assertEqual(
            placement_sequence_edges_with_aggregate_support(edges, ()),
            (),
        )


if __name__ == "__main__":
    unittest.main()
