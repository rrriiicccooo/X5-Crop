from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_sequence_measurement,
    phase_template,
)
from x5crop.detection.photo_geometry.aggregate_edge_support import (
    placement_sequence_edges_with_material_support,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    AggregateEdgeResolution,
    AggregateEdgeResolutionKind,
    BoundaryEdgeMeasurementBasis,
    SeparatorBandMeasurementBasis,
)
from x5crop.detection.photo_geometry.outer_material import (
    observe_outer_material_boundaries,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    assess_direct_role_binding_authority,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.domain import EvidenceState, FiniteInterval


def _edge(
    name: str,
    coordinate: float,
    role: BoundaryRole,
    *,
    source_wide: bool = True,
    basis: BoundaryEdgeMeasurementBasis = (
        BoundaryEdgeMeasurementBasis.DIRECT_TRACE
    ),
):
    return replace(
        phase_edge(name, coordinate),
        trace_coordinates_px=(
            (0, 10, 20) if source_wide else (10, 20)
        ),
        support_fraction=(1.0 if source_wide else 2.0 / 3.0),
        continuous_support_fraction=(
            1.0 if source_wide else 2.0 / 3.0
        ),
        measurement_basis=basis,
        qualified_anchor_roles=(role,),
    )


class OuterMaterialContractTest(unittest.TestCase):
    def test_two_region_start_material_transfers_from_exterior_once(
        self,
    ) -> None:
        exterior = _edge("outer:start:exterior", 10.0, BoundaryRole.START)
        boundary = _edge(
            "outer:start:boundary",
            20.0,
            BoundaryRole.START,
            source_wide=False,
        )
        band = phase_separator(
            "outer:start:band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
            region_count=2,
        )

        observations = observe_outer_material_boundaries(
            (band,),
            (),
            (exterior, boundary),
            direction=1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(
                (exterior.observation_id,)
            ),
        )

        self.assertEqual(len(observations), 1)
        observation = observations[0]
        self.assertEqual(observation.role, BoundaryRole.START)
        self.assertEqual(
            observation.boundary_edge_observation_id,
            boundary.observation_id,
        )
        self.assertEqual(
            observation.exterior_edge_observation_id,
            exterior.observation_id,
        )
        self.assertEqual(observation.independent_support_region_count, 2)
        self.assertTrue(observation.exterior_edge_has_intrinsic_authority)

    def test_two_region_material_without_exterior_authority_is_not_fact(
        self,
    ) -> None:
        exterior = _edge(
            "outer:unsupported:exterior",
            10.0,
            BoundaryRole.START,
            source_wide=False,
        )
        boundary = _edge(
            "outer:unsupported:boundary",
            20.0,
            BoundaryRole.START,
            source_wide=False,
        )
        band = phase_separator(
            "outer:unsupported:band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
            region_count=2,
        )

        self.assertEqual(
            observe_outer_material_boundaries(
                (band,),
                (),
                (exterior, boundary),
                direction=1,
                maximum_material_width_px=20.0,
                intrinsic_authority_edge_ids=frozenset(),
            ),
            (),
        )

    def test_material_wider_than_the_calibrated_local_gap_is_not_fact(
        self,
    ) -> None:
        exterior = _edge("outer:wide:exterior", 10.0, BoundaryRole.START)
        boundary = _edge("outer:wide:boundary", 40.0, BoundaryRole.START)
        band = phase_separator(
            "outer:wide:band",
            exterior,
            boundary,
            FiniteInterval(29.0, 31.0),
        )

        self.assertEqual(
            observe_outer_material_boundaries(
                (band,),
                (),
                (exterior, boundary),
                direction=1,
                maximum_material_width_px=20.0,
                intrinsic_authority_edge_ids=frozenset(),
            ),
            (),
        )

    def test_only_spatially_outermost_pair_can_describe_start(self) -> None:
        exterior = _edge("outer:first:exterior", 10.0, BoundaryRole.START)
        boundary = _edge("outer:first:boundary", 20.0, BoundaryRole.START)
        later_exterior = _edge(
            "outer:later:exterior",
            100.0,
            BoundaryRole.START,
        )
        later_boundary = _edge(
            "outer:later:boundary",
            110.0,
            BoundaryRole.START,
        )
        first_band = phase_separator(
            "outer:first:band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
        )
        later_band = phase_separator(
            "outer:later:band",
            later_exterior,
            later_boundary,
            FiniteInterval(9.0, 11.0),
        )

        observations = observe_outer_material_boundaries(
            (first_band, later_band),
            (),
            (exterior, boundary, later_exterior, later_boundary),
            direction=1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(),
        )

        self.assertEqual(len(observations), 1)
        self.assertEqual(
            observations[0].boundary_edge_observation_id,
            boundary.observation_id,
        )

    def test_overlapping_outermost_explanations_remain_unresolved(self) -> None:
        exterior_one = _edge(
            "outer:ambiguous:exterior-1",
            10.0,
            BoundaryRole.START,
        )
        boundary_one = _edge(
            "outer:ambiguous:boundary-1",
            20.0,
            BoundaryRole.START,
        )
        exterior_two = _edge(
            "outer:ambiguous:exterior-2",
            10.1,
            BoundaryRole.START,
        )
        boundary_two = _edge(
            "outer:ambiguous:boundary-2",
            20.1,
            BoundaryRole.START,
        )
        bands = (
            phase_separator(
                "outer:ambiguous:band-1",
                exterior_one,
                boundary_one,
                FiniteInterval(9.0, 11.0),
            ),
            phase_separator(
                "outer:ambiguous:band-2",
                exterior_two,
                boundary_two,
                FiniteInterval(9.0, 11.0),
            ),
        )

        self.assertEqual(
            observe_outer_material_boundaries(
                bands,
                (),
                (
                    exterior_one,
                    boundary_one,
                    exterior_two,
                    boundary_two,
                ),
                direction=1,
                maximum_material_width_px=20.0,
                intrinsic_authority_edge_ids=frozenset(),
            ),
            (),
        )

    def test_reverse_direction_end_material_keeps_physical_sides(
        self,
    ) -> None:
        exterior = _edge("outer:end:exterior", 10.0, BoundaryRole.END)
        boundary = _edge(
            "outer:end:boundary",
            20.0,
            BoundaryRole.END,
            source_wide=False,
        )
        band = phase_separator(
            "outer:end:band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
            region_count=2,
        )

        observation = observe_outer_material_boundaries(
            (band,),
            (),
            (exterior, boundary),
            direction=-1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(
                (exterior.observation_id,)
            ),
        )[0]

        self.assertEqual(observation.role, BoundaryRole.END)
        self.assertEqual(
            observation.boundary_edge_observation_id,
            boundary.observation_id,
        )
        self.assertEqual(
            observation.exterior_edge_observation_id,
            exterior.observation_id,
        )

    def test_correlated_aggregate_material_collapses_to_one_group(
        self,
    ) -> None:
        exterior = _edge("outer:merged:exterior", 10.0, BoundaryRole.START)
        boundary = _edge(
            "outer:merged:boundary",
            20.0,
            BoundaryRole.START,
            source_wide=False,
        )
        direct_band = phase_separator(
            "outer:merged:direct-band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
            region_count=2,
        )
        aggregate_exterior = _edge(
            "outer:merged:aggregate-exterior",
            10.0,
            BoundaryRole.START,
            basis=BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        aggregate_boundary = _edge(
            "outer:merged:aggregate-boundary",
            20.0,
            BoundaryRole.START,
            basis=BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        aggregate_band = replace(
            phase_separator(
                "outer:merged:aggregate-band",
                aggregate_exterior,
                aggregate_boundary,
                FiniteInterval(9.0, 11.0),
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )
        resolutions = tuple(
            AggregateEdgeResolution(
                support_observation_id=aggregate.observation_id,
                state=EvidenceState.SUPPORTED,
                kind=AggregateEdgeResolutionKind.MATCHED_EXISTING_EDGE,
                compatible_existing_edge_ids=(direct.observation_id,),
                final_edge_observation_id=direct.observation_id,
                failure_kind=None,
            )
            for aggregate, direct in (
                (aggregate_exterior, exterior),
                (aggregate_boundary, boundary),
            )
        )

        observation = observe_outer_material_boundaries(
            (direct_band, aggregate_band),
            resolutions,
            (exterior, boundary),
            direction=1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(
                (exterior.observation_id,)
            ),
        )[0]

        self.assertEqual(
            observation.supporting_band_observation_ids,
            tuple(
                sorted(
                    (
                        direct_band.observation_id,
                        aggregate_band.observation_id,
                    )
                )
            ),
        )
        self.assertEqual(
            observation.measurement_bases,
            (
                SeparatorBandMeasurementBasis.DIRECT_TRACE,
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
            ),
        )
        self.assertEqual(observation.independent_support_region_count, 3)

    def test_outer_material_admits_only_boundary_from_registered_exterior(
        self,
    ) -> None:
        exterior = _edge("outer:standalone:exterior", 10.0, BoundaryRole.START)
        aggregate_exterior = _edge(
            "outer:standalone:aggregate-exterior",
            10.0,
            BoundaryRole.START,
            basis=BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        boundary = _edge(
            "outer:standalone:boundary",
            20.0,
            BoundaryRole.START,
            basis=BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        )
        band = replace(
            phase_separator(
                "outer:standalone:band",
                aggregate_exterior,
                boundary,
                FiniteInterval(9.0, 11.0),
            ),
            measurement_basis=(
                SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )
        resolutions = (
            AggregateEdgeResolution(
                support_observation_id=aggregate_exterior.observation_id,
                state=EvidenceState.SUPPORTED,
                kind=AggregateEdgeResolutionKind.MATCHED_EXISTING_EDGE,
                compatible_existing_edge_ids=(exterior.observation_id,),
                final_edge_observation_id=exterior.observation_id,
                failure_kind=None,
            ),
            AggregateEdgeResolution(
                support_observation_id=boundary.observation_id,
                state=EvidenceState.SUPPORTED,
                kind=AggregateEdgeResolutionKind.STANDALONE_EDGE,
                compatible_existing_edge_ids=(),
                final_edge_observation_id=boundary.observation_id,
                failure_kind=None,
            ),
        )
        outer = observe_outer_material_boundaries(
            (band,),
            resolutions,
            (exterior, boundary),
            direction=1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(),
        )

        self.assertEqual(
            placement_sequence_edges_with_material_support(
                (exterior, boundary),
                (),
                outer,
            ),
            (exterior, boundary),
        )

    def test_only_inner_edge_can_own_first_start(self) -> None:
        exterior = _edge("outer:phase:exterior", 10.0, BoundaryRole.START)
        boundary = _edge(
            "outer:phase:boundary",
            20.0,
            BoundaryRole.START,
            source_wide=False,
        )
        end_one = _edge("outer:phase:end-1", 120.0, BoundaryRole.END)
        start_two = _edge(
            "outer:phase:start-2",
            140.0,
            BoundaryRole.START,
        )
        end_two = _edge("outer:phase:end-2", 240.0, BoundaryRole.END)
        observations = (exterior, boundary, end_one, start_two, end_two)
        band = phase_separator(
            "outer:phase:band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
            region_count=2,
        )
        outer = observe_outer_material_boundaries(
            (band,),
            (),
            observations,
            direction=1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(
                (exterior.observation_id,)
            ),
        )

        result = fit_template_phase(
            observations,
            phase_template(2),
            outer_material_boundaries=outer,
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "outer-material-phase",
                    FiniteInterval(0.0, 260.0),
                ),
            ),
        )

        self.assertEqual(result.status.value, "resolved")
        assert result.best is not None
        self.assertEqual(
            result.best.role_bindings[0].observation_id,
            boundary.observation_id,
        )
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None
        authority = projection.input_direct_role_authority
        first = authority.facts[0]
        self.assertIn(
            DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,
            first.bases,
        )
        self.assertEqual(
            first.supporting_outer_material_observation_ids,
            (outer[0].observation_id,),
        )
        self.assertEqual(
            first.evidence_group_id,
            outer[0].evidence_group_id,
        )

    def test_exterior_edge_is_counterevidence_for_first_start(self) -> None:
        exterior = _edge(
            "outer:conflict:exterior",
            10.0,
            BoundaryRole.START,
        )
        boundary = _edge(
            "outer:conflict:boundary",
            20.0,
            BoundaryRole.START,
            source_wide=False,
        )
        end_one = _edge("outer:conflict:end-1", 110.0, BoundaryRole.END)
        start_two = _edge(
            "outer:conflict:start-2",
            130.0,
            BoundaryRole.START,
        )
        end_two = _edge("outer:conflict:end-2", 230.0, BoundaryRole.END)
        band = phase_separator(
            "outer:conflict:band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
            region_count=2,
        )
        observations = (exterior, boundary, end_one, start_two, end_two)
        outer = observe_outer_material_boundaries(
            (band,),
            (),
            observations,
            direction=1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(
                (exterior.observation_id,)
            ),
        )
        wrong = fit_template_phase(
            (exterior, end_one, start_two, end_two),
            phase_template(2),
        ).best
        assert wrong is not None

        authority = assess_direct_role_binding_authority(
            wrong,
            observations,
            (),
            (
                phase_sequence_measurement(
                    "outer-material-conflict",
                    FiniteInterval(0.0, 260.0),
                ),
            ),
            outer_material_boundaries=outer,
        )

        first = authority.facts[0]
        self.assertEqual(first.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            first.blocking_material_conflict_ids,
            (outer[0].observation_id,),
        )

    def test_outer_material_cannot_authorize_an_internal_start(self) -> None:
        start_one = _edge(
            "outer:internal:start-1",
            20.0,
            BoundaryRole.START,
        )
        end_one = _edge("outer:internal:end-1", 120.0, BoundaryRole.END)
        exterior = _edge(
            "outer:internal:exterior",
            130.0,
            BoundaryRole.START,
        )
        boundary = _edge(
            "outer:internal:boundary",
            140.0,
            BoundaryRole.START,
            source_wide=False,
        )
        end_two = _edge("outer:internal:end-2", 240.0, BoundaryRole.END)
        observations = (start_one, end_one, exterior, boundary, end_two)
        band = phase_separator(
            "outer:internal:band",
            exterior,
            boundary,
            FiniteInterval(9.0, 11.0),
            region_count=2,
        )
        outer = observe_outer_material_boundaries(
            (band,),
            (),
            observations,
            direction=1,
            maximum_material_width_px=20.0,
            intrinsic_authority_edge_ids=frozenset(
                (exterior.observation_id,)
            ),
        )
        selected = fit_template_phase(
            (start_one, end_one, boundary, end_two),
            phase_template(2),
        ).best
        assert selected is not None

        authority = assess_direct_role_binding_authority(
            selected,
            observations,
            (),
            (
                phase_sequence_measurement(
                    "outer-material-internal",
                    FiniteInterval(0.0, 260.0),
                ),
            ),
            outer_material_boundaries=outer,
        )

        internal = next(
            item for item in authority.facts if item.role_index == 2
        )
        self.assertEqual(internal.state, EvidenceState.UNAVAILABLE)
        self.assertNotIn(
            DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,
            internal.bases,
        )


if __name__ == "__main__":
    unittest.main()
