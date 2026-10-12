from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.detection.photo_geometry import (
    template_phase_candidate_model as candidate_model,
    template_phase_fitting as phase_fitting,
    template_phase_projection as phase_projection,
)
from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_edge as edge,
    phase_sequence_measurement,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_model import (
    LatticeParameterFitBasis,
    SequenceBindingUse,
    SequenceRoleBinding,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import assess_direct_role_binding_authority
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_refinement import (
    _project_retained_late_local_refinements,
    _with_local_role_refinement,
)
from x5crop.detection.photo_geometry.template_phase import (
    account_prior_phase_fit,
    fit_template_phase_candidate_with_adjacency_relations,
    fit_template_phase_with_adjacency_relations,
)
from x5crop.detection.photo_geometry.template_phase_fitting import _bounded_lattice_least_squares
from x5crop.detection.photo_geometry.template_phase_observations import _facts
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectedBinding,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_placement import (
    retained_cross_support_domain_groups_px,
    resolved_cross_support_domains_px,
)
from x5crop.domain import EvidenceState, FiniteInterval, PositiveInterval
from tools.tests.phase_test_support import _local_line, _phase_candidate_group


class TemplatePhaseRefinementContractTest(unittest.TestCase):
    def test_discrete_candidates_refine_their_own_local_roles_without_a_winner(
        self,
    ) -> None:
        observations = tuple(
            replace(
                _local_line(f"{offset}:{index}", coordinate + offset, role),
                fit_residual_px=0.0 if index == 0 else 20.0,
            )
            for offset in (0, 10)
            for index, (coordinate, role) in enumerate(
                (
                    (100.0, BoundaryRole.START),
                    (201.0, BoundaryRole.END),
                    (221.0, BoundaryRole.START),
                    (321.0, BoundaryRole.END),
                )
            )
        )
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(98.0, 102.0),
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=spec,
            calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(spec),
            scale_px_per_mm=PositiveInterval.exact(100.0),
            holder_span_px=FiniteInterval(90.0, 350.0),
            phase_authority_px=None,
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "two-local-candidates",
                    FiniteInterval(90.0, 350.0),
                ),
            ),
        )
        before = fit_template_phase(
            observations,
            spec,
            scale_px_per_mm=phase_input.scale_px_per_mm,
            holder_span_px=phase_input.holder_span_px,
            sequence_measurement_sets=phase_input.sequence_measurement_sets,
            calibrated_nominal_grid_prior=phase_input.calibrated_nominal_grid_prior,
        )
        result = fit_template_phase_candidate_with_adjacency_relations(
            phase_input
        ).result

        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(result.failure_kind, PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS)
        self.assertIsNone(result.winner_basis)
        domain_groups = retained_cross_support_domain_groups_px(result)
        self.assertEqual(len(domain_groups), 2)
        self.assertEqual(
            domain_groups,
            tuple(
                resolved_cross_support_domains_px(fit)
                for fit in (result.best, result.runner_up)
            ),
        )
        self.assertNotEqual(domain_groups[0], domain_groups[1])
        with patch(
            "x5crop.detection.photo_geometry.template_placement."
            "resolved_cross_support_domains_px",
            side_effect=(domain_groups[0], ValueError("unmodeled overlap")),
        ):
            with self.assertRaisesRegex(ValueError, "unmodeled overlap"):
                retained_cross_support_domain_groups_px(result)
        for original, refined in zip(
            (before.best, before.runner_up),
            (result.best, result.runner_up),
            strict=True,
        ):
            assert original is not None and refined is not None
            self.assertEqual(refined.phase_lattice_fit, original.phase_lattice_fit)
            self.assertEqual(refined.pitch_fit, original.pitch_fit)
            self.assertEqual(refined.model_role_positions_px, original.model_role_positions_px)
            self.assertEqual(refined.role_bindings[0], original.role_bindings[0])
            added = refined.role_bindings[1]
            assert added is not None
            self.assertEqual(added.use, SequenceBindingUse.LOCAL_REFINEMENT)
            self.assertAlmostEqual(
                added.canonical_position_px,
                original.model_role_positions_px[1] + 1.0,
            )
            self.assertIsNone(refined.role_bindings[2])
            self.assertIsNone(refined.role_bindings[3])
        self.assertEqual(result.receipt.local_refinement_lookup_count, 64)
        self.assertEqual(result.receipt.local_refinement_binding_count, 2)
        self.assertEqual(
            result.receipt.phase_hypothesis_count,
            before.receipt.phase_hypothesis_count,
        )
        self.assertEqual(
            result.receipt.fit_pass_count, before.receipt.fit_pass_count + 1,
        )
        result.receipt.validate_bounds()
        with self.assertRaisesRegex(ValueError, "cannot share selected source W"):
            _with_local_role_refinement(
                before,
                observations,
                (),
                phase_input.sequence_measurement_sets,
                frame_width_authority_px=FiniteInterval(99.0, 101.0),
            )
        unavailable = replace(
            before,
            status=PhaseFitStatus.UNRESOLVED,
            failure_kind=PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE,
            ambiguity_reason="direct-role authority is unavailable",
        )
        self.assertEqual(retained_cross_support_domain_groups_px(unavailable), ())
        self.assertIs(
            _with_local_role_refinement(
                unavailable, observations, (), phase_input.sequence_measurement_sets,
            ),
            unavailable,
        )

        weak_observations = tuple(
            replace(
                item,
                trace_coordinates_px=(10, 20),
                support_fraction=2.0 / 3.0,
                continuous_support_fraction=2.0 / 3.0,
            )
            if str(item.observation_id).endswith(":1")
            else item
            for item in observations
        )
        weak_result = fit_template_phase_candidate_with_adjacency_relations(
            replace(phase_input, observations=weak_observations)
        ).result
        self.assertEqual(weak_result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(weak_result.failure_kind, result.failure_kind)
        self.assertIsNone(weak_result.winner_basis)
        for fit, projection in (
            (weak_result.best, weak_result.best_phase_candidate_authority_projection),
            (weak_result.runner_up, weak_result.runner_phase_candidate_authority_projection),
        ):
            assert fit is not None and projection is not None
            self.assertIsNone(fit.role_bindings[1])
            self.assertEqual(
                projection.outcome,
                PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
            )
            self.assertEqual(
                projection.input_direct_role_authority.state,
                EvidenceState.UNAVAILABLE,
            )
            self.assertEqual(
                tuple(item.role_index for item in projection.projected_out_bindings),
                (1,),
            )
            self.assertEqual(
                str(projection.projected_out_bindings[0].observation_id).split(":")[0],
                str(fit.role_bindings[0].observation_id).split(":")[0],
            )
        self.assertEqual(weak_result.receipt.selected_direct_role_projection_evaluation_count, 2)
        self.assertEqual(weak_result.receipt.selected_direct_role_projection_binding_count, 2)
        self.assertEqual(weak_result.receipt.selected_nominal_grid_solve_success_count, 2)
        weak_result.receipt.validate_bounds()

    def test_late_incompatible_refit_retains_input_and_failed_projection(self) -> None:
        spec = template(3)
        observations = (*_phase_candidate_group("late-residual", 0.0),
            replace(edge("late-residual:last-start", 280.0),
                qualified_anchor_roles=(BoundaryRole.START,), polarity=1))
        weak = replace(edge("late-residual:weak-end", 381.0),
            qualified_anchor_roles=(BoundaryRole.END,), polarity=-1,
            trace_coordinates_px=(10, 20), support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0, fit_residual_px=20.0)
        registered = (*observations, weak)
        measurement = (phase_sequence_measurement(
            "late-residual-measurement", FiniteInterval(0.0, 480.0)),)
        raw = fit_template_phase(registered, spec,
            scale_px_per_mm=PositiveInterval.exact(100.0),
            holder_span_px=FiniteInterval(0.0, 400.0))
        assert raw.best is not None
        weak_fact = _facts((weak,))[0]
        binding = SequenceRoleBinding(
            use=SequenceBindingUse.LOCAL_REFINEMENT,
            observation_id=weak.observation_id, evidence_group_id=weak.observation_id,
            canonical_position_px=weak.canonical_position_px,
            fit_position_interval_px=weak.fit_position_interval_px,
            full_position_interval_px=weak.full_position_interval_px,
            line_evidence=weak_fact.line_evidence,
        )
        refined = replace(raw, best=replace(raw.best,
            role_bindings=(*raw.best.role_bindings[:5], binding),
            model_role_intervals_px=(*raw.best.model_role_intervals_px[:5],
                FiniteInterval(379.0, 382.0)),
            model_full_role_intervals_px=(*raw.best.model_full_role_intervals_px[:5],
                FiniteInterval(379.0, 382.0)),
        ))
        self.assertEqual(refined.best.role_bindings[5].use, SequenceBindingUse.LOCAL_REFINEMENT)
        authority = assess_direct_role_binding_authority(refined.best, registered, (), measurement)
        self.assertEqual(authority.unsupported_role_indices, (5,))
        # A real bounded solve keeps every native phase anchor while its mean
        # residual exceeds 1.5% W, below the 3.5% individual trim threshold.
        facts = _facts(observations)
        refit = phase_fitting._fit_seed(
            candidate_model._PhaseSeed(43.0, 120.0,
                tuple((index, binding.observation_id)
                    for index, binding in enumerate(refined.best.role_bindings)
                    if binding is not None and binding.use == SequenceBindingUse.PHASE_ANCHOR)),
            facts, (), spec.roles, spec, (), FiniteInterval.exact(120.0),
            FiniteInterval.exact(43.0), None,
        )
        assert refit is not None
        self.assertFalse(refit.residual_compatible)
        projection = PhaseCandidateAuthorityProjection(
            authority, PhaseCandidateProjectionOutcome.PROJECTED,
            PhaseCandidateProjectionBasis.DIRECT_RANK_THREE,
            (PhaseCandidateProjectedBinding(5, weak.observation_id),), 3, None,
        )
        phase_input = TemplatePhaseInput(
            observations=registered, separator_bands=(), template=spec,
            scale_px_per_mm=None, holder_span_px=None, phase_authority_px=None,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(spec),
            sequence_measurement_sets=measurement,
        )
        with patch.object(phase_projection, "project_candidate_to_authorized_direct_roles",
            return_value=(refit, projection)):
            result = _project_retained_late_local_refinements(
                refined, phase_input, allow_direct_rank=True)
        self.assertEqual(result.best, refined.best)
        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(result.failure_kind, PhaseFailureKind.FIXED_TEMPLATE_MISMATCH)
        self.assertIsNone(result.winner_basis)
        failed = result.best_phase_candidate_authority_projection
        assert failed is not None
        self.assertFalse(failed.eligible)
        self.assertEqual(failed.outcome, PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE)
        self.assertEqual(failed.projected_out_bindings, projection.projected_out_bindings)

    def test_rank_three_fit_uses_nearest_joint_physical_solution(self) -> None:
        matrix = np.asarray(
            [
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
                (1.0, 0.0, 2.0),
                (1.0, 1.0, 2.0),
            ],
            dtype=np.float64,
        )
        values = np.asarray(
            (10.0, 108.0, 131.0, 229.0, 252.0, 350.0),
            dtype=np.float64,
        )

        phase, width, pitch, basis = _bounded_lattice_least_squares(
            matrix,
            values,
            width_authority=PositiveInterval(95.0, 105.0),
            pitch_authority=FiniteInterval(115.0, 125.0),
            gap_authority=FiniteInterval(18.0, 22.0),
            phase_authority=None,
        )

        self.assertAlmostEqual(pitch - width, 22.0)
        self.assertEqual(
            basis,
            LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES,
        )
        self.assertNotEqual((width, pitch), (100.0, 120.0))
        bounded_residual = np.sum(
            (matrix @ np.asarray((phase, width, pitch)) - values) ** 2
        )
        nominal_phase = float(
            np.mean(values - matrix @ np.asarray((0.0, 100.0, 120.0)))
        )
        nominal_residual = np.sum(
            (
                matrix @ np.asarray((nominal_phase, 100.0, 120.0))
                - values
            )
            ** 2
        )
        self.assertLess(bounded_residual, nominal_residual)

    def test_rank_three_fit_never_widens_compiled_authorities(self) -> None:
        matrix = np.asarray(
            [
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 2.0),
            ],
            dtype=np.float64,
        )
        values = np.asarray((0.0, 70.0, 150.0, 390.0), dtype=np.float64)

        phase, width, pitch, basis = _bounded_lattice_least_squares(
            matrix,
            values,
            width_authority=PositiveInterval(95.0, 105.0),
            pitch_authority=FiniteInterval(115.0, 125.0),
            gap_authority=FiniteInterval(18.0, 22.0),
            phase_authority=FiniteInterval(-2.0, 2.0),
        )

        self.assertTrue(FiniteInterval(-2.0, 2.0).contains(phase))
        self.assertTrue(FiniteInterval(95.0, 105.0).contains(width))
        self.assertTrue(FiniteInterval(115.0, 125.0).contains(pitch))
        self.assertTrue(FiniteInterval(18.0, 22.0).contains(pitch - width))
        self.assertEqual(
            basis,
            LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES,
        )

    def test_parameter_basis_follows_only_the_same_discrete_lineage(self) -> None:
        coordinates = (10.0, 110.0, 130.0, 230.0)
        observations = tuple(
            edge(f"lineage:{index}", coordinate)
            for index, coordinate in enumerate(coordinates)
        )
        current = fit_template_phase(observations, template(2))
        assert current.best is not None
        prior = replace(
            current,
            best=replace(
                current.best,
                lattice_parameter_fit_basis=(
                    LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES
                ),
            ),
        )

        inherited = account_prior_phase_fit(current, prior)

        assert inherited.best is not None
        self.assertEqual(
            inherited.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES,
        )
        unrelated = fit_template_phase(
            tuple(
                edge(f"other:{index}", coordinate)
                for index, coordinate in enumerate(coordinates)
            ),
            template(2),
        )
        retained = account_prior_phase_fit(unrelated, prior)
        assert retained.best is not None
        self.assertEqual(
            retained.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.DIRECT_LEAST_SQUARES,
        )

    def test_prior_direct_pass_cannot_relabel_a_calibrated_grid_solve(
        self,
    ) -> None:
        spec = template(4)
        observations = tuple(
            replace(
                edge(f"nominal-lineage:{slot}", 40.0 + 120.0 * slot),
                qualified_anchor_roles=(BoundaryRole.START,),
            )
            for slot in range(4)
        )
        nominal = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                    spec
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 520.0),
                phase_authority_px=FiniteInterval.exact(40.0),
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "nominal-lineage-complete",
                        FiniteInterval(0.0, 520.0),
                    ),
                ),
            )
        )
        direct_prior = fit_template_phase(
            observations,
            spec,
            phase_authority_px=FiniteInterval.exact(40.0),
        )

        retained = account_prior_phase_fit(nominal, direct_prior)

        assert retained.best is not None
        self.assertEqual(
            retained.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
        )
        self.assertIsNotNone(
            retained.best.calibrated_nominal_grid_fit_state
        )
        self.assertIsNotNone(retained.calibrated_nominal_grid_evidence)

    def test_terminal_refit_closes_new_outliers_without_rematching(self) -> None:
        compiled = template(6)
        observations = tuple(
            edge(f"cascade:{index}", 10.0 + 120.0 * index + departure)
            for index, departure in enumerate((0.0, 0.0, 0.0, 3.0, 6.0, 7.0))
        )
        facts = _facts(observations)
        matches = tuple(
            (compiled.roles[2 * index], fact)
            for index, fact in enumerate(facts)
        )
        seed = candidate_model._PhaseSeed(
            10.0, 120.0, ((0, observations[0].observation_id),),
        )
        arguments = (
            seed, facts, (), compiled.roles, compiled, (),
            FiniteInterval.exact(120.0), None, None,
        )
        with patch.object(phase_fitting, "_match_roles", return_value=matches), patch.object(
            phase_fitting, "_linear_fit", wraps=phase_fitting._linear_fit,
        ) as linear:
            result = phase_fitting._fit_seed(*arguments)
        self.assertEqual(linear.call_count, 4)
        assert result is not None
        self.assertTrue(result.residual_compatible)
        self.assertEqual(
            tuple(identity for identity in result.fit.binding_observation_ids if identity is not None),
            tuple(item.observation_id for item in observations[:4]),
        )
        self.assertEqual(
            tuple(binding.canonical_position_px for binding in result.fit.role_bindings if binding),
            tuple(item.canonical_position_px for item in observations[:4]),
        )
        with patch.object(phase_fitting, "_match_roles", return_value=matches[:4]):
            independent = phase_fitting._fit_seed(*arguments)
        assert independent is not None
        self.assertEqual(result, independent)

        # The same observed row also defines its own independent seed. Its
        # identity must survive a fit dominated by incompatible optional rows.
        required = replace(seed, required_bindings=((8, observations[4].observation_id),))
        with patch.object(phase_fitting, "_match_roles", return_value=matches), patch.object(
            phase_fitting, "_linear_fit", wraps=phase_fitting._linear_fit,
        ) as linear:
            restored = phase_fitting._fit_seed(required, *arguments[1:])
        assert restored is not None
        self.assertEqual(linear.call_count, 5)
        self.assertEqual(
            tuple(identity for identity in restored.fit.binding_observation_ids
                  if identity is not None),
            tuple(item.observation_id for item in observations[3:5]),
        )
        self.assertEqual(restored.fit.role_bindings[8].canonical_position_px, 496.0)
        self.assertTrue(restored.residual_compatible)
        # A hard phase authority still makes that defining row infeasible.
        # The independent check cannot move the authority or erase the row.
        with patch.object(phase_fitting, "_match_roles", return_value=matches):
            rejected = phase_fitting._fit_seed(
                required, *arguments[1:7], FiniteInterval.exact(10.0), None,
            )
        self.assertIsNone(rejected)

    def test_terminal_refit_rejects_an_empty_retained_set(self) -> None:
        compiled = template(1)
        facts = _facts((edge("empty-trim", 10.0),))
        with patch.object(
            phase_fitting, "_match_roles", return_value=((compiled.roles[0], facts[0]),),
        ):
            result = phase_fitting._fit_seed(
                candidate_model._PhaseSeed(0.0, 120.0), facts, (), compiled.roles,
                compiled, (), FiniteInterval.exact(120.0), FiniteInterval.exact(0.0), None,
            )
        self.assertIsNone(result)

    def test_terminal_refit_closes_after_all_matching_passes(self) -> None:
        compiled = template(6)
        observations = tuple(
            edge(f"bounded-cascade:{index}", 10.0 + 120.0 * index + departure)
            for index, departure in enumerate((0.0, 0.0, 0.0, 3.0, 6.0, 7.0))
        )
        facts = _facts(observations)
        matches = tuple((compiled.roles[2 * index], fact) for index, fact in enumerate(facts))
        reversed_matches = tuple(reversed(matches))
        with patch.object(
            phase_fitting, "_match_roles", side_effect=(matches, reversed_matches, matches, reversed_matches),
        ), patch.object(phase_fitting, "_linear_fit", wraps=phase_fitting._linear_fit) as linear:
            result = phase_fitting._fit_seed(
                candidate_model._PhaseSeed(10.0, 120.0), facts, (), compiled.roles,
                compiled, (), FiniteInterval.exact(120.0), None, None,
            )
        self.assertEqual(linear.call_count, 6)
        self.assertLessEqual(linear.call_count, len(matches) + 3)
        assert result is not None
        self.assertTrue(result.residual_compatible)
        self.assertEqual(
            tuple(identity for identity in result.fit.binding_observation_ids if identity is not None),
            tuple(item.observation_id for item in observations[:4]),
        )


if __name__ == "__main__":
    unittest.main()
