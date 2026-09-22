from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.regression.common_output_validation import validate_common_h_output
from tools.tests.test_common_output_contract import native_output, translated_h
from tools.tests.test_common_h_output_contract import registration
from tools.tests.test_template_output_contract import _lane, _placement
from x5crop.detection.photo_geometry.template_common_output import materialize_common_h_output
from x5crop.detection.photo_geometry.template_output import template_direct_use_budget_assessment
from x5crop.domain import Box
from x5crop.report.read_models import typed_read_model


def fixture(delta=5):
    first = _placement()
    placements = first, translated_h(first, delta)
    result = materialize_common_h_output(placements, ((0, 1), (1, 0)), lane=_lane(), layout="horizontal")
    cross = {"fit_groups": [{"fit": typed_read_model(p.cross_fit), "independently_supported": True}
                            for p in placements],
             "conditional_fit_groups": [{"fit": typed_read_model(p.cross_fit), "independently_supported": True}
                                        for p in reversed(placements)]}
    return result, cross


class CommonOutputReportContractTest(unittest.TestCase):
    def setUp(self):
        self.result, self.cross = fixture()
        self.value = typed_read_model(self.result)
        self.extent = self.result.output_footprints[0].source_extent

    def validate(self, value, **kwargs):
        validate_common_h_output(value, expected_source_extent=self.extent, **kwargs)

    def test_current_typed_proof_and_optional_development_links_pass(self):
        self.validate(None)
        self.validate(self.value)
        self.validate(self.value, cross_competition=self.cross,
                      cross_registration_work=typed_read_model(registration()),
                      phase_best=typed_read_model(self.result.placements[0].sequence_fit))
        result, cross = fixture(20)
        self.assertFalse(result.output_footprints[0].budget_supported)
        self.validate(typed_read_model(result), cross_competition=cross)

    def test_missing_member_or_budget_is_rejected(self):
        for key in ("members", "member_budgets"):
            with self.subTest(key=key):
                bad = deepcopy(self.value)
                bad["output_footprints"][0][key].pop()
                with self.assertRaises(ValueError):
                    self.validate(bad)

    def test_changed_group_mapping_and_omitted_unsupported_group_are_rejected(self):
        bad = deepcopy(self.value)
        bad["group_member_indices"][1].reverse()
        with self.assertRaisesRegex(ValueError, "retained Cross group"):
            self.validate(bad, cross_competition=self.cross)
        cross = deepcopy(self.cross)
        third = typed_read_model(translated_h(self.result.placements[0], 8).cross_fit)
        cross["fit_groups"].append({"fit": third, "independently_supported": False})
        with self.assertRaisesRegex(ValueError, "retained Cross group"):
            self.validate(self.value, cross_competition=cross)
        # A support flag cannot remove an otherwise fully mapped interpretation.
        cross = deepcopy(self.cross)
        cross["fit_groups"][0]["independently_supported"] = False
        self.validate(self.value, cross_competition=cross)

    def test_full_fit_equality_is_used_for_deduplication(self):
        cross = deepcopy(self.cross)
        cross["conditional_fit_groups"][0]["fit"]["direct_provenance_ids"] = ["changed"]
        with self.assertRaisesRegex(ValueError, "retained Cross group"):
            self.validate(self.value, cross_competition=cross)

    def test_changed_common_hull_source_clipping_or_saturation_is_rejected(self):
        clipped, _ = fixture(-20)
        value = typed_read_model(clipped)
        self.assertTrue(value["output_footprints"][0]["saturation_facts"])
        self.validate(value)
        for key in ("mandatory_source_footprint", "requested_source_footprint", "required_source_footprint"):
            with self.subTest(key=key):
                bad = deepcopy(value)
                bad["output_footprints"][0][key][0][0] += 1
                with self.assertRaises(ValueError):
                    self.validate(bad)
        bad = deepcopy(value)
        bad["output_footprints"][0]["saturation_facts"] = []
        with self.assertRaisesRegex(ValueError, "clipping or saturation"):
            self.validate(bad)

    def test_native_budget_cannot_replace_wider_common_budget(self):
        result, _ = fixture(20)
        bad = typed_read_model(result)
        common = bad["output_footprints"][0]
        for index, placement in enumerate(result.placements):
            assessment = typed_read_model(template_direct_use_budget_assessment(placement, native_output(placement)))
            assessment["geometry_id"] = common["geometry_id"]
            common["member_budgets"][index]["assessment"] = assessment
        with self.assertRaisesRegex(ValueError, "common requested footprint"):
            self.validate(bad)

    def test_every_budget_field_is_verified(self):
        for key, value in (("expansion_px", 0), ("expansion_mm", 0), ("limit_mm", 100),
                           ("limit_applies", False), ("within_limit", 1), ("role", "top")):
            with self.subTest(key=key):
                bad = deepcopy(self.value)
                bad["output_footprints"][0]["member_budgets"][0]["assessment"]["edge_assessments"][0][key] = value
                with self.assertRaises(ValueError):
                    self.validate(bad)
        for key, value in (("state", "contradicted"), ("enclosing_support_height_ratio", 1.01),
                           ("unexpected", True)):
            with self.subTest(key=key):
                bad = deepcopy(self.value)
                bad["output_footprints"][0]["member_budgets"][0]["assessment"][key] = value
                with self.assertRaises(ValueError):
                    self.validate(bad)

    def test_second_member_uses_its_own_budget_and_source_scale(self):
        bad = deepcopy(self.value)
        bad["output_footprints"][0]["member_budgets"][1]["assessment"]["edge_assessments"][2]["expansion_px"] = 0
        with self.assertRaisesRegex(ValueError, "common requested footprint"):
            self.validate(bad)
        bad = deepcopy(self.value)
        for placement in bad["placements"]:
            for vertex in placement["source_scan_geometry"]["height_state"]["vertices"]:
                vertex[0] /= 2
        with self.assertRaisesRegex(ValueError, "common requested footprint"):
            self.validate(bad)

    def test_internal_lane_overflow_stays_unclipped(self):
        lane = _lane()
        lane = replace(lane, domain=replace(lane.domain, work_box=Box(0, 12, 500, 400)))
        result = materialize_common_h_output(self.result.placements, ((0, 1), (1, 0)),
                                            lane=lane, layout="horizontal")
        self.assertFalse(result.output_footprints[0].source_authority_supported)
        self.validate(typed_read_model(result))

    def test_swapped_placement_or_native_identity_is_rejected(self):
        for target in ("envelope", "budget"):
            with self.subTest(target=target):
                bad = deepcopy(self.value)
                output = bad["output_footprints"][0]
                record = output["members"][0]["envelope"] if target == "envelope" else output["member_budgets"][0]
                record["placement_id"] = bad["placements"][1]["placement_id"]
                with self.assertRaises(ValueError):
                    self.validate(bad)

    def test_failed_proposal_cannot_expose_partial_output(self):
        with patch("x5crop.detection.photo_geometry.template_common_output.project_format_placement",
                   side_effect=ValueError("cannot project member")):
            failed = materialize_common_h_output(self.result.placements, ((0, 1), (1, 0)),
                                                 lane=_lane(), layout="horizontal")
        value = typed_read_model(failed)
        self.validate(value)
        bad = deepcopy(value)
        bad["work"]["output_evaluation_count"] = 100
        with self.assertRaisesRegex(ValueError, "work exceeds"):
            self.validate(bad)
        value["output_footprints"] = self.value["output_footprints"]
        with self.assertRaisesRegex(ValueError, "partial crop"):
            self.validate(value)

    def test_work_bounds_fixed_w_and_development_links_are_verified(self):
        for mutate in (
            lambda v: v["work"].update(output_evaluation_count=100),
            lambda v: v["work"].update(member_budget_evaluation_bound=1),
            lambda v: v["work"].update(member_count=True),
            lambda v: v["group_member_indices"][0].__setitem__(0, False),
            lambda v: v["group_member_indices"][0].__setitem__(0, -1),
            lambda v: v["group_member_indices"][0].__setitem__(0, 2),
            lambda v: v["placements"][1].update(width_axis="y"),
            lambda v: v["placements"][1]["source_scan_geometry"].update(geometry_id="different"),
            lambda v: v.update(unexpected=True),
        ):
            bad = deepcopy(self.value)
            mutate(bad)
            with self.assertRaises(ValueError):
                self.validate(bad)
        for work in (replace(registration(), local_refinement_scope_count=1),
                     replace(registration(), membership=None)):
            with self.assertRaises(ValueError):
                self.validate(self.value, cross_registration_work=typed_read_model(work))
        with self.assertRaisesRegex(ValueError, "retained phase"):
            self.validate(self.value, phase_best={})

    def test_native_member_authority_validation_is_not_skipped(self):
        bad = deepcopy(self.value)
        bad["output_footprints"][0]["members"][1]["boundary_protections"][0]["joint_expansion_px"] = -1
        with self.assertRaises(ValueError):
            self.validate(bad)


if __name__ == "__main__":
    unittest.main()
