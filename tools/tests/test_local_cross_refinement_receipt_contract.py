from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests import test_template_registration_contract as fixtures
from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.detection.photo_geometry import template_registration as owner


class LocalCrossRefinementReceiptContractTest(unittest.TestCase):
    def evaluate(self, coordinates=((100.0,),) * 6, *, rejected=True, observations=()):
        helper = fixtures.TemplateRegistrationContractTest()
        measurement = helper._bottom_measurement(coordinates)
        if rejected:
            measurement = replace(measurement, transitions=tuple(replace(
                item, left_texture_mean=1.0, right_texture_mean=1.0,
            ) for item in measurement.transitions))
        return owner.evaluate_local_cross_refinement(helper._top_anchor(), measurement,
            width_axis=BoundaryAxis.Y, height_axis=BoundaryAxis.X,
            height_scale_px_per_mm=PositiveInterval.exact(10.0), lane_reference_trace_px=25.0,
            fixed_height_px=FiniteInterval(79.0, 81.0), canonical_height_px=80.0,
            registered_observations=observations)

    def test_rejected_fit_closes_only_with_complete_original_coverage(self):
        first = self.evaluate()
        self.assertIsNotNone(first.fitted_observation)
        self.assertFalse(first.can_register)
        self.assertFalse(first.closed_structural_rejection)
        covered = self.evaluate(observations=(first.fitted_observation,))
        self.assertTrue(covered.closed_structural_rejection)
        self.assertFalse(replace(covered, query_complete=False).closed_structural_rejection)
        self.assertFalse(replace(covered, covered_observation_ids=()).closed_structural_rejection)
        receipt = owner.CrossRegistrationWorkReceipt(1, 1, 0,
            local_refinement_scope_count=1, local_refinement_scopes=(covered,))
        self.assertTrue(owner.local_cross_refinements_closed(receipt))
        self.assertFalse(owner.local_cross_refinements_closed(replace(receipt, local_refinement_scopes=())))

    def test_accepted_fit_is_not_a_closed_rejection(self):
        first = self.evaluate(rejected=False)
        covered = self.evaluate(rejected=False, observations=(first.fitted_observation,))
        self.assertTrue(covered.can_register)
        self.assertFalse(covered.closed_structural_rejection)

    def test_numerical_failure_and_empty_selection_do_not_close_scope(self):
        first = self.evaluate()
        with patch.object(owner, 'fit_format_bound_boundary_observation', return_value=None):
            failed = self.evaluate(observations=(first.fitted_observation,))
        self.assertTrue(failed.covered_observation_ids)
        self.assertFalse(failed.closed_structural_rejection)
        tied = self.evaluate(((99.0, 101.0),) * 6)
        absent = self.evaluate(((120.0,),) * 6)
        self.assertEqual(len(tied.trace_selections), 6)
        self.assertTrue(all(item.ambiguous for item in tied.trace_selections))
        self.assertFalse(any(item.ambiguous for item in absent.trace_selections))
        self.assertFalse(tied.selected_transition_ids)
        self.assertFalse(absent.selected_transition_ids)
        self.assertFalse(tied.closed_structural_rejection)
        self.assertFalse(absent.closed_structural_rejection)

    def test_mixed_trace_receipt_preserves_ambiguity_and_selection(self):
        scope = self.evaluate(((99.0, 101.0), (100.0,), (100.0,), (120.0,), (100.0,), (100.0,)))
        self.assertEqual(tuple(x.ambiguous for x in scope.trace_selections), (True, False, False, False, False, False))
        self.assertEqual(tuple(x.selected_transition_id is not None for x in scope.trace_selections),
                         (False, True, True, False, True, True))

    def test_covered_selected_points_do_not_close_ambiguous_competition(self):
        coordinates = ((99.0, 101.0),) + ((100.0,),) * 5
        first = self.evaluate(coordinates)
        self.assertIsNotNone(first.fitted_observation)
        covered = self.evaluate(coordinates, observations=(first.fitted_observation,))
        self.assertTrue(covered.covered_observation_ids)
        self.assertFalse(covered.can_register)
        self.assertFalse(covered.closed_structural_rejection)
