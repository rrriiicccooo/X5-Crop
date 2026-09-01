from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_sequence_measurement,
    phase_template,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.template_contact import (
    ContactEdgeAuthorityBasis,
    ContactEdgeObservation,
    observe_contact_edges,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_model import ContactRelation
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
)


class TemplateContactContractTest(unittest.TestCase):
    def test_positive_separator_edges_cannot_become_contact_candidates(
        self,
    ) -> None:
        shared = phase_edge("shared", 110.0)
        left = phase_edge("separator:left", 200.0)
        right = phase_edge("separator:right", 230.0)
        observations = (shared, left, right)
        band = phase_separator(
            "separator:band",
            left,
            right,
            FiniteInterval(29.0, 31.0),
        )

        result = observe_contact_edges(
            observations,
            (band,),
            (
                phase_sequence_measurement(
                    "contact-window",
                    FiniteInterval(0.0, 250.0),
                ),
            ),
        )

        self.assertEqual(
            tuple(item.shared_edge_observation_id for item in result),
            (shared.observation_id,),
        )

    def test_overlapping_distinct_edge_identities_do_not_prove_contact(
        self,
    ) -> None:
        first = phase_edge("first-physical-edge", 110.0)
        second = phase_edge("second-physical-edge", 110.1)

        result = observe_contact_edges(
            (first, second),
            (),
            (
                phase_sequence_measurement(
                    "contact-window",
                    FiniteInterval(100.0, 120.0),
                ),
            ),
        )

        self.assertEqual(result, ())

    def test_separator_owned_identity_still_blocks_overlapping_contact(
        self,
    ) -> None:
        candidate = phase_edge("candidate-shared-edge", 110.0)
        separator_left = phase_edge("separator-left", 110.1)
        separator_right = phase_edge("separator-right", 130.0)
        band = phase_separator(
            "separator-band",
            separator_left,
            separator_right,
            FiniteInterval(19.0, 21.0),
        )

        result = observe_contact_edges(
            (candidate, separator_left, separator_right),
            (band,),
            (
                phase_sequence_measurement(
                    "contact-window",
                    FiniteInterval(100.0, 140.0),
                ),
            ),
        )

        self.assertEqual(result, ())

    def test_unique_shared_edge_enters_the_single_phase_candidate_pool(
        self,
    ) -> None:
        observations = (
            phase_edge("frame-1:start", 10.0),
            phase_edge("shared", 110.0),
            phase_edge("frame-2:end", 210.0),
        )
        contact_edges = observe_contact_edges(
            observations,
            (),
            (
                phase_sequence_measurement(
                    "contact-window",
                    FiniteInterval(0.0, 220.0),
                ),
            ),
        )

        result = fit_template_phase(
            observations,
            phase_template(2),
            contact_edge_observations=contact_edges,
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        (relation,) = result.best.adjacency_relations
        self.assertIsInstance(relation, ContactRelation)
        self.assertEqual(relation.relation_ordinal, 1)
        self.assertEqual(
            result.best.binding_observation_ids,
            (
                ObservationId("frame-1:start"),
                ObservationId("shared"),
                ObservationId("shared"),
                ObservationId("frame-2:end"),
            ),
        )
        self.assertEqual(
            result.best.model_role_positions_px,
            (10.0, 110.0, 110.0, 210.0),
        )

    def test_competing_contact_mappings_have_a_typed_topology_failure(
        self,
    ) -> None:
        observations = tuple(
            phase_edge(f"ambiguous:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 160.0, 260.0, 360.0, 380.0, 480.0)
            )
        )
        contact_edges = observe_contact_edges(
            observations,
            (),
            (
                phase_sequence_measurement(
                    "ambiguous-contact-window",
                    FiniteInterval(0.0, 500.0),
                ),
            ),
        )

        result = fit_template_phase(
            observations,
            phase_template(4),
            contact_edge_observations=contact_edges,
        )

        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS,
        )

    def test_contact_cannot_project_out_its_required_shared_edge(self) -> None:
        shared = replace(
            phase_edge("weak-shared", 110.0),
            trace_coordinates_px=(10, 20),
            support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0,
        )
        observations = (
            phase_edge("contact-frame-1:start", 10.0),
            shared,
            phase_edge("contact-frame-2:end", 210.0),
        )
        measurement = phase_sequence_measurement(
            "weak-contact-window",
            FiniteInterval(0.0, 220.0),
        )
        relation = ContactRelation(
            relation_ordinal=1,
            contact_observation_id=ObservationId("weak-contact-relation"),
            physical_edge_id=shared.observation_id,
            shared_edge_observation_id=shared.observation_id,
            delta_interval_px=FiniteInterval.exact(-20.0),
            canonical_delta_px=-20.0,
            supporting_observation_ids=(shared.observation_id,),
        )
        contact = ContactEdgeObservation(
            observation_id=relation.contact_observation_id,
            physical_edge_id=shared.observation_id,
            shared_edge_observation_id=shared.observation_id,
            authority_bases=(ContactEdgeAuthorityBasis.SOURCE_WIDE_EDGE,),
            qualified_anchor_roles=(BoundaryRole.START, BoundaryRole.END),
        )

        result = fit_template_phase(
            observations,
            phase_template(2),
            adjacency_relations=(relation,),
            contact_edge_observations=(contact,),
            sequence_measurement_sets=(measurement,),
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE,
        )
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.TOPOLOGY_BINDING_UNAVAILABLE,
        )
        self.assertEqual(
            projection.input_direct_role_authority.state,
            EvidenceState.UNAVAILABLE,
        )


if __name__ == "__main__":
    unittest.main()
