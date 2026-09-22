from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.test_common_output_contract import native_output, translated_h
from tools.tests.test_template_output_contract import _lane, _placement
from tools.tests.test_template_cross_contract import aspect_input, binding, template
from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_common_output import common_h_fit_members, materialize_common_h_output
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_family_membership import MembershipFitBudget, MembershipReceipt, MembershipState
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_registration import CrossRegistrationWorkReceipt


def registration():
    membership = MembershipReceipt(MembershipState.COMPLETE, (), tuple(
        MembershipFitBudget(role, 0, 0, 0, 0) for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM)), ())
    return CrossRegistrationWorkReceipt(0, 0, 0, membership=membership)


class CommonHOutputContractTest(unittest.TestCase):
    def test_every_supported_group_survives_and_identical_views_share_computation(self):
        tops = tuple(binding(BoundaryRole.TOP, f'top-{i}', 100 + i) for i in range(4))
        conditional = replace(binding(BoundaryRole.TOP, 'conditional', 104), conditional_family_ids=('family',))
        cross = fit_template_cross(aspect_input(template=template(), fixed_height_px=FiniteInterval(230, 250),
            top_bindings=(*tops, conditional), bottom_bindings=(binding(BoundaryRole.BOTTOM, 'bottom', 340),)))
        members, views = common_h_fit_members(cross, registration())
        self.assertEqual(len(members), 5)
        for actual, expected in zip(views, (cross.fit_groups, cross.conditional_fit_groups), strict=True):
            self.assertEqual(tuple(members[i] for i in actual), tuple(g.fit for g in expected))
        self.assertIsNone(common_h_fit_members(cross, replace(registration(), local_refinement_scope_count=1)))
        self.assertIsNone(common_h_fit_members(cross, replace(registration(), membership=None)))
        unsupported = replace(cross, fit_groups=(replace(cross.fit_groups[0], independently_supported=False), *cross.fit_groups[1:]))
        self.assertIsNone(common_h_fit_members(unsupported, registration()))

    def test_materialization_reuses_only_the_identical_native_output(self):
        first = _placement()
        second = translated_h(first, 5)
        native = native_output(first)
        with patch('x5crop.detection.photo_geometry.template_common_output.project_format_placement', wraps=project_format_placement) as project:
            result = materialize_common_h_output((first, second), ((0, 1), (0, 1)), lane=_lane(),
                layout='horizontal', reusable=((first, (native,)),))
        self.assertIsNone(result.failure)
        self.assertEqual(project.call_count, 1)
        self.assertEqual(result.work.reused_projection_count, 1)
        self.assertEqual(result.work.projection_count, 1)
        self.assertEqual(result.work.output_evaluation_count, 1)
        self.assertEqual(result.output_footprints[0].members[0], native)
        self.assertTrue(result.output_footprints[0].budget_supported)
        with self.assertRaisesRegex(ValueError, 'complete group mapping'):
            replace(result, group_member_indices=((0,), (0,)))

    def test_over_budget_member_is_retained_in_generated_common_geometry(self):
        first = _placement()
        second = translated_h(first, 20)
        result = materialize_common_h_output((first, second), ((0, 1), ()), lane=_lane(), layout='horizontal')
        self.assertIsNone(result.failure)
        self.assertFalse(result.output_footprints[0].budget_supported)
        self.assertEqual(result.work.member_budget_evaluation_bound, 2)
        self.assertEqual(len(result.output_footprints[0].member_budgets), 2)

    def test_failed_member_withholds_the_whole_common_output_and_keeps_work(self):
        first = _placement()
        second = translated_h(first, 5)
        with patch('x5crop.detection.photo_geometry.template_common_output.project_format_placement',
                   side_effect=(project_format_placement(first), ValueError('member cannot project'))):
            result = materialize_common_h_output((first, second), ((0, 1), ()), lane=_lane(), layout='horizontal')
        self.assertIsNotNone(result.failure)
        self.assertEqual(result.output_footprints, ())
        self.assertEqual(result.placements, (first, second))
        self.assertEqual(result.work.projection_count, 2)
        self.assertEqual(result.work.output_evaluation_count, 1)


if __name__ == '__main__':
    unittest.main()
