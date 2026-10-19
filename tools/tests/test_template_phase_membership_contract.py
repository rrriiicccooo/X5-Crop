from __future__ import annotations

from dataclasses import replace
import json
import unittest

from tools.tests.phase_test_support import _phase_candidate_group
from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    placement_sequence,
    placement_template,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.template_phase_candidate_model import _BoundFit
from x5crop.detection.photo_geometry.template_phase_competition import (
    fit_template_phase,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    assess_direct_role_binding_authority,
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_model import (
    SequenceBindingUse,
    TemplateSearchReceipt,
)
from x5crop.detection.photo_geometry.template_phase_membership import (
    PhaseCompetitionMember,
    build_phase_competition_scope,
    combine_phase_competition_scopes,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
)
from x5crop.detection.photo_geometry.template_phase_observations import _facts
from x5crop.detection.photo_geometry.template_phase_projection import (
    project_candidate_to_authorized_direct_roles,
)
from x5crop.detection.photo_geometry.template_residual import (
    derive_candidate_separator_relations,
)
from x5crop.detection.photo_geometry.template_source_domain import PhaseSourceDomain
from x5crop.domain import Box, EvidenceState, FiniteInterval, ObservationId, WorkspaceExtent


class TemplatePhaseMembershipContractTest(unittest.TestCase):
    def _receipt(
        self,
        *,
        hypotheses: int,
        projection_count: int = 0,
        role_checks: int = 0,
    ) -> TemplateSearchReceipt:
        return TemplateSearchReceipt(
            observation_count=6,
            role_count=6,
            phase_lookup_count=hypotheses,
            role_binding_count=role_checks,
            adjacency_relation_evaluation_count=0,
            local_refinement_lookup_count=0,
            local_refinement_binding_count=0,
            phase_hypothesis_count=hypotheses,
            phase_offset_lookup_count=hypotheses,
            direct_observation_count=6,
            inferred_role_count=0,
            candidate_direct_role_authority_evaluation_count=projection_count,
            candidate_direct_role_authority_role_check_count=role_checks,
            candidate_direct_role_projection_evaluation_count=projection_count,
        )

    def _member(
        self,
        fit,
        ordinal: int,
        *,
        holder_admitted: bool = True,
        projection=None,
        projected_fit=None,
        projected_residual_compatible=None,
        source_terminal_role_indices=(),
    ) -> PhaseCompetitionMember:
        return PhaseCompetitionMember(
            record_ordinal=ordinal,
            input_fit=fit,
            projected_fit=projected_fit,
            projection=projection,
            input_residual_compatible=True,
            projected_residual_compatible=projected_residual_compatible,
            holder_admitted=holder_admitted,
            source_terminal_role_indices=source_terminal_role_indices,
            phase_anchor_ceiling_satisfied=True,
        )

    def _scope(
        self,
        template,
        members,
        receipt,
        *,
        holder_span_px=FiniteInterval(0.0, 500.0),
        source_domain=None,
        projection_evaluated=False,
        bound_exceeded=False,
    ):
        return build_phase_competition_scope(
            template,
            None,
            holder_span_px,
            source_domain,
            (),
            None,
            projection_evaluated,
            bound_exceeded,
            receipt,
            tuple(members),
        )

    def _authority(self, fit, basis):
        facts = tuple(
            DirectRoleAuthorityFact(
                role_index=index,
                lane_ordinal=index // 2 + 1,
                role=(BoundaryRole.START if index % 2 == 0 else BoundaryRole.END),
                observation_id=binding.observation_id,
                evidence_group_id=binding.evidence_group_id,
                independent_support_region_count=3,
                bases=(basis,),
                blocking_material_conflict_ids=(),
                state=EvidenceState.SUPPORTED,
            )
            for index, binding in enumerate(fit.role_bindings)
            if binding is not None
        )
        return DirectRoleBindingAuthority(
            state=EvidenceState.SUPPORTED,
            facts=facts,
            unsupported_role_indices=(),
            reason=None,
        )

    def _unchanged_projection(self, fit, basis):
        return PhaseCandidateAuthorityProjection(
            input_direct_role_authority=self._authority(fit, basis),
            outcome=PhaseCandidateProjectionOutcome.UNCHANGED,
            basis=PhaseCandidateProjectionBasis.DIRECT_BINDINGS,
            projected_out_bindings=(),
            retained_direct_constraint_rank=3,
            reason=None,
        )

    def test_contradicted_projection_keeps_unavailable_input_without_invented_removal(self):
        fit = placement_sequence(placement_template(3))
        authority = self._authority(fit, DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE)
        facts = list(authority.facts)
        facts[0] = replace(facts[0], bases=(), state=EvidenceState.CONTRADICTED,
            blocking_material_conflict_ids=(ObservationId("material:counterevidence"),))
        facts[1] = replace(facts[1], bases=(), state=EvidenceState.UNAVAILABLE)
        authority = DirectRoleBindingAuthority(EvidenceState.CONTRADICTED, tuple(facts), (0, 1),
            "one native role is contradicted and another lacks coordinate authority")
        projected, projection = project_candidate_to_authorized_direct_roles(
            _BoundFit(fit, True), authority, (), (), fit.template.roles, fit.template,
            fit.adjacency_relations, FiniteInterval(fit.template.pitch_px.minimum, fit.template.pitch_px.maximum),
            None, None, None)
        self.assertIsNone(projected)
        self.assertEqual(projection.outcome, PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION)
        self.assertEqual(projection.projected_out_bindings, ())
        member = self._member(fit, 0, projection=projection)
        receipt = replace(self._receipt(hypotheses=1, projection_count=1, role_checks=6),
                          candidate_direct_role_authority_terminal_count=1)
        scope = self._scope(fit.template, (member,), receipt, projection_evaluated=True)
        self.assertEqual(scope.members[0].projection.input_direct_role_authority.facts[1].state,
                         EvidenceState.UNAVAILABLE)

    def test_complete_member_tuple_keeps_third_record_and_rejects_deletion(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        members = tuple(self._member(fit, ordinal) for ordinal in range(3))
        scope = self._scope(template, members, self._receipt(hypotheses=3))
        self.assertEqual(
            tuple(item.record_ordinal for item in scope.members),
            (0, 1, 2),
        )
        self.assertIs(scope.members[2], members[2])
        with self.assertRaises(ValueError):
            replace(scope, members=scope.members[:2])

    def test_raw_unprojected_scope_is_non_empty_and_has_no_output_state(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        member = self._member(fit, 0)
        scope = self._scope(template, (member,), self._receipt(hypotheses=1))
        self.assertFalse(scope.projection_evaluated)
        self.assertEqual(scope.receipt.candidate_direct_role_projection_evaluation_count, 0)
        self.assertEqual(scope.members[0].projection, None)
        self.assertEqual(scope.members[0].projected_fit, None)
        self.assertEqual(scope.members[0].projected_residual_compatible, None)

    def test_real_direct_separator_refit_keeps_relation_and_local_binding(self):
        observations = (
            *_phase_candidate_group("direct-refit", 0.0),
            replace(
                edge("direct-refit:4", 305.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                edge("direct-refit:5", 380.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            ),
        )
        spec = template(3)
        measurements = (
            phase_sequence_measurement("direct-refit", FiniteInterval(0.0, 500.0)),
        )
        result = fit_template_phase(
            observations,
            spec,
            sequence_measurement_sets=measurements,
        )
        self.assertIsNotNone(result.best)
        assert result.best is not None
        original_binding = result.best.role_bindings[0]
        self.assertIsNotNone(original_binding)
        assert original_binding is not None
        local_binding = replace(
            original_binding,
            use=SequenceBindingUse.LOCAL_REFINEMENT,
            observation_id=observations[4].observation_id,
            evidence_group_id=observations[4].observation_id,
            canonical_position_px=305.0,
            fit_position_interval_px=FiniteInterval.exact(305.0),
            full_position_interval_px=FiniteInterval.exact(305.0),
            line_evidence=None,
        )
        input_fit = replace(
            result.best,
            role_bindings=(
                *result.best.role_bindings[:4],
                local_binding,
                result.best.role_bindings[5],
            ),
        )
        separator_band = separator(
            "direct-refit:band",
            observations[1],
            observations[2],
            FiniteInterval.exact(17.8),
        )
        authority = assess_direct_role_binding_authority(
            input_fit,
            observations,
            (separator_band,),
            measurements,
        )
        relations = derive_candidate_separator_relations(
            input_fit,
            authority,
            (separator_band,),
            FiniteInterval.exact(120.0),
        )
        projected, projection = project_candidate_to_authorized_direct_roles(
            _BoundFit(input_fit, True),
            authority,
            _facts(observations),
            (),
            spec.roles,
            spec,
            relations,
            FiniteInterval.exact(120.0),
            None,
            None,
            None,
        )
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT,
        )
        self.assertIsNotNone(projected)
        assert projected is not None
        output_binding = projected.fit.role_bindings[4]
        self.assertIsNotNone(output_binding)
        assert output_binding is not None
        self.assertEqual(output_binding.use, SequenceBindingUse.LOCAL_REFINEMENT)
        self.assertEqual(len(projected.fit.adjacency_relations), 1)

        member = self._member(
            input_fit,
            0,
            projection=projection,
            projected_fit=projected.fit,
            projected_residual_compatible=projected.residual_compatible,
        )
        scope = self._scope(
            spec,
            (member,),
            self._receipt(hypotheses=1, projection_count=1, role_checks=6),
            projection_evaluated=True,
        )
        self.assertIs(scope.members[0].projected_fit, projected.fit)

    def test_source_only_record_is_retained_without_becoming_contradicted(self):
        template = placement_template(3)
        original = placement_sequence(template)
        shifted_positions = tuple(value + 100.0 for value in original.model_role_positions_px)
        shifted_bindings = tuple(
            None
            if binding is None
            else replace(
                binding,
                canonical_position_px=shifted_positions[index],
                fit_position_interval_px=FiniteInterval.exact(shifted_positions[index]),
                full_position_interval_px=FiniteInterval.exact(shifted_positions[index]),
            )
            for index, binding in enumerate(original.role_bindings)
        )
        fit = replace(
            original,
            phase_lattice_fit=replace(
                original.phase_lattice_fit,
                cycle_phase_interval_px=FiniteInterval.exact(80.0),
                canonical_cycle_phase_px=80.0,
                integer_slot_offset=1,
                absolute_phase_interval_px=FiniteInterval.exact(200.0),
                canonical_absolute_phase_px=200.0,
            ),
            model_role_positions_px=shifted_positions,
            model_role_intervals_px=tuple(
                FiniteInterval.exact(value) for value in shifted_positions
            ),
            model_full_role_intervals_px=tuple(
                FiniteInterval.exact(value) for value in shifted_positions
            ),
            role_bindings=shifted_bindings,
        )
        domain = PhaseSourceDomain(
            lane_id="lane:test",
            sampling_authority_box=Box(0, 0, 500, 100),
            source_extent=WorkspaceExtent(500, 100),
            width_axis=BoundaryAxis.X,
        )
        member = self._member(
            fit,
            0,
            holder_admitted=False,
            source_terminal_role_indices=(5,),
        )
        scope = self._scope(
            template,
            (member,),
            self._receipt(hypotheses=1),
            source_domain=domain,
        )
        retained = scope.members[0]
        self.assertFalse(retained.holder_admitted)
        self.assertEqual(retained.source_terminal_role_indices, (5,))
        self.assertTrue(retained.input_residual_compatible)
        self.assertIsNone(retained.projection)

    def test_same_output_fit_with_different_projection_provenance_is_retained(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        first_projection = self._unchanged_projection(
            fit,
            DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        )
        second_projection = self._unchanged_projection(
            fit,
            DirectRoleAuthorityBasis.AGGREGATE_UNION,
        )
        members = (
            self._member(
                fit,
                0,
                projection=first_projection,
                projected_fit=fit,
                projected_residual_compatible=True,
            ),
            self._member(
                fit,
                1,
                projection=second_projection,
                projected_fit=fit,
                projected_residual_compatible=True,
            ),
        )
        scope = self._scope(
            template,
            members,
            self._receipt(hypotheses=2, projection_count=2, role_checks=12),
            projection_evaluated=True,
        )
        self.assertEqual(len(scope.members), 2)
        self.assertEqual(scope.members[0].projected_fit, scope.members[1].projected_fit)
        self.assertNotEqual(scope.members[0].projection, scope.members[1].projection)

    def test_bound_scope_cannot_retain_a_usable_prefix(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        member = self._member(fit, 0)
        with self.assertRaises(ValueError):
            self._scope(
                template,
                (member,),
                self._receipt(hypotheses=1),
                bound_exceeded=True,
            )

    def test_strict_types_and_scope_id_bind_complete_contents(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        with self.assertRaises(TypeError):
            self._member(fit, True)
        with self.assertRaises(TypeError):
            PhaseCompetitionMember(
                0, fit, None, None, 1, None, True, (), True
            )
        scope = self._scope(
            template,
            (self._member(fit, 0),),
            self._receipt(hypotheses=1),
        )
        with self.assertRaises(ValueError):
            replace(scope, scope_id="phase-competition-scope:stale")
        changed_fit = replace(fit, residual_sum_px=1.0)
        changed_member = replace(scope.members[0], input_fit=changed_fit)
        with self.assertRaises(ValueError):
            replace(scope, members=(changed_member,))
        with self.assertRaises(TypeError):
            replace(scope, projection_evaluated=1)
        encoded = json.dumps(
            {
                "scope_id": scope.scope_id,
                "projection_evaluated": scope.projection_evaluated,
                "member_ordinals": [item.record_ordinal for item in scope.members],
            },
            sort_keys=True,
        )
        decoded = json.loads(encoded)
        self.assertEqual(decoded["scope_id"], scope.scope_id)
        rebuilt = build_phase_competition_scope(
            scope.template,
            scope.phase_authority_px,
            scope.holder_span_px,
            scope.source_domain,
            scope.adjacency_relations,
            scope.phase_anchor_authority_ceiling,
            scope.projection_evaluated,
            scope.bound_exceeded,
            scope.receipt,
            scope.members,
        )
        self.assertEqual(rebuilt.scope_id, decoded["scope_id"])

    def test_scope_combine_deduplicates_only_exact_scopes_and_keeps_projection_provenance(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        first = self._unchanged_projection(fit, DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE)
        second = self._unchanged_projection(fit, DirectRoleAuthorityBasis.AGGREGATE_UNION)
        scope_a = self._scope(
            template,
            (
                self._member(
                    fit,
                    0,
                    projection=first,
                    projected_fit=fit,
                    projected_residual_compatible=True,
                ),
            ),
            self._receipt(hypotheses=1, projection_count=1, role_checks=6),
            projection_evaluated=True,
        )
        scope_b = self._scope(
            template,
            (
                self._member(
                    fit,
                    0,
                    projection=second,
                    projected_fit=fit,
                    projected_residual_compatible=True,
                ),
            ),
            self._receipt(hypotheses=1, projection_count=1, role_checks=6),
            projection_evaluated=True,
        )
        combined = combine_phase_competition_scopes(
            (scope_a, scope_a),
            (scope_b, scope_a),
        )
        self.assertEqual(combined, (scope_a, scope_b))
        self.assertIs(combined[0], scope_a)
        self.assertIs(combined[1], scope_b)

    def test_scope_combine_rejects_more_than_six_exact_scopes(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        scopes = tuple(
            self._scope(
                template,
                (self._member(fit, 0),),
                self._receipt(hypotheses=1),
                holder_span_px=FiniteInterval(0.0, 500.0 + index),
            )
            for index in range(7)
        )
        with self.assertRaises(ValueError):
            combine_phase_competition_scopes(scopes[:6], scopes[6:])


if __name__ == "__main__":
    unittest.main()
