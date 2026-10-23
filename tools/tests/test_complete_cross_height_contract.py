"""A complete alternative H envelope sizes output without selecting a fit."""

from copy import deepcopy
from dataclasses import replace
import unittest

from tools.regression.report_validation import _validate_complete_height_provenance
from tools.tests.cross_fixture_support import binding
from tools.tests.output_fixture_support import _case, _lane, registration, translated_h
from x5crop.domain import EvidenceState, FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_common_output import (
    complete_cross_height_calibration, materialize_common_h_output,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import CrossFitGroup
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_placement import compose_format_placement
from x5crop.detection.photo_geometry.template_phase_model import PhaseFailureKind, PhaseFitStatus
from x5crop.detection.photo_geometry.template_output import output_footprint_from_template_placement
from x5crop.report.read_models import typed_read_model


class CompleteCrossHeightContractTest(unittest.TestCase):
    def setUp(self):
        self.phase, self.cross, self.inputs, self.common = _case()
        self.source = self.common.source_scan_geometry
        self.inputs = replace(self.inputs, fixed_height_px=self.source.height_state.extent_projection_px())
        self.cross = fit_template_cross(self.inputs)
        self.work = registration()

    def calibrate(self, **changes):
        values = dict(phase=self.phase, cross=self.cross, registration=self.work,
                      observations=(), cross_input=self.inputs)
        values.update(changes)
        return complete_cross_height_calibration(self.source, **values)

    def test_disjoint_alternatives_keep_or_hull_and_do_not_change_competition(self):
        original = typed_read_model((self.phase, self.cross, self.inputs, self.work))
        proof = self.calibrate()
        self.assertEqual(proof.member_height_intervals_px,
                         (FiniteInterval.exact(240), FiniteInterval.exact(239)))
        self.assertEqual(proof.height_hull_px, FiniteInterval(239, 240))
        # This representative is an output size, not a newly observed H or a
        # shared point satisfying both mutually exclusive measurements.
        height = proof.source_geometry.fixed_output_size.frame_height_px
        self.assertTrue(239 < height < 240)
        self.assertTrue(all(not h.contains(height) for h in proof.member_height_intervals_px))
        self.assertEqual(proof.source_geometry.width_state, self.source.width_state)
        self.assertEqual(typed_read_model((self.phase, self.cross, self.inputs, self.work)), original)

    def test_member_order_changes_no_physical_size_or_provenance(self):
        first = self.calibrate()
        second = self.calibrate(cross=replace(self.cross, fit_groups=tuple(reversed(self.cross.fit_groups))))
        self.assertEqual(first.source_geometry, second.source_geometry)
        self.assertEqual(first.height_hull_px, second.height_hull_px)

    def test_incomplete_membership_or_refinement_cannot_calibrate(self):
        failed = replace(self.work, membership=None)
        self.assertIsNone(self.calibrate(registration=failed))
        missing_scope = replace(self.work, local_refinement_scope_count=1)
        self.assertIsNone(self.calibrate(registration=missing_scope))
        phase = replace(self.phase, status=PhaseFitStatus.UNRESOLVED, winner_basis=None,
                        failure_kind=PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE)
        self.assertIsNone(self.calibrate(phase=phase))

    def test_unqualified_conditional_member_cannot_borrow_canonical_support(self):
        fit = self.cross.fit_groups[0].fit
        cross = replace(self.cross, conditional_fit_groups=(CrossFitGroup(fit, False),))
        self.assertIsNone(self.calibrate(cross=cross))

    def test_ratio_counterevidence_withholds_collective_height(self):
        _phase, cross, inputs, _common = _case(aspect_height=FiniteInterval(239.5, 240.5))
        self.assertIsNone(self.calibrate(cross=cross, cross_input=inputs))

    def test_new_source_size_preserves_every_native_joint_state_and_mandatory(self):
        proof = self.calibrate()
        for old in self.common.placements:
            new = compose_format_placement(lane_id=old.lane_id, frame_spec=old.frame_spec,
                source_scan_geometry=proof.source_geometry, sequence_fit=old.sequence_fit,
                global_lattice_authority=old.global_lattice_authority, cross_fit=old.cross_fit,
                width_axis=old.width_axis, height_axis=old.height_axis,
                width_authority_px=old.width_authority_px, height_authority_px=old.height_authority_px)
            self.assertNotEqual(old.placement_id, new.placement_id)
            self.assertEqual(old.frames, new.frames)
            old_projection, new_projection = map(project_format_placement, (old, new))
            self.assertEqual(old_projection.frame_states, new_projection.frame_states)
            outputs = tuple(output_footprint_from_template_placement(p, projection,
                lane=_lane(), lane_ordinal=1, layout="horizontal")
                for p, projection in ((old, old_projection), (new, new_projection)))
            self.assertEqual(outputs[0].mandatory_source_footprint, outputs[1].mandatory_source_footprint)
            self.assertNotEqual(outputs[0].fixed_size, outputs[1].fixed_size)

    def test_calibrated_size_does_not_override_an_over_budget_member(self):
        proof = self.calibrate()
        first = replace(self.common.placements[0], source_scan_geometry=proof.source_geometry)
        shifted = translated_h(first, 30)
        shifted = compose_format_placement(lane_id=first.lane_id, frame_spec=first.frame_spec,
            source_scan_geometry=proof.source_geometry, sequence_fit=first.sequence_fit,
            global_lattice_authority=first.global_lattice_authority, cross_fit=shifted.cross_fit,
            width_axis=first.width_axis, height_axis=first.height_axis,
            width_authority_px=first.width_authority_px, height_authority_px=first.height_authority_px)
        members = (first, shifted)
        common = materialize_common_h_output(members, ((0, 1), ()), lane=_lane(), layout="horizontal")
        self.assertEqual(len(common.output_footprints[0].member_budgets), 2)
        self.assertFalse(common.output_footprints[0].budget_supported)
        self.assertTrue(any(b.assessment.state == EvidenceState.CONTRADICTED
                            for b in common.output_footprints[0].member_budgets))

    def test_report_replays_third_member_and_rejects_a_self_consistent_omission(self):
        inputs = replace(self.inputs, top_bindings=(*self.inputs.top_bindings,
            binding(BoundaryRole.TOP, "third-top", 102)))
        cross = fit_template_cross(inputs)
        proof = self.calibrate(cross=cross, cross_input=inputs)
        self.assertEqual(len(proof.member_observation_pairs), 3)
        lane = dict(complete_height_calibration=typed_read_model(proof),
            source_scan_geometry=typed_read_model(proof.source_geometry),
            phase_competition=typed_read_model(self.phase), cross_competition=typed_read_model(cross),
            cross_registration_work=typed_read_model(self.work), cross_input=typed_read_model(inputs),
            observations={"raw_top_bottom_lines": []})
        _validate_complete_height_provenance(lane, lane)
        forged = deepcopy(lane)
        forged["complete_height_calibration"] = typed_read_model(self.calibrate())
        with self.assertRaisesRegex(ValueError, "full physical competition"):
            _validate_complete_height_provenance(forged, forged)
        altered = deepcopy(lane)
        altered["complete_height_calibration"]["member_height_intervals_px"][0]["maximum"] += 1
        with self.assertRaises(ValueError):
            _validate_complete_height_provenance(altered, altered)
        deleted = deepcopy(lane)
        deleted["complete_height_calibration"] = None
        with self.assertRaisesRegex(ValueError, "calibration proof"):
            _validate_complete_height_provenance(deleted, deleted)


if __name__ == "__main__":
    unittest.main()
