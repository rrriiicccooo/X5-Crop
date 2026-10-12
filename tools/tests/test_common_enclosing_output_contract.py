from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.cross_fixture_support import native_coarse_fixture
from tools.tests.output_fixture_support import _enclosing_support_placement, _lane, native_output, registration
from tools.regression.common_output_validation import validate_common_h_output
from x5crop.domain import EvidenceState
from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.template_common_output import materialize_common_h_output, common_h_fit_members
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_output import template_direct_use_budget_assessment


class CommonEnclosingOutputContractTest(unittest.TestCase):
    def common(self, delta):
        placements = tuple(_enclosing_support_placement(support_center_px=152+i*delta) for i in range(2))
        with patch('x5crop.detection.photo_geometry.template_common_output.project_format_placement',
                   wraps=project_format_placement) as project:
            common = materialize_common_h_output(placements, ((0, 1), ()), lane=_lane(), layout='horizontal')
        self.assertIsNone(common.failure)
        self.assertEqual(project.call_count, 2)
        self.assertEqual(common.work.member_budget_evaluation_bound, 2)
        return common

    def test_common_request_keeps_each_support_member_and_replays_its_budget(self):
        common = self.common(1)
        output = common.output_footprints[0]
        self.assertTrue(output.budget_supported)
        validate_common_h_output(typed_read_model(common), expected_source_extent=output.source_extent)
        for index in range(2):
            bad = typed_read_model(common)
            bad['output_footprints'][0]['member_budgets'][index]['assessment']['edge_assessments'][2]['required_extent_px'] = 0
            with self.assertRaises(ValueError):
                validate_common_h_output(bad, expected_source_extent=output.source_extent)

    def test_individually_safe_supports_cannot_lend_native_budgets_to_common_crop(self):
        common = self.common(30)
        output = common.output_footprints[0]
        self.assertFalse(output.budget_supported)
        for p, native in zip(common.placements, output.members, strict=True):
            self.assertEqual(template_direct_use_budget_assessment(p, native).state, EvidenceState.SUPPORTED)
        bad = typed_read_model(common)
        for index, (p, native) in enumerate(zip(common.placements, output.members, strict=True)):
            budget = typed_read_model(template_direct_use_budget_assessment(p, native))
            budget['geometry_id'] = output.geometry_id
            bad['output_footprints'][0]['member_budgets'][index]['assessment'] = budget
        with self.assertRaisesRegex(ValueError, 'member budget'):
            validate_common_h_output(bad, expected_source_extent=output.source_extent)

    def test_position_uncertainty_is_not_counted_again_as_alignment_padding(self):
        from x5crop.detection.photo_geometry.template_output import common_h_output_footprint
        p = _enclosing_support_placement(support_position_uncertainty_px=2)
        native = native_output(p)
        common = common_h_output_footprint((p,), (native,), projections=(project_format_placement(p),))
        self.assertEqual(
            common.member_budgets[0].assessment.edge_assessments,
            template_direct_use_budget_assessment(p, native).edge_assessments,
        )

    def test_forged_narrow_center_interval_is_rejected_before_budget_replay(self):
        common = self.common(1)
        bad = typed_read_model(common)
        center = bad['placements'][0]['enclosing_support_aperture_authority']
        self.assertEqual(center['state'], 'unavailable')
        from x5crop.detection.photo_geometry.template_enclosing_support_aperture import derive_enclosing_support_aperture_authority
        bad['placements'][0]['enclosing_support_aperture_authority'] = typed_read_model(
            derive_enclosing_support_aperture_authority(common.placements[0].cross_fit))
        with self.assertRaisesRegex(ValueError, 'center authority'):
            validate_common_h_output(bad, expected_source_extent=common.output_footprints[0].source_extent)

    def test_all_support_members_and_canonical_permission_are_required(self):
        _, _, cross, *_ = native_coarse_fixture()
        self.assertEqual(tuple(f.direct_bindings for f in cross.enclosing_support_fits), cross.support_pair_bindings)
        from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus, CrossFailureKind
        cross = replace(cross, status=CrossFitStatus.UNRESOLVED, winner_basis=None,
            failure_kind=CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE, reason='unresolved support set',
            support_output_eligible=True)
        self.assertEqual(common_h_fit_members(cross, registration())[0], cross.enclosing_support_fits)
        with self.assertRaisesRegex(ValueError, 'complete support ledger'):
            replace(cross, enclosing_support_fits=cross.enclosing_support_fits[:1])
        self.assertIsNone(common_h_fit_members(cross, replace(registration(), local_refinement_scope_count=1)))
        self.assertIsNone(common_h_fit_members(replace(cross, support_output_eligible=False), registration()))


if __name__ == '__main__':
    unittest.main()
