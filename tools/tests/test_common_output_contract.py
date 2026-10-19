from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.output_fixture_support import (
    _enclosing_support_placement,
    _lane,
    _placement,
    native_output,
    translated_h,
)
from tools.tests.template_test_support import placement_binding, placement_compose, placement_cross_longitudinal_authority
from x5crop.domain import Box, EvidenceState, FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_output import (
    common_h_output_footprint, output_footprint_from_template_placement,
    common_phase_output_footprint,
    template_direct_use_budget_assessment,
)


class CommonOutputContractTest(unittest.TestCase):
    def test_third_phase_member_can_invalidate_an_otherwise_safe_common_window(self):
        first = _placement()
        second = translated_h(first, 5)
        third = translated_h(first, 35)
        placements = (first, second, third)
        native = tuple(native_output(p) for p in placements)
        pair = common_phase_output_footprint(placements[:2], native[:2])
        complete = common_phase_output_footprint(placements, native)
        self.assertTrue(pair.budget_supported)
        self.assertFalse(complete.budget_supported)
        self.assertEqual(len(complete.member_budgets), 3)
        reverse = common_phase_output_footprint(tuple(reversed(placements)), tuple(reversed(native)))
        self.assertEqual(reverse.requested_source_footprint, complete.requested_source_footprint)
        self.assertEqual(reverse.geometry_id, complete.geometry_id)

    def test_phase_common_window_cannot_invent_a_source_size_identity(self):
        first = _placement()
        second = translated_h(first, 5)
        second = replace(second, source_scan_geometry=replace(second.source_scan_geometry,
                         geometry_id="foreign-source-size"))
        with self.assertRaisesRegex(ValueError, "same fixed source W/H"):
            common_phase_output_footprint((first, second), (native_output(first), native_output(second)))

    def test_single_member_has_identical_geometry_and_budget_to_native_owner(self):
        placement = _placement()
        native = native_output(placement)
        common = common_h_output_footprint((placement,), (native,))
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
        common = common_h_output_footprint((first, second), native)
        self.assertTrue(common.budget_supported)
        self.assertTrue(common.source_authority_supported)
        self.assertEqual(common.members, native)
        self.assertEqual(tuple(b.placement_id for b in common.member_budgets), (first.placement_id, second.placement_id))
        self.assertTrue(all(b.assessment.geometry_id == common.geometry_id for b in common.member_budgets))
        self.assertNotEqual(native[0].requested_source_footprint, native[1].requested_source_footprint)
        self.assertGreater(max(y for _, y in common.required_source_footprint), max(y for _, y in native[0].required_source_footprint))
        reversed_common = common_h_output_footprint((second, first), tuple(reversed(native)))
        self.assertEqual(reversed_common.geometry_id, common.geometry_id)
        self.assertEqual(reversed_common.requested_source_footprint, common.requested_source_footprint)
        self.assertEqual(reversed_common.required_source_footprint, common.required_source_footprint)
        self.assertEqual(reversed_common.fixed_size, common.fixed_size)
        self.assertEqual(reversed_common.width_axis, common.width_axis)
        self.assertEqual(reversed_common.sequence_direction, common.sequence_direction)
        self.assertAlmostEqual(
            common.requested_source_footprint[1][0]
            - common.requested_source_footprint[0][0],
            common.fixed_size.output_width_px,
        )
        self.assertAlmostEqual(
            common.requested_source_footprint[2][1]
            - common.requested_source_footprint[1][1],
            common.fixed_size.output_height_px,
        )
        mandatory_x = tuple(x for x, _ in common.mandatory_source_footprint)
        mandatory_y = tuple(y for _, y in common.mandatory_source_footprint)
        requested_x = tuple(x for x, _ in common.requested_source_footprint)
        requested_y = tuple(y for _, y in common.requested_source_footprint)
        self.assertAlmostEqual(
            min(requested_x), -.5,
        )
        self.assertAlmostEqual(max(requested_x), -.5 + common.fixed_size.output_width_px)
        self.assertLessEqual(max(requested_x), common.source_extent.width - .5)
        self.assertLessEqual(min(requested_x), min(mandatory_x))
        self.assertGreaterEqual(max(requested_x), max(mandatory_x))
        self.assertAlmostEqual(
            (min(requested_y) + max(requested_y)) / 2.0,
            (min(mandatory_y) + max(mandatory_y)) / 2.0,
        )
        self.assertEqual(tuple(reversed(reversed_common.member_budgets)), common.member_budgets)
        with self.assertRaisesRegex(ValueError, "every native member"):
            replace(common, member_budgets=common.member_budgets[:1])
        with self.assertRaisesRegex(ValueError, "fixed output window"):
            replace(common, requested_source_footprint=native[0].requested_source_footprint)

    def test_individually_safe_outputs_can_have_an_over_budget_common_crop(self):
        first = _placement()
        second = translated_h(first, 30)
        native = (native_output(first), native_output(second))
        self.assertTrue(all(template_direct_use_budget_assessment(p, o).state == EvidenceState.SUPPORTED
                            for p, o in zip((first, second), native)))
        common = common_h_output_footprint((first, second), native)
        self.assertFalse(common.budget_supported)
        self.assertEqual(len(common.member_budgets), 2)
        self.assertAlmostEqual(
            common.requested_source_footprint[2][1]
            - common.requested_source_footprint[1][1],
            common.fixed_size.output_height_px,
        )
        self.assertTrue(any(not edge.within_limit for member in common.member_budgets for edge in member.assessment.edge_assessments))

    def test_avoidable_source_clipping_keeps_complete_window_and_every_member_budget(self):
        first = _placement()
        second = translated_h(first, -20)
        common = common_h_output_footprint((first, second), (native_output(first), native_output(second)))
        self.assertTrue(common.source_authority_supported)
        self.assertFalse(common.saturation_facts)
        self.assertEqual(common.requested_source_footprint, common.required_source_footprint)
        self.assertTrue(common.budget_supported)
        self.assertTrue(all(member.assessment.state == EvidenceState.SUPPORTED for member in common.member_budgets))
        self.assertGreaterEqual(min(y for _, y in common.requested_source_footprint), -.5)
        self.assertAlmostEqual(
            common.requested_source_footprint[2][1]
            - common.requested_source_footprint[1][1],
            common.fixed_size.output_height_px,
        )

    def test_unavoidable_short_source_clipping_preserves_all_common_members(self):
        first = _placement()
        second = translated_h(first, -20)
        lane = _lane()
        lane = replace(lane, domain=replace(lane.domain, work_box=Box(0, 0, 500, 80)),
                       scan_canvas=replace(lane.scan_canvas, observed_short_axis_px=80))
        native = (native_output(first, lane), native_output(second, lane))
        common = common_h_output_footprint((first, second), native)
        self.assertEqual(common.members, native)
        self.assertTrue(common.source_authority_supported)
        self.assertTrue(common.saturation_facts)
        self.assertTrue(common.budget_supported)
        self.assertTrue(all(member.assessment.state == EvidenceState.SUPPORTED for member in common.member_budgets))
        self.assertAlmostEqual(max(y for _, y in common.requested_source_footprint)
                               - min(y for _, y in common.requested_source_footprint), common.fixed_size.output_height_px)
        self.assertEqual((min(y for _, y in common.required_source_footprint),
                          max(y for _, y in common.required_source_footprint)), (-.5, 79.5))

    def test_internal_lane_edge_is_not_clipped_into_approval(self):
        first = _placement()
        second = translated_h(first, 5)
        lane = _lane()
        lane = replace(lane, domain=replace(lane.domain, work_box=Box(0, 12, 500, 400)))
        common = common_h_output_footprint((first, second), (native_output(first, lane), native_output(second, lane)))
        self.assertFalse(common.source_authority_supported)
        self.assertEqual(common.required_source_footprint, common.requested_source_footprint)

    def test_members_require_distinct_identity_shared_w_and_matching_projection(self):
        first = _placement()
        native = native_output(first)
        with self.assertRaisesRegex(ValueError, "repeats a placement"):
            common_h_output_footprint((first, first), (native, native))
        second = translated_h(first, 5)
        second = replace(second, width_authority_px=FiniteInterval(1, second.width_authority_px.maximum))
        with self.assertRaisesRegex(ValueError, "identical W ownership"):
            common_h_output_footprint((first, second), (native, native_output(second)))
        enclosing = _enclosing_support_placement()
        common = common_h_output_footprint((enclosing,), (native_output(enclosing),))
        self.assertTrue(common.budget_supported)
        with self.assertRaisesRegex(ValueError, "identity or order"):
            common_h_output_footprint(
                (enclosing,),
                (native_output(enclosing),),
                projections=(project_format_placement(first),),
            )

    def test_missing_or_over_bound_members_cannot_be_silently_truncated(self):
        from x5crop.detection.photo_geometry.template_measurement_plan_model import MAX_CROSS_PAIRS

        placement = _placement()
        native = native_output(placement)
        for placements, outputs in (
            ((), ()), ((placement,), ()),
            ((placement,) * (MAX_CROSS_PAIRS + 1), (native,) * (MAX_CROSS_PAIRS + 1)),
        ):
            with self.assertRaisesRegex(ValueError, "bounded, complete member list"):
                common_h_output_footprint(placements, outputs)


if __name__ == "__main__":
    unittest.main()
