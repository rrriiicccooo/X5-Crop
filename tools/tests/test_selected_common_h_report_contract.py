from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
import unittest

from tools.regression.report_validation import (
    _common_authority_comparison_record, _read_common_proof,
    _validate_common_authority_provenance, _validate_finalization,
    _validate_holder_fill_identity, _validate_holder_fill_provenance,
    _validate_nominal_grid_authority, _validate_selected_contact_protection,
    _validate_selected_output_reuse, _validate_sequence_output_line_provenance,
)
from tools.tests.affine_tiff_support import make_deskew_observation
from tools.tests.template_test_support import placement_compose
from tools.tests.test_common_h_output_contract import registration
from tools.tests.test_common_output_contract import translated_h
from tools.tests.test_template_output_contract import _lane, _placement
from x5crop.detection.final.deskew import assess_output_deskew
from x5crop.detection.photo_geometry.model import BoundaryRole, QueryPurpose
from x5crop.detection.photo_geometry.template_common_output import (
    CommonHOutput, assess_common_h_output_authority, materialize_common_h_output,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFailureKind, CrossFitCompetition, CrossFitGroup, CrossFitStatus,
    CrossSearchReceipt, TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_holder_fill import (
    LaneLongAxisAuthority, assess_holder_fill_state, photo_group_outer_from_selected_placement,
)
from x5crop.detection.photo_geometry.template_model import TemplateSearchReceipt
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitResult, PhaseFitStatus, PhaseWinnerBasis
from x5crop.domain import FiniteInterval
from x5crop.geometry.convex import mapped_half_open_box
from x5crop.report.read_models import typed_read_model
from x5crop.report.development import _placement_competition_read_model
from x5crop.detection.photo_geometry.template_runtime_model import TemplatePlacementCompetition
from x5crop.domain import EvidenceState


def selected_common_fixture():
    first = _placement()
    placements = tuple(placement_compose(p.sequence_fit.template, p.sequence_fit,
        replace(p.cross_fit, height_compatibility_px=FiniteInterval.exact(240.0),
                direct_bindings=tuple(replace(b, independent_support_region_count=2,
                                              role_authorized=True) for b in p.cross_fit.direct_bindings)))
        for p in (first, translated_h(first, 5)))
    common = materialize_common_h_output(placements, ((0, 1), (1, 0)), lane=_lane(), layout="horizontal")
    receipt = TemplateSearchReceipt(**{f.name: (1 if f.name == "fit_pass_count" else 0)
                                      for f in fields(TemplateSearchReceipt)})
    phase = PhaseFitResult(placements[0].sequence_fit.template, placements[0].sequence_fit,
        None, PhaseFitStatus.RESOLVED, None, receipt, (), winner_basis=PhaseWinnerBasis.ONLY_PHYSICAL_FIT)
    fits = tuple(p.cross_fit for p in placements)
    cross = CrossFitCompetition(phase.template.template_id, fits[0], fits[1], CrossFitStatus.UNRESOLVED,
        None, "distinct H interpretations", CrossFailureKind.NON_EQUIVALENT_FITS,
        CrossSearchReceipt(2, 2, 4, 2, 0, 4, 256, 256, 4096, 4096),
        fit_groups=tuple(CrossFitGroup(fit, True) for fit in fits),
        conditional_fit_groups=tuple(CrossFitGroup(fit, True) for fit in reversed(fits)))
    bindings = tuple(b for fit in fits for b in fit.direct_bindings)
    traces = tuple(sorted({trace for b in bindings for trace in b.trace_coordinates_px}))
    fixed_height = placements[0].source_scan_geometry.height_state.extent_projection_px()
    inputs = TemplateCrossInput(template=phase.template, fixed_height_px=fixed_height,
        lane_reference_trace_px=placements[0].width_authority_px.center,
        registered_trace_coordinates_px=traces,
        top_bindings=tuple(b for b in bindings if b.role == BoundaryRole.TOP),
        bottom_bindings=tuple(b for b in bindings if b.role == BoundaryRole.BOTTOM))
    authority = assess_common_h_output_authority(common, phase=phase, cross=cross,
        registration=registration(), membership_coverage=(), cross_input=inputs)
    holder = assess_holder_fill_state(photo_group_outer_from_selected_placement(common),
        LaneLongAxisAuthority.from_box(common.lane_id, common.width_axis, _lane().domain.work_box))
    lane = {
        "lane_id": common.lane_id,
        "selected_placement_id": common.placement_id,
        "common_h_output": typed_read_model(common), "common_h_authority": typed_read_model(authority),
        "output_footprints": typed_read_model(common.output_footprints),
        "direct_use_budget_assessments": typed_read_model(common.direct_use_budget_assessments),
        "placement_proposal": {"state": "generated", "placement_id": placements[0].placement_id,
            "output_footprints": typed_read_model(tuple(o.members[0] for o in common.output_footprints)),
            "direct_use_budget_assessments": []},
        "holder_fill_assessment": typed_read_model(holder), "photo_group_outer": typed_read_model(holder.outer),
        "source_scan_geometry": typed_read_model(placements[0].source_scan_geometry),
    }
    development = {
        "lane_id": common.lane_id, "common_h_output": lane["common_h_output"],
        "common_h_authority": lane["common_h_authority"], "phase_competition": typed_read_model(phase),
        "cross_competition": typed_read_model(cross), "cross_registration_work": typed_read_model(registration()),
        "template_spec": typed_read_model(phase.template),
        "observations": {"raw_top_bottom_lines": [], "registered_top_bottom_bindings": typed_read_model(bindings)},
        "placement_competition": {"placements": typed_read_model(placements)},
        "holder_fill_assessment": lane["holder_fill_assessment"],
    }
    query = {"query": {"lane_id": common.lane_id, "purpose": QueryPurpose.TOP_CORRIDOR.value,
                        "trace_positions_px": list(traces)}}
    return common, lane, development, [query]


class SelectedCommonHReportContractTest(unittest.TestCase):
    def setUp(self):
        self.common, self.lane, self.development, self.queries = selected_common_fixture()

    def test_selected_common_preserves_independent_identity_and_full_proof(self):
        self.assertTrue(_validate_selected_output_reuse(self.lane))
        self.assertNotEqual(self.lane["selected_placement_id"], self.lane["placement_proposal"]["placement_id"])
        self.assertEqual(_read_common_proof(typed_read_model(self.common), CommonHOutput), self.common)
        _validate_common_authority_provenance(self.development, self.lane, self.queries)

    def test_development_competition_does_not_duplicate_common_proofs(self):
        from x5crop.detection.photo_geometry.template_common_output import CommonHOutputAuthority
        authority = _read_common_proof(self.lane["common_h_authority"], CommonHOutputAuthority)
        competition = TemplatePlacementCompetition(self.common.placements, self.common.placement_id,
            self.common.placements[1].placement_id, EvidenceState.SUPPORTED, None,
            common_h_output=self.common, common_h_authority=authority)
        value = _placement_competition_read_model(competition)
        self.assertNotIn("common_h_output", value)
        self.assertNotIn("common_h_authority", value)
        self.assertEqual(value["selected_placement_id"], self.common.placement_id)
        self.assertEqual(value["placements"], typed_read_model(self.common.placements))

    def test_common_selection_does_not_require_native_proposal_generation(self):
        self.lane["placement_proposal"] = {"state": "unavailable", "placement_id": None,
            "output_footprints": [], "direct_use_budget_assessments": []}
        self.assertTrue(_validate_selected_output_reuse(self.lane))

    def test_native_selection_still_requires_exact_proposal_reuse(self):
        self.lane["selected_placement_id"] = self.lane["placement_proposal"]["placement_id"]
        with self.assertRaisesRegex(ValueError, "reuse the proposal"):
            _validate_selected_output_reuse(self.lane)
        self.lane["output_footprints"] = self.lane["placement_proposal"]["output_footprints"]
        self.lane["direct_use_budget_assessments"] = self.lane["placement_proposal"]["direct_use_budget_assessments"]
        self.assertFalse(_validate_selected_output_reuse(self.lane))

    def test_summary_cannot_borrow_a_narrower_member_budget(self):
        assessment = deepcopy(self.lane["output_footprints"][0]["member_budgets"][0]["assessment"])
        self.lane["direct_use_budget_assessments"][0] = assessment
        with self.assertRaisesRegex(ValueError, "worst-member budgets"):
            _validate_selected_output_reuse(self.lane)

    def test_unknown_missing_and_bool_fields_are_rejected(self):
        for mutate in (lambda v: v.update(extra=1), lambda v: v.pop("work"),
                       lambda v: v["work"].update(member_count=True),
                       lambda v: v["placements"][0]["frames"][0].update(lane_ordinal=True)):
            with self.subTest(mutate=mutate):
                value = typed_read_model(self.common)
                mutate(value)
                with self.assertRaises(ValueError):
                    _read_common_proof(value, CommonHOutput)

    def test_authority_member_identity_and_replayed_coverage_are_required(self):
        bad = deepcopy(self.development)
        bad["common_h_authority"]["member_placement_ids"].reverse()
        with self.assertRaisesRegex(ValueError, "member identities"):
            _validate_common_authority_provenance(bad, self.lane, self.queries)
        bad = deepcopy(self.development)
        bad["common_h_authority"]["membership_coverage"] = [{
            "parent_family_id": "invented", "role": "top", "member_observation_ids": ["fake-member"],
            "member_transition_ids": ["fake-transition"], "solver_observation_ids": ["fake-solver"],
        }]
        with self.assertRaisesRegex(ValueError, "not reproducible"):
            _validate_common_authority_provenance(bad, self.lane, self.queries)

    def test_every_member_aspect_and_support_receipt_is_recomputed(self):
        for index in range(2):
            for field in ("aperture_aspect_ratio_authorities", "enclosing_support_competitions"):
                with self.subTest(member=index, field=field):
                    bad = deepcopy(self.development)
                    item = bad["common_h_authority"][field][index]
                    if field == "aperture_aspect_ratio_authorities":
                        item["direct_height_px"] = {"minimum": 239.0, "maximum": 241.0}
                    else:
                        item["evaluated_candidate_count"] = 1 - item["evaluated_candidate_count"]
                    with self.assertRaisesRegex(ValueError, "not reproducible"):
                        _validate_common_authority_provenance(bad, self.lane, self.queries)

    def test_support_replay_ignores_generated_names_but_keeps_measurements_and_work(self):
        from tools.tests.test_common_h_selection_contract import _case, _authority
        from x5crop.detection.photo_geometry.template_common_output import CommonHOutputAuthority

        authority = _authority(_case(support_pair=True))
        baseline = _common_authority_comparison_record(authority)
        record = typed_read_model(authority)
        fit = record["enclosing_support_competitions"][0]["best"]
        self.assertIsNotNone(fit)
        fit["selected_direction"]["direction_id"] = "another-run-direction"
        fit["longitudinal_projection_authority"]["authority_id"] = "another-run-projection"
        renamed = _read_common_proof(record, CommonHOutputAuthority)
        self.assertEqual(_common_authority_comparison_record(renamed), baseline)
        for field in ("work", "source", "measurement"):
            with self.subTest(field=field):
                changed = deepcopy(record)
                support = changed["enclosing_support_competitions"][0]
                if field == "work":
                    support["evaluated_candidate_count"] = 0
                elif field == "source":
                    support["best"]["top_binding"]["observation_id"] = "foreign-source-edge"
                    with self.assertRaises(ValueError):
                        _read_common_proof(changed, CommonHOutputAuthority)
                    continue
                else:
                    support["best"]["top_binding"]["fit_residual_px"] += 1.0
                changed = _read_common_proof(changed, CommonHOutputAuthority)
                self.assertNotEqual(_common_authority_comparison_record(changed), baseline)

    def test_contact_protection_cannot_be_completed_by_other_member(self):
        outputs = deepcopy(self.lane["output_footprints"])
        for member in outputs[0]["members"]:
            member["boundary_protections"][1]["topology_relation_id"] = "contact:1"
        expected = {("contact:1", 1, "end")}
        _validate_selected_contact_protection(outputs, expected, common=True)
        outputs[0]["members"][1]["boundary_protections"][1]["topology_relation_id"] = None
        with self.assertRaisesRegex(ValueError, "topology protection"):
            _validate_selected_contact_protection(outputs, expected, common=True)

    def test_common_only_member_sequence_line_provenance_is_checked(self):
        lane = deepcopy(self.development)
        lane["placement_competition"]["placements"] = lane["placement_competition"]["placements"][:1]
        sequence = lane["phase_competition"]["best"]
        lane["observations"].update(sequence_edges=[
            {"observation_id": binding["observation_id"], "fit_direction_interval_degrees": None}
            for binding in sequence["role_bindings"]], cross_height_edges=[], broad_material_edges=[])
        _validate_sequence_output_line_provenance(lane)
        lane["common_h_output"]["placements"][1]["frames"][0]["start"]["line_evidence"] = {"invented": True}
        with self.assertRaisesRegex(ValueError, "frame protection"):
            _validate_sequence_output_line_provenance(lane)

    def test_nominal_and_holder_authority_bind_common_identity(self):
        ids = {o.geometry_id for o in self.common.output_footprints}
        nominal = {"authority_id": "nominal:common", "state": "supported", "evidence_id": "nominal:evidence",
            "placement_id": self.common.placement_id, "output_geometry_ids": list(ids),
            "failure_kind": None, "reason": None}
        _validate_nominal_grid_authority(nominal, selected_placement_id=self.common.placement_id, output_geometry_ids=ids)
        nominal["placement_id"] = self.common.placements[0].placement_id
        with self.assertRaises(ValueError):
            _validate_nominal_grid_authority(nominal, selected_placement_id=self.common.placement_id, output_geometry_ids=ids)
        _validate_holder_fill_identity(self.lane)
        measurement = {"source_lanes": [{"domain": typed_read_model(_lane().domain)}]}
        _validate_holder_fill_provenance(self.development, self.lane, measurement, layout="horizontal")
        self.lane["holder_fill_assessment"]["outer"]["placement_id"] = self.common.placements[0].placement_id
        with self.assertRaisesRegex(ValueError, "holder fill changed"):
            _validate_holder_fill_identity(self.lane)

    def test_holder_free_space_and_development_consistency_are_checked(self):
        bad = deepcopy(self.lane)
        bad["holder_fill_assessment"]["lower"]["free_space_px"]["maximum"] += 1
        with self.assertRaisesRegex(ValueError, "free space"):
            _validate_holder_fill_identity(bad)
        bad = deepcopy(self.development)
        bad["holder_fill_assessment"] = None
        with self.assertRaisesRegex(ValueError, "development holder fill"):
            _validate_holder_fill_provenance(bad, self.lane, {}, layout="horizontal")

    def test_finalization_accepts_common_and_rejects_native_substitution(self):
        extent = self.common.output_footprints[0].source_extent
        deskew = assess_output_deskew(make_deskew_observation(0.0), layout="horizontal",
                                     source_width=extent.width, source_height=extent.height)
        report = {
            "decision": {"status": "approved_auto"},
            "photo_geometry": {"resolved_output_slots": {"lane_output_slot_counts": [1]},
                "output_slot_count": 1, "slot_identities": [{"lane_id": self.common.lane_id, "lane_ordinal": 1}],
                "lanes": [self.lane]},
            "output": {"output_files": [], "review_copy": None, "tiff_fidelity": {"validation": "not_created"},
                "finalization": {"output_footprints": deepcopy(self.lane["output_footprints"]),
                    "final_boxes": [typed_read_model(mapped_half_open_box(o.required_source_footprint,
                                               deskew.transform.map_point)) for o in self.common.output_footprints],
                    "deskew_assessment": typed_read_model(deskew), "frame_export_requested": False,
                    "frame_export_eligible": True, "frame_export_performed": False, "official_tiff_count": 0}},
        }
        _validate_finalization(report, extent)
        report["output"]["finalization"]["output_footprints"] = self.lane["placement_proposal"]["output_footprints"]
        with self.assertRaisesRegex(ValueError, "changed selected output"):
            _validate_finalization(report, extent)


if __name__ == "__main__":
    unittest.main()
