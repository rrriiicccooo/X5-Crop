from __future__ import annotations

import unittest

from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_template,
)
from x5crop.detection.photo_geometry.template_model import (
    ContactRelation,
    SeparatorRelationKind,
    SeparatorRelation,
)
from x5crop.detection.photo_geometry.template_nominal_grid_authority import (
    NominalGridRoleConstraint,
    assess_calibrated_nominal_grid_authority,
    compile_calibrated_nominal_grid_prior,
    nominal_grid_evidence_id,
    solve_calibrated_nominal_grid_envelope,
)
from x5crop.detection.photo_geometry.template_nominal_grid_model import (
    CalibratedNominalGridEvidence,
    NominalGridFailureKind,
)
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import format_spec


class TemplateNominalGridContractTest(unittest.TestCase):
    def test_format_prior_is_calibrated_but_does_not_supply_phase(self) -> None:
        physical = format_spec("135")
        prior = compile_calibrated_nominal_grid_prior(
            format_spec=physical,
            frame_spec=physical.frame,
            template_id="production-grid",
            scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        self.assertEqual(prior.state, EvidenceState.SUPPORTED)
        self.assertEqual(prior.pitch_px, FiniteInterval(376.5, 382.0))
        self.assertIsNone(prior.failure_kind)

        unavailable_format = format_spec("xpan")
        unavailable = compile_calibrated_nominal_grid_prior(
            format_spec=unavailable_format,
            frame_spec=unavailable_format.frame,
            template_id="uncalibrated-grid",
            scale_px_per_mm=PositiveInterval.exact(10.0),
        )
        self.assertEqual(unavailable.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            unavailable.failure_kind,
            NominalGridFailureKind.CALIBRATED_PRIOR_UNAVAILABLE,
        )

    def test_one_absolute_anchor_places_the_calibrated_zero_delta_grid(
        self,
    ) -> None:
        template = phase_template(3)
        constraint = NominalGridRoleConstraint(
            role_index=0,
            observation_id=ObservationId("start:1"),
            coordinate_px=40.0,
            full_interval_px=FiniteInterval.exact(40.0),
        )

        envelope, state = solve_calibrated_nominal_grid_envelope(
            prior=calibrated_nominal_grid_prior(template),
            template=template,
            integer_slot_offset=0,
            role_constraints=(constraint,),
            relations=(),
            phase_authority_px=None,
            retained_direct_constraint_rank=1,
        )

        self.assertEqual(
            envelope.role_positions_px,
            (40.0, 140.0, 160.0, 260.0, 280.0, 380.0),
        )
        self.assertEqual(state.phase_anchor_role_indices, (0,))
        self.assertEqual(
            state.phase_anchor_observation_ids,
            (ObservationId("start:1"),),
        )

    def test_one_adjacency_relation_propagates_once_through_the_same_grid(
        self,
    ) -> None:
        template = phase_template(3)
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval.exact(5.0),
            canonical_delta_px=5.0,
            separator_band_observation_id=ObservationId("separator:1"),
            end_edge_observation_id=ObservationId("end:1"),
            next_start_edge_observation_id=ObservationId("start:2"),
            signed_gap_interval_px=FiniteInterval.exact(25.0),
            canonical_signed_gap_px=25.0,
        )

        envelope, _state = solve_calibrated_nominal_grid_envelope(
            prior=calibrated_nominal_grid_prior(template),
            template=template,
            integer_slot_offset=0,
            role_constraints=(
                NominalGridRoleConstraint(
                    role_index=0,
                    observation_id=ObservationId("start:1"),
                    coordinate_px=40.0,
                    full_interval_px=FiniteInterval.exact(40.0),
                ),
            ),
            relations=(relation,),
            phase_authority_px=None,
            retained_direct_constraint_rank=1,
        )

        self.assertEqual(
            envelope.role_positions_px,
            (40.0, 140.0, 165.0, 265.0, 285.0, 385.0),
        )

    def test_direct_separator_gap_conflict_has_no_joint_grid_state(self) -> None:
        template = phase_template(2)
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval.exact(5.0),
            canonical_delta_px=5.0,
            separator_band_observation_id=ObservationId("separator:conflict"),
            end_edge_observation_id=ObservationId("end:1"),
            next_start_edge_observation_id=ObservationId("start:2"),
            signed_gap_interval_px=FiniteInterval.exact(25.0),
            canonical_signed_gap_px=25.0,
        )

        with self.assertRaisesRegex(
            ValueError,
            "calibrated nominal Grid has no joint feasible state",
        ):
            solve_calibrated_nominal_grid_envelope(
                prior=calibrated_nominal_grid_prior(template),
                template=template,
                integer_slot_offset=0,
                role_constraints=(
                    NominalGridRoleConstraint(
                        role_index=1,
                        observation_id=ObservationId("end:1"),
                        coordinate_px=140.0,
                        full_interval_px=FiniteInterval.exact(140.0),
                    ),
                    NominalGridRoleConstraint(
                        role_index=2,
                        observation_id=ObservationId("start:2"),
                        coordinate_px=160.0,
                        full_interval_px=FiniteInterval.exact(160.0),
                    ),
                ),
                relations=(relation,),
                phase_authority_px=None,
                retained_direct_constraint_rank=2,
            )

    def test_contact_is_the_exact_w_minus_pitch_grid_relation(self) -> None:
        template = phase_template(2)
        shared_id = ObservationId("contact:shared-edge")
        relation = ContactRelation(
            relation_ordinal=1,
            contact_observation_id=ObservationId("contact:observation"),
            physical_edge_id=shared_id,
            shared_edge_observation_id=shared_id,
            delta_interval_px=FiniteInterval.exact(-20.0),
            canonical_delta_px=-20.0,
            supporting_observation_ids=(shared_id,),
        )

        envelope, _state = solve_calibrated_nominal_grid_envelope(
            prior=calibrated_nominal_grid_prior(template),
            template=template,
            integer_slot_offset=0,
            role_constraints=(
                NominalGridRoleConstraint(
                    role_index=0,
                    observation_id=ObservationId("start:1"),
                    coordinate_px=40.0,
                    full_interval_px=FiniteInterval.exact(40.0),
                ),
                NominalGridRoleConstraint(
                    role_index=1,
                    observation_id=shared_id,
                    coordinate_px=140.0,
                    full_interval_px=FiniteInterval.exact(140.0),
                ),
            ),
            relations=(relation,),
            phase_authority_px=None,
            retained_direct_constraint_rank=2,
        )

        self.assertEqual(
            envelope.role_positions_px,
            (40.0, 140.0, 140.0, 240.0),
        )
        self.assertEqual(
            envelope.role_intervals_px[1],
            envelope.role_intervals_px[2],
        )

    def test_selected_output_binding_is_a_separate_authority(self) -> None:
        template = phase_template(2)
        _envelope, state = solve_calibrated_nominal_grid_envelope(
            prior=calibrated_nominal_grid_prior(template),
            template=template,
            integer_slot_offset=0,
            role_constraints=(
                NominalGridRoleConstraint(
                    role_index=0,
                    observation_id=ObservationId("start:1"),
                    coordinate_px=40.0,
                    full_interval_px=FiniteInterval.exact(40.0),
                ),
            ),
            relations=(),
            phase_authority_px=None,
            retained_direct_constraint_rank=1,
        )
        evidence = CalibratedNominalGridEvidence(
            evidence_id=nominal_grid_evidence_id(
                state,
                (1,),
                (2,),
                ("query:1",),
            ),
            state=EvidenceState.SUPPORTED,
            prior_id=state.prior_id,
            phase_anchor_role_indices=state.phase_anchor_role_indices,
            phase_anchor_observation_ids=state.phase_anchor_observation_ids,
            inferred_adjacency_ordinals=(1,),
            unobserved_frame_ordinals=(2,),
            covering_query_ids=("query:1",),
            failure_kind=None,
            reason=None,
        )

        authority = assess_calibrated_nominal_grid_authority(
            evidence,
            placement_id="placement:1",
            output_geometry_ids=("geometry:1", "geometry:2"),
        )
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(evidence.unobserved_frame_ordinals, (2,))

        incomplete = assess_calibrated_nominal_grid_authority(
            evidence,
            placement_id=None,
            output_geometry_ids=(),
        )
        self.assertEqual(incomplete.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            incomplete.failure_kind,
            NominalGridFailureKind.OUTPUT_FOOTPRINT_UNAVAILABLE,
        )


if __name__ == "__main__":
    unittest.main()
