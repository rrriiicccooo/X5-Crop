from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior, unavailable_nominal_grid_prior,
    phase_edge, phase_sequence_measurement, phase_template, placement_sequence,
)
from tools.tests.test_native_grid_association_contract import _phase
from tools.tests import test_phase_member_adjacency_propagation_contract as adjacency_fixture
from x5crop.detection.photo_geometry.template_phase_model import TemplatePhaseInput, PhaseFitStatus, PhaseWinnerBasis
from x5crop.detection.photo_geometry.template_phase_projection import (
    CandidateProjectionWork, CandidateProjectionWorkBoundError,
)
from x5crop.detection.photo_geometry.template_phase_refinement import _project_late_local_candidate
from x5crop.detection.photo_geometry import template_phase_refinement as refinement
from x5crop.detection.photo_geometry import template_phase_output as member_output
from x5crop.detection.photo_geometry.template_direct_role_authority import assess_direct_role_binding_authority
from x5crop.detection.photo_geometry.template_model import SequenceBindingUse
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId


def _fixture():
    template = phase_template(3)
    fit = placement_sequence(template, missing=(2, 3))
    observations = tuple(phase_edge(b.observation_id, b.canonical_position_px)
                         for b in fit.role_bindings if b is not None)
    inputs = TemplatePhaseInput(observations, (), template, None,
        FiniteInterval(0.0, 500.0), FiniteInterval.exact(100.0),
        calibrated_nominal_grid_prior(template), sequence_measurement_sets=(
            phase_sequence_measurement('late-nominal-state', FiniteInterval(0.0, 500.0)),))
    return fit, inputs


class MissingNominalStateContractTest(unittest.TestCase):
    def test_supported_native_roles_still_compile_their_missing_nominal_state(self):
        fit, inputs = _fixture()
        authority = assess_direct_role_binding_authority(fit, inputs.observations,
            inputs.separator_bands, inputs.sequence_measurement_sets)
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertIsNone(fit.calibrated_nominal_grid_fit_state)
        work = CandidateProjectionWork()
        projected, proof = _project_late_local_candidate(fit, inputs,
            allow_direct_rank=True, projection_work=work)
        self.assertIsNotNone(projected)
        self.assertIsNotNone(projected.calibrated_nominal_grid_fit_state)
        self.assertEqual(projected.role_bindings, fit.role_bindings)
        self.assertEqual(projected.template, fit.template)
        self.assertEqual(projected.phase_lattice_fit.integer_slot_offset,
                         fit.phase_lattice_fit.integer_slot_offset)
        self.assertTrue(proof.eligible)
        self.assertEqual(work.nominal_grid_solve_count, 1)
        self.assertEqual(work.nominal_grid_solve_success_count, 1)
        self.assertGreater(work.projection_work_bound, 0)
        self.assertIsNone(fit.calibrated_nominal_grid_fit_state)

    def test_missing_prior_and_missing_measurements_do_not_create_grid_authority(self):
        fit, inputs = _fixture()
        for changed in (replace(inputs, calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(fit.template)),
                        replace(inputs, sequence_measurement_sets=())):
            work = CandidateProjectionWork()
            actual, proof = _project_late_local_candidate(fit, changed,
                allow_direct_rank=True, projection_work=work)
            self.assertIs(actual, fit)
            self.assertIsNone(proof)
            self.assertEqual(work, CandidateProjectionWork())

    def test_existing_nominal_state_is_not_solved_again(self):
        fit, inputs = _fixture()
        projected, _ = _project_late_local_candidate(fit, inputs, allow_direct_rank=True)
        work = CandidateProjectionWork()
        actual, proof = _project_late_local_candidate(projected, inputs,
            allow_direct_rank=True, projection_work=work)
        self.assertIs(actual, projected)
        self.assertIsNone(proof)
        self.assertEqual(work, CandidateProjectionWork())

    def test_missing_state_cannot_remove_an_unsupported_phase_anchor(self):
        fit, inputs = _fixture()
        observations = tuple(replace(o, trace_coordinates_px=(0, 10),
                                      support_fraction=0.5, continuous_support_fraction=0.5)
                             if o.observation_id == fit.role_bindings[0].observation_id else o
                             for o in inputs.observations)
        changed = replace(inputs, observations=observations)
        authority = assess_direct_role_binding_authority(fit, observations, (), inputs.sequence_measurement_sets)
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(fit.role_bindings[0].use, SequenceBindingUse.PHASE_ANCHOR)
        work = CandidateProjectionWork()
        actual, proof = _project_late_local_candidate(fit, changed,
            allow_direct_rank=True, projection_work=work)
        self.assertIs(actual, fit)
        self.assertIsNone(proof)
        self.assertEqual(work, CandidateProjectionWork())

    def test_work_limit_stops_before_projection_preparation_and_solver(self):
        fit, inputs = _fixture()
        work = CandidateProjectionWork()
        with patch('x5crop.detection.photo_geometry.template_phase_refinement._projection.project_candidate_to_authorized_direct_roles') as solver:
            with self.assertRaises(CandidateProjectionWorkBoundError):
                _project_late_local_candidate(fit, inputs, allow_direct_rank=True,
                    projection_work=work, available_projection_work_units=0)
        solver.assert_not_called()
        self.assertEqual(work, CandidateProjectionWork())

    def test_identity_rejection_still_counts_the_successful_grid_solve(self):
        fit, inputs = _fixture()
        phase = _phase(fit, direct_roles=(0, 1, 4, 5))
        phase = replace(phase, status=PhaseFitStatus.RESOLVED, ambiguity_reason=None,
                        failure_kind=None, winner_basis=PhaseWinnerBasis.ONLY_PHYSICAL_FIT)
        real = refinement._projection.project_candidate_to_authorized_direct_roles

        def changed_identity(*args, **kwargs):
            projected, proof = real(*args, **kwargs)
            self.assertIsNotNone(projected)
            bindings = list(projected.fit.role_bindings)
            bindings[0] = replace(bindings[0], evidence_group_id=ObservationId('changed-group'))
            return replace(projected, fit=replace(projected.fit, role_bindings=tuple(bindings))), proof

        with patch.object(refinement._projection, 'project_candidate_to_authorized_direct_roles', changed_identity):
            result = refinement._project_retained_late_local_refinements(phase, inputs, allow_direct_rank=True)
        self.assertEqual(result.best, fit)
        self.assertFalse(result.best_phase_candidate_authority_projection.eligible)
        self.assertEqual(result.receipt.selected_nominal_grid_solve_count, 1)
        self.assertEqual(result.receipt.selected_nominal_grid_solve_success_count, 1)

    def test_member_reserves_prerequisites_before_a_late_grid_solve(self):
        fit, inputs = _fixture()
        lane, scope, member = adjacency_fixture.PhaseMemberAdjacencyPropagationContractTest._assess_lane(fit, inputs)
        for quota in (0, 35, 36, 60, 69, 70, 100, 504, 505, 549, 550, 600, 10000):
            with self.subTest(quota=quota), patch.object(member_output, 'prepare_template_cross_context',
                    side_effect=ValueError('bounded Cross test stop')):
                proof = member_output.assess_phase_member_output(lane, scope, member,
                    available_work_units=quota)
                self.assertLessEqual(member_output._member_work_units(proof.work, 6), quota)
                if quota == 505:
                    self.assertIn(member_output.PhaseMemberOutputGap.WORK_BOUND_EXCEEDED, proof.gaps)
                    self.assertEqual(proof.work.late_nominal_grid_solve_count, 0)


if __name__ == '__main__':
    unittest.main()
