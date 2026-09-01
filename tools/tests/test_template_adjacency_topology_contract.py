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
from x5crop.detection.photo_geometry.model import BoundaryEvidenceState
from x5crop.detection.photo_geometry.observation_types import (
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.template_residual import (
    AdjacencyRelationFailureKind,
    ResidualPattern,
    derive_adjacency_relations,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
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
    return observe_adjacency_continuity(
        fit,
        tuple(edges),
        tuple(bands),
        coverage,
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
        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_ADVANCES)
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

    def test_reversed_direct_edges_are_typed_normal_counterevidence(self) -> None:
        fit = placement_sequence(phase_template(2))
        edges = _edges(100.0, 200.0, 195.0, 295.0)

        (observation,) = _observe(fit, edges)
        analysis = derive_adjacency_relations(fit, (observation,))

        self.assertEqual(observation.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.NORMAL_SEPARATOR_COUNTEREVIDENCE,
        )
        self.assertEqual(
            observation.basis,
            AdjacencyContinuityBasis.REVERSED_DIRECT_EDGES,
        )
        self.assertEqual(analysis.pattern, ResidualPattern.UNRESOLVED)
        self.assertEqual(
            analysis.failure_kind,
            AdjacencyRelationFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED,
        )

    def test_material_unavailable_cannot_hide_reversed_direct_edges(self) -> None:
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

        self.assertEqual(observation.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            observation.kind,
            AdjacencyContinuityKind.NORMAL_SEPARATOR_COUNTEREVIDENCE,
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
