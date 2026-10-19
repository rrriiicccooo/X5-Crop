from __future__ import annotations

from dataclasses import replace
from itertools import product
import unittest

from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.template_model import (
    SeparatorRelationKind,
    SeparatorRelation,
    SequenceBindingUse,
    SequenceRoleBinding,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import assess_direct_role_binding_authority
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_refinement import (
    _project_retained_late_local_refinements,
    _refine_selected_roles_with_candidate_elimination,
    _with_local_role_refinement,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase_with_adjacency_relations
from x5crop.detection.photo_geometry.template_lattice_authority import direct_role_constraint_rank
from x5crop.detection.photo_geometry.template_phase_observations import _refine_local_role_bindings
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseWinnerBasis,
    TemplatePhaseInput,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from tools.tests.phase_test_support import _phase_candidate_group


class TemplatePhaseSeparatorRefinementContractTest(unittest.TestCase):
    def test_direct_separator_identity_transmits_prefix_once(
        self,
    ) -> None:
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval.exact(20.0),
            canonical_delta_px=20.0,
            separator_band_observation_id=ObservationId("gap:1"),
            end_edge_observation_id=ObservationId("edge:1"),
            next_start_edge_observation_id=ObservationId("edge:2"),
            signed_gap_interval_px=FiniteInterval.exact(40.0),
            canonical_signed_gap_px=40.0,
        )
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 90.0, 130.0, 230.0, 250.0, 350.0))
        )
        result = fit_template_phase(
            observations,
            template(3),
            adjacency_relations=(relation,),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(result.winner_basis, PhaseWinnerBasis.ONLY_PHYSICAL_FIT)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        phase = result.best.phase_lattice_fit.canonical_absolute_phase_px
        pitch = result.best.pitch_fit.canonical_pitch_px
        self.assertAlmostEqual(
            result.best.model_role_intervals_px[4].center,
            phase + 2.0 * pitch + 20.0,
        )
        self.assertAlmostEqual(
            result.best.model_role_intervals_px[5].center,
            phase + 2.0 * pitch + 120.0,
        )

    def test_direct_separator_authorizes_one_bounded_local_refit(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 253.0, 353.0)
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(
                separator(
                    "separator:wide",
                    observations[3],
                    observations[4],
                    FiniteInterval(22.8, 23.2),
                ),
                ),
                template=template(3),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(3)),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "wide-adjacency-relation",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            )
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        assert result.global_lattice_authority is not None
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 3)
        self.assertTrue(
            all(
                item.state.value == "complete"
                for item in result.adjacency_observation_coverage
                if item.normal_inference_required
            )
        )
        anomalies = tuple(
            relation
            for relation in result.best.adjacency_relations
            if relation.is_anomaly
        )
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].relation_ordinal, 2)
        self.assertAlmostEqual(result.best.model_role_positions_px[4], 253.0)
        self.assertAlmostEqual(result.best.model_role_positions_px[5], 353.0)
        self.assertEqual(
            result.receipt.adjacency_relation_evaluation_count,
            2,
        )
        self.assertEqual(result.receipt.fit_pass_count, 2)

    def test_direct_separator_refit_cannot_add_phase_authority(self) -> None:
        observations = tuple(
            edge(f"fixed-refit:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 253.0, 365.0)
            )
        )
        spec = template(3)
        measurement_sets = (
            phase_sequence_measurement(
                "fixed-separator-refit",
                FiniteInterval(0.0, 400.0),
            ),
        )
        normal = fit_template_phase(
            observations,
            spec,
            sequence_measurement_sets=measurement_sets,
        )
        self.assertEqual(normal.status, PhaseFitStatus.RESOLVED)
        assert normal.best is not None
        fixed = tuple(
            (role_index, binding.observation_id)
            for role_index, binding in enumerate(normal.best.role_bindings)
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        )
        relation = SeparatorRelation(
            relation_ordinal=2,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval.exact(3.0),
            canonical_delta_px=3.0,
            separator_band_observation_id=ObservationId("fixed-refit:band"),
            end_edge_observation_id=observations[3].observation_id,
            next_start_edge_observation_id=observations[4].observation_id,
            signed_gap_interval_px=FiniteInterval.exact(23.0),
            canonical_signed_gap_px=23.0,
        )
        adjusted = fit_template_phase(
            observations,
            spec,
            adjacency_relations=(
                SeparatorRelation(
                    relation_ordinal=1,
                    kind=SeparatorRelationKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                ),
                relation,
            ),
            sequence_measurement_sets=measurement_sets,
            phase_anchor_authority_ceiling=fixed,
        )

        self.assertEqual(adjusted.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(adjusted.competition_scopes[0].phase_anchor_authority_ceiling, fixed)
        assert adjusted.best is not None
        self.assertTrue(
            set(
                (role_index, binding.observation_id)
                for role_index, binding
                in enumerate(adjusted.best.role_bindings)
                if binding is not None
                and binding.use == SequenceBindingUse.PHASE_ANCHOR
            ).issubset(set(fixed)),
        )
        self.assertIsNone(adjusted.best.role_bindings[5])

    def test_direct_narrow_separator_uses_the_same_single_suffix_relation(self) -> None:
        observations = tuple(
            edge(f"edge:narrow:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 127.0, 227.0, 247.0, 347.0)
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(
                    separator(
                        "separator:narrow",
                        observations[1],
                        observations[2],
                        FiniteInterval(16.8, 17.2),
                    ),
                ),
                template=template(3),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(3)),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "narrow-adjacency-relation",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        anomalies = tuple(
            relation
            for relation in result.best.adjacency_relations
            if relation.is_anomaly
        )
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].kind, SeparatorRelationKind.NARROW)
        self.assertEqual(anomalies[0].relation_ordinal, 1)
        self.assertAlmostEqual(result.best.model_role_positions_px[2], 127.0)
        self.assertAlmostEqual(result.best.model_role_positions_px[4], 247.0)

    def test_local_separator_cannot_override_conflicting_edge_roles(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0)
            )
        )
        fit = fit_template_phase(observations, template(2)).best
        assert fit is not None
        bindings = list(fit.role_bindings)
        bindings[1], bindings[2] = bindings[2], bindings[1]
        reversed_fit = replace(fit, role_bindings=tuple(bindings))
        band = separator(
            "separator:direct-role-relation",
            observations[1],
            observations[2],
            FiniteInterval(19.8, 20.2),
            region_count=2,
        )

        authority = assess_direct_role_binding_authority(
            reversed_fit,
            observations,
            (band,),
            (
                phase_sequence_measurement(
                    "reversed-local-separator-pair",
                    FiniteInterval(0.0, 260.0),
                ),
            ),
        )

        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        conflicts = tuple(
            item
            for item in authority.facts
            if item.state == EvidenceState.CONTRADICTED
        )
        self.assertEqual(
            tuple(item.role_index for item in conflicts),
            (1, 2),
        )
        self.assertTrue(
            all(
                item.blocking_material_conflict_ids
                == (band.observation_id,)
                for item in conflicts
            )
        )

    def test_unrelated_two_region_separator_does_not_block_selected_roles(
        self,
    ) -> None:
        selected = _phase_candidate_group("selected", 0.0)
        spec = template(2)
        fit = fit_template_phase(selected, spec).best
        assert fit is not None
        unrelated_left = replace(
            edge("unrelated:separator:left", 500.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
            trace_coordinates_px=(10, 20),
            support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0,
        )
        unrelated_right = replace(
            edge("unrelated:separator:right", 520.0),
            qualified_anchor_roles=(BoundaryRole.START,),
            polarity=1,
            trace_coordinates_px=(10, 20),
            support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0,
        )
        unrelated_band = separator(
            "unrelated:separator",
            unrelated_left,
            unrelated_right,
            FiniteInterval(19.8, 20.2),
            region_count=2,
        )

        authority = assess_direct_role_binding_authority(
            fit,
            (*selected, unrelated_left, unrelated_right),
            (unrelated_band,),
            (
                phase_sequence_measurement(
                    "unrelated-two-region-separator",
                    FiniteInterval(0.0, 560.0),
                ),
            ),
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertTrue(
            all(not item.blocking_material_conflict_ids for item in authority.facts)
        )

    def test_late_reversed_pair_eliminates_winner_and_promotes_legal_runner(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(f"late-reversed:{index}", coordinate),
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                full_direction_interval_degrees=FiniteInterval.exact(0.0),
            )
            for index, coordinate in enumerate(
                (10.0, 120.0, 130.0, 230.0)
            )
        )
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(80.0, 130.0),
        )
        base = fit_template_phase(observations, spec)
        base_fit = base.best
        assert base_fit is not None

        def role_binding(
            observation: BoundaryEdgeObservation,
        ) -> SequenceRoleBinding:
            return SequenceRoleBinding(
                use=SequenceBindingUse.PHASE_ANCHOR,
                observation_id=observation.observation_id,
                evidence_group_id=observation.observation_id,
                canonical_position_px=observation.canonical_position_px,
                fit_position_interval_px=(
                    observation.fit_position_interval_px
                ),
                full_position_interval_px=(
                    observation.full_position_interval_px
                ),
                line_evidence=None,
            )

        normal_fit = replace(
            base_fit,
            model_role_positions_px=tuple(
                item.canonical_position_px for item in observations
            ),
            model_role_intervals_px=tuple(
                item.fit_position_interval_px for item in observations
            ),
            model_full_role_intervals_px=tuple(
                item.full_position_interval_px for item in observations
            ),
            role_bindings=tuple(role_binding(item) for item in observations),
            phase_support_coverage=0.0,
        )
        wrong_bindings = list(normal_fit.role_bindings)
        wrong_bindings[1] = role_binding(observations[2])
        wrong_bindings[2] = None
        wrong_fit = replace(
            normal_fit,
            role_bindings=tuple(wrong_bindings),
            phase_support_coverage=0.0,
        )
        band = separator(
            "late-reversed:separator",
            observations[1],
            observations[2],
            FiniteInterval(9.8, 10.2),
            region_count=2,
        )
        measurement_sets = (
            phase_sequence_measurement(
                "late-reversed-candidate-elimination",
                FiniteInterval(0.0, 260.0),
            ),
        )
        wrong_authority = assess_direct_role_binding_authority(
            wrong_fit,
            observations,
            (band,),
            measurement_sets,
        )
        runner_authority = assess_direct_role_binding_authority(
            normal_fit,
            observations,
            (band,),
            measurement_sets,
        )
        self.assertEqual(wrong_authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(runner_authority.state, EvidenceState.SUPPORTED)
        refined_wrong = _refine_local_role_bindings(
            wrong_fit,
            observations,
            (band,),
            intrinsic_coordinate_authority_ids=frozenset(
                item.observation_id for item in observations
            ),
        ).fit
        self.assertEqual(
            refined_wrong.binding_observation_ids[2],
            observations[1].observation_id,
        )

        def eligible_projection(fit, authority):
            return PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=PhaseCandidateProjectionOutcome.UNCHANGED,
                basis=PhaseCandidateProjectionBasis.DIRECT_BINDINGS,
                projected_out_bindings=(),
                retained_direct_constraint_rank=direct_role_constraint_rank(
                    fit,
                    authority.supported_role_indices,
                ),
                reason=None,
            )

        competition = replace(
            base,
            best=wrong_fit,
            runner_up=normal_fit,
            status=PhaseFitStatus.RESOLVED,
            ambiguity_reason=None,
            failure_kind=None,
            winner_basis=PhaseWinnerBasis.INDEPENDENT_SUPPORT,
            best_phase_candidate_authority_projection=(
                eligible_projection(wrong_fit, wrong_authority)
            ),
            runner_phase_candidate_authority_projection=(
                eligible_projection(normal_fit, runner_authority)
            ),
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(band,),
            template=spec,
            calibrated_nominal_grid_prior=(
                unavailable_nominal_grid_prior(spec)
            ),
            scale_px_per_mm=None,
            holder_span_px=FiniteInterval(0.0, 260.0),
            phase_authority_px=None,
            sequence_measurement_sets=measurement_sets,
        )

        result = _refine_selected_roles_with_candidate_elimination(
            competition,
            phase_input,
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.binding_observation_ids[1:3],
            (
                observations[1].observation_id,
                observations[2].observation_id,
            ),
        )
        self.assertEqual(
            result.winner_basis,
            PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY,
        )
        self.assertEqual(
            len(result.eliminated_candidate_authority_projections),
            1,
        )
        eliminated = result.eliminated_candidate_authority_projections[0]
        self.assertEqual(
            eliminated.outcome,
            PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
        )
        self.assertEqual(
            tuple(
                item.role_index
                for item in eliminated.input_direct_role_authority.facts
                if item.state == EvidenceState.CONTRADICTED
            ),
            (1, 2),
        )

        # The same hard counterevidence belongs to its candidate even when
        # initial identity ambiguity forbids promotion or reordering.
        for failure_kind, reversed_primary in product(
            (PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
             PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS), (True, False),
        ):
            with self.subTest(failure_kind=failure_kind, reversed_primary=reversed_primary):
                ambiguous = replace(
                    competition,
                    best=wrong_fit if reversed_primary else normal_fit,
                    runner_up=normal_fit if reversed_primary else wrong_fit,
                    best_phase_candidate_authority_projection=(
                        eligible_projection(wrong_fit, wrong_authority)
                        if reversed_primary
                        else eligible_projection(normal_fit, runner_authority)
                    ),
                    runner_phase_candidate_authority_projection=(
                        eligible_projection(normal_fit, runner_authority)
                        if reversed_primary
                        else eligible_projection(wrong_fit, wrong_authority)
                    ),
                    status=PhaseFitStatus.AMBIGUOUS,
                    failure_kind=failure_kind,
                    ambiguity_reason="two retained identities",
                    winner_basis=None,
                )
                refined = _with_local_role_refinement(
                    ambiguous, observations, (band,), measurement_sets,
                )
                projected = _project_retained_late_local_refinements(
                    refined, phase_input, allow_direct_rank=True,
                )
                self.assertEqual(projected.status, ambiguous.status)
                self.assertEqual(projected.failure_kind, ambiguous.failure_kind)
                self.assertEqual(projected.ambiguity_reason, ambiguous.ambiguity_reason)
                self.assertIsNone(projected.winner_basis)
                self.assertEqual(projected.best, refined.best)
                self.assertEqual(projected.runner_up, refined.runner_up)
                failed = (
                    projected.best_phase_candidate_authority_projection
                    if reversed_primary
                    else projected.runner_phase_candidate_authority_projection
                )
                assert failed is not None
                self.assertEqual(
                    failed.outcome,
                    PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
                )
                self.assertFalse(failed.eligible)
                self.assertEqual(
                    failed.input_direct_role_authority.state,
                    EvidenceState.CONTRADICTED,
                )
                self.assertEqual(
                    projected.receipt.selected_direct_role_projection_evaluation_count,
                    1,
                )
                projected.receipt.validate_bounds()


if __name__ == "__main__":
    unittest.main()
