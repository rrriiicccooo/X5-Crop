from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
)
from x5crop.detection.photo_geometry.template_adjacency_coverage import (
    assess_adjacency_observation_coverage,
)
from x5crop.detection.photo_geometry.template_adjacency_topology import (
    AdjacencyContinuityBasis,
    AdjacencyContinuityFailureKind,
    AdjacencyContinuityKind,
    observe_adjacency_continuity,
)
from x5crop.detection.photo_geometry.template_contact import observe_contact_edges
from x5crop.detection.photo_geometry.model import (
    BoundaryEvidenceState,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.observation_types import (
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.template_residual import (
    ResidualPattern,
    derive_adjacency_relations,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase import (
    fit_template_phase_with_adjacency_relations,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from tools.tests.template_test_support import unavailable_nominal_grid_prior
from x5crop.detection.photo_geometry.template_model import (
    OverlapRelation,
    template_role_refinement_radius_px,
)
from x5crop.detection.photo_geometry.template_overlap import (
    observe_overlap_edge_pairs,
)
from x5crop.domain import EvidenceState, FiniteInterval


def _edges(*coordinates: float):
    return tuple(
        phase_edge(f"sequence:{index}", coordinate)
        for index, coordinate in enumerate(coordinates)
    )


def _observe(
    fit,
    edges,
    bands=(),
    *,
    complete: bool = True,
    register_overlap: bool = True,
):
    measurement = phase_sequence_measurement(
        "adjacency-continuity",
        FiniteInterval(0.0, 500.0),
        complete=complete,
    )
    coverage = assess_adjacency_observation_coverage(
        fit,
        (measurement,),
        directly_observed_ordinals=(),
    )
    overlap_pairs = (
        observe_overlap_edge_pairs(
            tuple(edges),
            tuple(bands),
            (measurement,),
            direction=fit.template.direction,
            maximum_overlap_px=template_role_refinement_radius_px(
                fit.template.pitch_px.maximum
            ),
        )
        if register_overlap
        else ()
    )
    return observe_adjacency_continuity(
        fit,
        tuple(edges),
        tuple(bands),
        coverage,
        overlap_pairs,
    )


def _contact_fit():
    edges = _edges(100.0, 200.0, 300.0)
    measurement = phase_sequence_measurement(
        "contact-candidate",
        FiniteInterval(0.0, 320.0),
    )
    contacts = observe_contact_edges(edges, (), (measurement,))
    result = fit_template_phase(
        edges,
        phase_template(2),
        contact_edge_observations=contacts,
    )
    assert result.best is not None
    return result.best, edges


class TemplateAdjacencyTopologyContractTests(unittest.TestCase):
    def test_overlap_is_refit_in_the_single_grid_and_prefix_model(self) -> None:
        edges = tuple(
            replace(
                phase_edge(f"overlap:{index}", coordinate),
                qualified_anchor_roles=(role,),
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                full_direction_interval_degrees=FiniteInterval.exact(0.0),
            )
            for index, (coordinate, role) in enumerate(
                (
                    (100.0, BoundaryRole.START),
                    (200.0, BoundaryRole.END),
                    (195.0, BoundaryRole.START),
                    (295.0, BoundaryRole.END),
                    (300.0, BoundaryRole.START),
                    (400.0, BoundaryRole.END),
                )
            )
        )
        base = phase_template(3)
        spec = replace(
            base,
            pitch_px=105.0,
            nominal_gap_px=5.0,
            phase_lattice_authority=replace(
                base.phase_lattice_authority,
                period_px=105.0,
            ),
        )
        measurement = phase_sequence_measurement(
            "overlap-end-to-end",
            FiniteInterval(0.0, 420.0),
        )
        overlap_pairs = observe_overlap_edge_pairs(
            edges,
            (),
            (measurement,),
            direction=1,
            maximum_overlap_px=12.0,
        )
        self.assertEqual(len(overlap_pairs), 1)

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=edges,
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=(
                    unavailable_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
                sequence_measurement_sets=(measurement,),
                overlap_edge_pair_observations=overlap_pairs,
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.model_role_positions_px,
            (100.0, 200.0, 195.0, 295.0, 300.0, 400.0),
        )
        self.assertEqual(len(result.best.adjacency_relations), 1)
        self.assertIsInstance(
            result.best.adjacency_relations[0],
            OverlapRelation,
        )
        self.assertEqual(
            result.adjacency_continuity_observations[0].kind,
            AdjacencyContinuityKind.OVERLAP,
        )

    def test_one_all_overlap_adjacency_does_not_fabricate_pitch_rank(
        self,
    ) -> None:
        edges = tuple(
            replace(
                phase_edge(f"rank-two-overlap:{index}", coordinate),
                qualified_anchor_roles=(role,),
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                full_direction_interval_degrees=FiniteInterval.exact(0.0),
            )
            for index, (coordinate, role) in enumerate(
                (
                    (100.0, BoundaryRole.START),
                    (200.0, BoundaryRole.END),
                    (195.0, BoundaryRole.START),
                    (295.0, BoundaryRole.END),
                )
            )
        )
        base = phase_template(2)
        spec = replace(
            base,
            pitch_px=105.0,
            nominal_gap_px=5.0,
            phase_lattice_authority=replace(
                base.phase_lattice_authority,
                period_px=105.0,
            ),
        )
        measurement = phase_sequence_measurement(
            "rank-two-overlap",
            FiniteInterval(0.0, 320.0),
        )
        overlap_pairs = observe_overlap_edge_pairs(
            edges,
            (),
            (measurement,),
            direction=1,
            maximum_overlap_px=12.0,
        )

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=edges,
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=(
                    unavailable_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
                sequence_measurement_sets=(measurement,),
                overlap_edge_pair_observations=overlap_pairs,
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE,
        )
        assert result.global_lattice_authority is not None
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 2)

    def test_selected_shared_edge_is_typed_contact(self) -> None:
        fit, edges = _contact_fit()

        (observation,) = _observe(fit, edges)
        analysis = derive_adjacency_relations(fit, (observation,))

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(observation.kind, AdjacencyContinuityKind.CONTACT)
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.SHARED_PHYSICAL_EDGE,
        )
        self.assertEqual(
            observation.end_observation_id,
            observation.next_start_observation_id,
        )
        self.assertEqual(
            observation.signed_gap_interval_px,
            FiniteInterval.exact(0.0),
        )
        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
        self.assertEqual(analysis.relations, fit.adjacency_relations)

    def test_contact_requires_complete_registered_corridor(self) -> None:
        fit, edges = _contact_fit()

        (observation,) = _observe(fit, edges, complete=False)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
        )

    def test_unique_positive_material_band_supports_normal_separator(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)
        band = phase_separator(
            "separator:normal",
            edges[1],
            edges[2],
            FiniteInterval(19.8, 20.2),
        )

        (observation,) = _observe(fit, edges, (band,))

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.SEPARATOR_MATERIAL,
        )
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.POSITIVE_SEPARATOR_BAND,
        )
        self.assertTrue(observation.directly_observed_separator)

    def test_complete_corridor_records_only_absence_of_counterevidence(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)

        (observation,) = _observe(fit, edges)

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED,
        )
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.COMPLETE_REGISTERED_CORRIDOR,
        )
        self.assertFalse(observation.directly_observed_separator)

    def test_registered_material_conflict_stays_unresolved(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)
        band = phase_separator(
            "separator:conflict",
            edges[1],
            edges[2],
            FiniteInterval(19.8, 20.2),
        )
        band = replace(
            band,
            material_support_region_count=1,
            material_regions=tuple(
                region
                if region.region_index == 0
                else replace(
                    region,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                )
                for region in band.material_regions
            ),
            evidence_state=BoundaryEvidenceState.CONTRADICTION,
        )

        (observation,) = _observe(fit, edges, (band,))

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.SEPARATOR_MATERIAL_UNRESOLVED,
        )
        self.assertEqual(
            observation.separator_band_observation_ids,
            (band.observation_id,),
        )

    def test_multiple_separator_bands_preserve_provenance_and_block(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)
        bands = tuple(
            phase_separator(
                f"separator:{index}",
                edges[1],
                edges[2],
                FiniteInterval(19.8, 20.2),
            )
            for index in range(2)
        )

        (observation,) = _observe(fit, edges, bands)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(observation.kind, AdjacencyContinuityKind.UNRESOLVED)
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.MULTIPLE_SEPARATOR_BANDS,
        )
        self.assertEqual(
            observation.separator_band_observation_ids,
            tuple(sorted(band.observation_id for band in bands)),
        )

    def test_reversed_direct_edges_with_complete_coverage_prove_overlap(
        self,
    ) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)

        (observation,) = _observe(fit, edges)
        analysis = derive_adjacency_relations(fit, (observation,))

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.OVERLAP,
        )
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.INDEPENDENT_REVERSED_EDGES,
        )
        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
        self.assertIsInstance(analysis.relations[0], OverlapRelation)
        relation = analysis.relations[0]
        assert isinstance(relation, OverlapRelation)
        self.assertEqual(
            relation.supporting_observation_ids,
            (edges[1].observation_id, edges[2].observation_id),
        )
        self.assertLess(relation.canonical_signed_gap_px, 0.0)

    def test_reversed_edges_without_registered_pair_stay_unresolved(
        self,
    ) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)

        (observation,) = _observe(
            fit,
            edges,
            register_overlap=False,
        )

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(observation.kind, AdjacencyContinuityKind.UNRESOLVED)
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.OVERLAP_OBSERVATION_UNAVAILABLE,
        )

    def test_material_conflict_blocks_reversed_edge_overlap(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)
        band = phase_separator(
            "separator:conflict",
            edges[1],
            edges[2],
            FiniteInterval(4.8, 5.2),
        )
        band = replace(
            band,
            material_support_region_count=1,
            material_regions=tuple(
                region
                if region.region_index == 0
                else replace(
                    region,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                )
                for region in band.material_regions
            ),
            evidence_state=BoundaryEvidenceState.CONTRADICTION,
        )

        (observation,) = _observe(fit, edges, (band,))

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED,
        )

    def test_reversed_edges_without_complete_coverage_do_not_prove_overlap(
        self,
    ) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)

        (observation,) = _observe(fit, edges, complete=False)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
        )

    def test_gap_uncertainty_crossing_zero_remains_unresolved(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 200.0, 300.0)

        (observation,) = _observe(fit, edges)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.UNRESOLVED,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.SIGNED_GAP_CROSSES_ZERO,
        )

    def test_incomplete_corridor_cannot_claim_no_counterevidence(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 220.0, 320.0)

        (observation,) = _observe(fit, edges, complete=False)

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        )
        self.assertEqual(
            observation.failure_kind,
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
        )


if __name__ == "__main__":
    unittest.main()
