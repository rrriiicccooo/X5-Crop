from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_template,
    placement_sequence,
)
from x5crop.detection.photo_geometry.template_lattice_authority import direct_role_constraint_rank
from x5crop.detection.photo_geometry.template_model import (
    ContactRelation,
    LatticeParameterFitBasis,
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
    CalibratedNominalGridFitState,
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

    @staticmethod
    def _contact_anchor_fixture():
        template = phase_template(2)
        start_id = ObservationId("contact:start:1")
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
        base = placement_sequence(template, missing=(3,))
        assert base.role_bindings[0] is not None and base.role_bindings[1] is not None
        start = replace(
            base.role_bindings[0], observation_id=start_id, evidence_group_id=start_id,
            canonical_position_px=40.0,
            fit_position_interval_px=FiniteInterval.exact(40.0),
            full_position_interval_px=FiniteInterval.exact(40.0),
        )
        shared = replace(
            base.role_bindings[1], observation_id=shared_id, evidence_group_id=shared_id,
            canonical_position_px=140.0,
            fit_position_interval_px=FiniteInterval(139.8, 140.2),
            full_position_interval_px=FiniteInterval(139.0, 141.0),
        )
        fit = replace(
            base,
            phase_lattice_fit=replace(
                base.phase_lattice_fit,
                cycle_phase_interval_px=FiniteInterval.exact(40.0),
                canonical_cycle_phase_px=40.0,
                absolute_phase_interval_px=FiniteInterval.exact(40.0),
                canonical_absolute_phase_px=40.0,
            ),
            pitch_fit=replace(base.pitch_fit, observation_ids=(start_id, shared_id)),
            model_role_positions_px=(40.0, 140.0, 140.0, 240.0),
            model_role_intervals_px=(
                start.fit_position_interval_px, shared.fit_position_interval_px,
                shared.fit_position_interval_px, FiniteInterval.exact(240.0),
            ),
            model_full_role_intervals_px=(
                start.full_position_interval_px, shared.full_position_interval_px,
                shared.full_position_interval_px, FiniteInterval.exact(240.0),
            ),
            role_bindings=(start, shared, shared, None),
            adjacency_relations=(relation,),
        )
        constraints = tuple(
            NominalGridRoleConstraint(
                role_index=index, observation_id=binding.observation_id,
                coordinate_px=binding.canonical_position_px,
                full_interval_px=binding.full_position_interval_px,
            )
            for index, binding in enumerate(fit.role_bindings) if binding is not None
        )
        return fit, relation, constraints

    def test_contact_is_the_exact_w_minus_pitch_grid_relation(self) -> None:
        fit, relation, constraints = self._contact_anchor_fixture()
        template = fit.template
        shared_id = relation.shared_edge_observation_id
        rank = direct_role_constraint_rank(fit)
        self.assertEqual(rank, 2)
        self.assertEqual(direct_role_constraint_rank(fit, (0, 1)), rank)

        envelope, state = solve_calibrated_nominal_grid_envelope(
            prior=calibrated_nominal_grid_prior(template),
            template=template,
            integer_slot_offset=0,
            role_constraints=constraints,
            relations=(relation,),
            phase_authority_px=None,
            retained_direct_constraint_rank=rank,
        )

        self.assertEqual(
            envelope.role_positions_px,
            (40.0, 140.0, 140.0, 240.0),
        )
        self.assertEqual(
            envelope.role_intervals_px[1],
            envelope.role_intervals_px[2],
        )
        self.assertEqual(envelope.role_intervals_px[1], FiniteInterval.exact(140.0))
        self.assertEqual(state.phase_anchor_role_indices, (0, 1, 2))
        self.assertEqual(
            state.phase_anchor_observation_ids,
            (constraints[0].observation_id, shared_id, shared_id),
        )
        self.assertEqual(state.retained_direct_constraint_rank, rank)
        selected = replace(
            fit, calibrated_nominal_grid_fit_state=state,
            lattice_parameter_fit_basis=LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
        )
        self.assertEqual(direct_role_constraint_rank(selected), rank)
        self.assertIs(selected.role_bindings[1], selected.role_bindings[2])
        evidence = CalibratedNominalGridEvidence(
            evidence_id=nominal_grid_evidence_id(state, (), (), ()),
            state=EvidenceState.SUPPORTED,
            prior_id=state.prior_id,
            phase_anchor_role_indices=state.phase_anchor_role_indices,
            phase_anchor_observation_ids=state.phase_anchor_observation_ids,
            inferred_adjacency_ordinals=(), unobserved_frame_ordinals=(),
            covering_query_ids=(), failure_kind=None, reason=None,
        )
        self.assertEqual(evidence.phase_anchor_role_indices, (0, 1, 2))
        self.assertEqual(
            evidence.phase_anchor_observation_ids,
            (constraints[0].observation_id, shared_id, shared_id),
        )
        from tools.regression.report_validation import _validate_nominal_grid_evidence
        from x5crop.report.read_models import typed_read_model

        recorded = typed_read_model(evidence)
        _validate_nominal_grid_evidence(recorded, relations=[typed_read_model(relation)])
        with self.assertRaisesRegex(ValueError, "shared anchor lost its contact"):
            _validate_nominal_grid_evidence(recorded, relations=[])

    def test_duplicate_solver_anchors_require_the_same_proven_contact(self) -> None:
        fit, relation, constraints = self._contact_anchor_fixture()
        other_id = ObservationId("contact:other-edge")
        mismatched = replace(
            relation, physical_edge_id=other_id, shared_edge_observation_id=other_id,
            supporting_observation_ids=(other_id,),
        )
        cases = (
            ("no contact", constraints, ()),
            ("different contact edge", constraints, (mismatched,)),
            ("nonadjacent roles", (*constraints[:2], replace(constraints[2], role_index=3)),
             (relation,)),
            ("different native interval", (*constraints[:2], replace(
                constraints[2], full_interval_px=FiniteInterval(139.5, 140.5),
            )), (relation,)),
            ("different native coordinate", (*constraints[:2], replace(
                constraints[2], coordinate_px=140.1,
            )), (relation,)),
        )
        for label, selected_constraints, relations in cases:
            with self.subTest(case=label), self.assertRaises(ValueError):
                solve_calibrated_nominal_grid_envelope(
                    prior=calibrated_nominal_grid_prior(fit.template),
                    template=fit.template, integer_slot_offset=0,
                    role_constraints=selected_constraints, relations=relations,
                    phase_authority_px=None, retained_direct_constraint_rank=2,
                )

    def test_duplicate_sequence_bindings_keep_one_native_contact_interval(self) -> None:
        fit, relation, _constraints = self._contact_anchor_fixture()
        shared = fit.role_bindings[2]
        assert shared is not None
        other_id = ObservationId("contact:other-edge")
        mismatched = replace(
            relation, physical_edge_id=other_id, shared_edge_observation_id=other_id,
            supporting_observation_ids=(other_id,),
        )
        cases = (
            ("no contact", fit.role_bindings, ()),
            ("different contact edge", fit.role_bindings, (mismatched,)),
            ("nonadjacent roles", (*fit.role_bindings[:2], None, shared), (relation,)),
            ("different native interval", (*fit.role_bindings[:2], replace(
                shared, full_position_interval_px=FiniteInterval(139.5, 140.5),
            ), None), (relation,)),
            ("different native coordinate", (*fit.role_bindings[:2], replace(
                shared, canonical_position_px=140.1,
            ), None), (relation,)),
        )
        for label, bindings, relations in cases:
            with self.subTest(case=label), self.assertRaises(ValueError):
                replace(fit, role_bindings=bindings, adjacency_relations=relations)

    def test_nominal_grid_models_reject_noncontact_role_reuse(self) -> None:
        prior = calibrated_nominal_grid_prior(phase_template(3))
        assert prior.frame_width_mm is not None and prior.pitch_mm is not None
        shared_id = ObservationId("contact:shared-edge")
        state = CalibratedNominalGridFitState(
            prior_id=prior.prior_id, scale_px_per_mm=prior.scale_px_per_mm,
            frame_width_mm=prior.frame_width_mm, pitch_mm=prior.pitch_mm,
            canonical_scale_px_per_mm=1.0,
            phase_anchor_role_indices=(0,), phase_anchor_observation_ids=(shared_id,),
            retained_direct_constraint_rank=1,
        )
        evidence = CalibratedNominalGridEvidence(
            evidence_id="contact:model-evidence", state=EvidenceState.SUPPORTED,
            prior_id=prior.prior_id, phase_anchor_role_indices=(0,),
            phase_anchor_observation_ids=(shared_id,), inferred_adjacency_ordinals=(),
            unobserved_frame_ordinals=(), covering_query_ids=(),
            failure_kind=None, reason=None,
        )
        for roles in ((0, 1), (0, 2), (1, 4), (1, 2, 3)):
            for model in (state, evidence):
                with self.subTest(roles=roles, model=type(model).__name__), self.assertRaises(ValueError):
                    replace(
                        model, phase_anchor_role_indices=roles,
                        phase_anchor_observation_ids=(shared_id,) * len(roles),
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
