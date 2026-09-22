from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.test_template_output_contract import _enclosing_support_placement, _lane, _placement
from tools.tests.template_test_support import placement_binding, placement_compose, placement_cross_longitudinal_authority
from x5crop.domain import Box, EvidenceState, FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_output import (
    common_aperture_output_footprint, output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)


def translated_h(placement, delta):
    original = placement.cross_fit
    top = original.top_canonical_px + delta
    bottom = original.bottom_canonical_px + delta
    bindings = (placement_binding(BoundaryRole.TOP, f"top:{delta}", top),
                placement_binding(BoundaryRole.BOTTOM, f"bottom:{delta}", bottom))
    fit = replace(original, top_canonical_px=top, bottom_canonical_px=bottom,
        top_fit_interval_px=FiniteInterval.exact(top), bottom_fit_interval_px=FiniteInterval.exact(bottom),
        top_full_interval_px=FiniteInterval.exact(top), bottom_full_interval_px=FiniteInterval.exact(bottom),
        direct_bindings=bindings, direct_provenance_ids=(),
        selected_direction=replace(original.selected_direction, selected_observation_ids=tuple(b.observation_id for b in bindings)),
        longitudinal_projection_authority=placement_cross_longitudinal_authority(placement.sequence_fit.template, *bindings))
    return placement_compose(placement.sequence_fit.template, placement.sequence_fit, fit)


def native_output(placement, lane=None):
    return output_footprint_from_template_placement(placement, project_format_placement(placement),
        lane=lane or _lane(), lane_ordinal=1, layout="horizontal")


class CommonOutputContractTest(unittest.TestCase):
    def test_single_member_has_identical_geometry_and_budget_to_native_owner(self):
        placement = _placement()
        native = native_output(placement)
        common = common_aperture_output_footprint((placement,), (native,))
        for field in ("mandatory_source_footprint", "requested_source_footprint", "required_source_footprint", "saturation_facts"):
            self.assertEqual(getattr(common, field), getattr(native, field))
        self.assertEqual(common.member_budgets[0].assessment.edge_assessments,
                         template_direct_use_budget_assessment(placement, native).edge_assessments)
        self.assertNotEqual(common.geometry_id, native.geometry_id)
        self.assertEqual(common.members, (native,))

    def test_distinct_safe_h_interpretations_share_one_crop_without_merging_identity(self):
        first = _placement()
        second = translated_h(first, 5)
        native = (native_output(first), native_output(second))
        common = common_aperture_output_footprint((first, second), native)
        self.assertTrue(common.budget_supported)
        self.assertTrue(common.source_authority_supported)
        self.assertEqual(common.members, native)
        self.assertEqual(tuple(b.placement_id for b in common.member_budgets), (first.placement_id, second.placement_id))
        self.assertTrue(all(b.assessment.geometry_id == common.geometry_id for b in common.member_budgets))
        self.assertNotEqual(native[0].requested_source_footprint, native[1].requested_source_footprint)
        self.assertGreater(max(y for _, y in common.required_source_footprint), max(y for _, y in native[0].required_source_footprint))
        reversed_common = common_aperture_output_footprint((second, first), tuple(reversed(native)))
        self.assertEqual(reversed_common.geometry_id, common.geometry_id)
        self.assertEqual(reversed_common.required_source_footprint, common.required_source_footprint)
        self.assertEqual(tuple(reversed(reversed_common.member_budgets)), common.member_budgets)
        with self.assertRaisesRegex(ValueError, "every native member"):
            replace(common, member_budgets=common.member_budgets[:1])
        with self.assertRaisesRegex(ValueError, "lost a native member"):
            replace(common, requested_source_footprint=native[0].requested_source_footprint)

    def test_individually_safe_outputs_can_have_an_over_budget_common_crop(self):
        first = _placement()
        second = translated_h(first, 20)
        native = (native_output(first), native_output(second))
        self.assertTrue(all(template_direct_use_budget_assessment(p, o).state == EvidenceState.SUPPORTED
                            for p, o in zip((first, second), native)))
        common = common_aperture_output_footprint((first, second), native)
        self.assertFalse(common.budget_supported)
        self.assertEqual(len(common.member_budgets), 2)
        self.assertTrue(any(not edge.within_limit for member in common.member_budgets for edge in member.assessment.edge_assessments))

    def test_source_clipping_does_not_erase_requested_budget_risk(self):
        first = _placement()
        second = translated_h(first, -20)
        common = common_aperture_output_footprint((first, second), (native_output(first), native_output(second)))
        self.assertTrue(common.source_authority_supported)
        self.assertTrue(common.saturation_facts)
        self.assertLess(min(y for _, y in common.requested_source_footprint), min(y for _, y in common.required_source_footprint))
        self.assertFalse(common.budget_supported)

    def test_internal_lane_edge_is_not_clipped_into_approval(self):
        first = _placement()
        second = translated_h(first, 5)
        lane = _lane()
        lane = replace(lane, domain=replace(lane.domain, work_box=Box(0, 12, 500, 400)))
        common = common_aperture_output_footprint((first, second), (native_output(first, lane), native_output(second, lane)))
        self.assertFalse(common.source_authority_supported)
        self.assertEqual(common.required_source_footprint, common.requested_source_footprint)

    def test_members_cannot_change_w_or_borrow_enclosing_support_risk(self):
        first = _placement()
        native = native_output(first)
        with self.assertRaisesRegex(ValueError, "repeats a placement"):
            common_aperture_output_footprint((first, first), (native, native))
        second = translated_h(first, 5)
        second = replace(second, width_authority_px=FiniteInterval(1, second.width_authority_px.maximum))
        with self.assertRaisesRegex(ValueError, "identical W ownership"):
            common_aperture_output_footprint((first, second), (native, native_output(second)))
        enclosing = _enclosing_support_placement()
        with self.assertRaisesRegex(ValueError, "enclosing-support risk"):
            common_aperture_output_footprint((enclosing,), (native_output(enclosing),))

    def test_missing_or_over_bound_members_cannot_be_silently_truncated(self):
        from x5crop.detection.photo_geometry.template_measurement_plan_model import MAX_CROSS_PAIRS

        placement = _placement()
        native = native_output(placement)
        for placements, outputs in (
            ((), ()), ((placement,), ()),
            ((placement,) * (MAX_CROSS_PAIRS + 1), (native,) * (MAX_CROSS_PAIRS + 1)),
        ):
            with self.assertRaisesRegex(ValueError, "bounded, complete member list"):
                common_aperture_output_footprint(placements, outputs)


if __name__ == "__main__":
    unittest.main()
