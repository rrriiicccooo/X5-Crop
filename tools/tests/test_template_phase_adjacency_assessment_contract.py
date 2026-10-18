from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.test_template_adjacency_topology_contract import _unbound_separator_case
from tools.tests.template_test_support import phase_sequence_measurement, unavailable_nominal_grid_prior
from x5crop.detection.photo_geometry.template_model import TemplateSearchReceipt, LatticeParameterFitBasis
from x5crop.detection.photo_geometry.template_phase import account_prior_phase_fit
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind, PhaseFitResult, PhaseFitStatus, PhaseWinnerBasis, TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_phase_refinement import assess_retained_phase_adjacencies
from x5crop.detection.photo_geometry.template_adjacency_topology import assess_phase_candidate_adjacency
from x5crop.domain import EvidenceState, FiniteInterval
from x5crop.report.read_models import typed_read_model
from tools.regression.report_validation import _read_common_proof


class RetainedAdjacencyAssessmentTests(unittest.TestCase):
    def _case(self, *, resolved=False):
        fit, edges, band, _, _ = _unbound_separator_case()
        inputs = TemplatePhaseInput(
            observations=edges, separator_bands=(band,), template=fit.template,
            scale_px_per_mm=None, holder_span_px=FiniteInterval(0.0, 600.0), phase_authority_px=None,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(fit.template),
            sequence_measurement_sets=(phase_sequence_measurement("native-proof", FiniteInterval(0.0, 600.0)),),
        )
        result = PhaseFitResult(
            template=fit.template, best=fit,
            runner_up=None if resolved else replace(fit, residual_sum_px=2.0),
            status=PhaseFitStatus.RESOLVED if resolved else PhaseFitStatus.AMBIGUOUS,
            ambiguity_reason=None if resolved else "complete competition still has unresolved identities",
            failure_kind=None if resolved else PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS,
            winner_basis=PhaseWinnerBasis.ONLY_PHYSICAL_FIT if resolved else None,
            registered_direct_observation_ids=tuple(edge.observation_id for edge in edges),
            receipt=TemplateSearchReceipt(
                observation_count=len(edges), role_count=len(fit.role_bindings),
                phase_lookup_count=0, role_binding_count=0, adjacency_relation_evaluation_count=0,
                local_refinement_lookup_count=0, local_refinement_binding_count=0,
                phase_hypothesis_count=0, phase_offset_lookup_count=0,
                direct_observation_count=len(edges), inferred_role_count=len(fit.unbound_role_indices),
            ),
        )
        return result, inputs

    def test_final_native_assessment_does_not_promote_a_retained_survivor_or_borrow_w(self):
        original, inputs = self._case()
        foreign_w = SimpleNamespace(state=EvidenceState.SUPPORTED,
            width_px=FiniteInterval.exact(999.0), matches_placement=lambda fit: False)
        with patch("x5crop.detection.photo_geometry.template_phase_refinement.assess_phase_candidate_adjacency",
                   wraps=assess_phase_candidate_adjacency) as assess:
            result = assess_retained_phase_adjacencies(original, inputs, source_frame_width_authority=foreign_w)
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertIs(result.best, original.best)
        self.assertIs(result.runner_up, original.runner_up)
        self.assertIsNone(result.winner_basis)
        self.assertEqual(len(result.retained_adjacency_assessments), 2)
        self.assertTrue(all(item.state == EvidenceState.CONTRADICTED for item in result.retained_adjacency_assessments))
        for call in assess.call_args_list:
            self.assertIsNone(call.kwargs["authorized_source_frame_width_px"])
        with self.assertRaisesRegex(ValueError, "complete fit identities"):
            replace(result, retained_adjacency_assessments=result.retained_adjacency_assessments[:1])

    def test_a_resolved_candidate_with_late_native_counterevidence_loses_qualification(self):
        original, inputs = self._case(resolved=True)
        result = assess_retained_phase_adjacencies(original, inputs, source_frame_width_authority=None)
        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertIsNone(result.winner_basis)
        self.assertIs(result.best, original.best)
        with self.assertRaisesRegex(ValueError, "registered adjacency counterevidence"):
            replace(result, status=PhaseFitStatus.RESOLVED, failure_kind=None,
                    winner_basis=PhaseWinnerBasis.ONLY_PHYSICAL_FIT)

    def test_report_cannot_forge_partner_role_width_or_assessment_state(self):
        original, inputs = self._case()
        result = assess_retained_phase_adjacencies(original, inputs, source_frame_width_authority=None)
        value = typed_read_model(result)
        self.assertEqual(_read_common_proof(value, PhaseFitResult), result)
        changes = (
            ("state", "supported"),
            ("registered_role_associations", []),
        )
        for key, invalid in changes:
            forged = deepcopy(value)
            forged["retained_adjacency_assessments"][0][key] = invalid
            with self.subTest(key=key), self.assertRaises(ValueError):
                _read_common_proof(forged, PhaseFitResult)
        for key, invalid in (("partner_role_index", 0), ("physical_frame_width_upper_px", 1000.0)):
            forged = deepcopy(value)
            forged["retained_adjacency_assessments"][0]["registered_role_associations"][0][key] = invalid
            with self.subTest(key=key), self.assertRaises(ValueError):
                _read_common_proof(forged, PhaseFitResult)

    def test_prior_provenance_keeps_each_final_native_assessment_on_its_own_fit(self):
        prior, inputs = self._case()
        weaker = replace(prior,
            best=replace(prior.best, lattice_parameter_fit_basis=LatticeParameterFitBasis.TEMPLATE_INTERVAL_CENTER),
            runner_up=replace(prior.runner_up, lattice_parameter_fit_basis=LatticeParameterFitBasis.TEMPLATE_INTERVAL_CENTER))
        current = assess_retained_phase_adjacencies(weaker, inputs, source_frame_width_authority=None)
        inherited = account_prior_phase_fit(current, prior)
        self.assertEqual(inherited.best.lattice_parameter_fit_basis, LatticeParameterFitBasis.DIRECT_LEAST_SQUARES)
        for fit, assessment in zip((inherited.best, inherited.runner_up), inherited.retained_adjacency_assessments, strict=True):
            self.assertIs(assessment.fit, fit)
            self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
