from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.output_fixture_support import _lane, native_output
from tools.tests.template_test_support import (
    phase_edge, phase_sequence_measurement, placement_compose, placement_cross, placement_direction,
    placement_sequence, placement_template,
)
from x5crop.domain import EvidenceState, FiniteInterval
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_common_source_size import (
    CommonSourceSizeGap, prove_common_source_size,
)
from x5crop.detection.photo_geometry.template_cross import calibrate_source_frame_height
from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis, assess_direct_role_binding_authority,
)
from x5crop.detection.photo_geometry.template_family_membership import MembershipState
from x5crop.detection.photo_geometry.template_frame_width import (
    complete_frame_width_observations, independent_frame_width_pairs,
)
from x5crop.detection.photo_geometry.template_output import common_phase_output_footprint
from x5crop.detection.photo_geometry.template_output import output_footprint_from_template_placement
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_phase_output import PhaseScopeOutputProof


class CommonSourceSizeContractTest(unittest.TestCase):
    def _problem(self, second_width=FiniteInterval(99, 102)):
        template = placement_template(3)
        sequence = placement_sequence(template)
        cross = replace(placement_cross(template, direction=placement_direction()),
                        height_compatibility_px=FiniteInterval.exact(240))
        first = placement_compose(template, sequence, cross, frame_spec=FramePhysicalSpec(10.0, 24.0, None))
        initial = SourceScanGeometry.create(first.frame_spec,
            width_scale_px_per_mm=first.source_scan_geometry.width_state.scale_authority,
            height_scale_px_per_mm=first.source_scan_geometry.height_state.scale_authority)
        observations = tuple(phase_edge(binding.observation_id, binding.canonical_position_px)
                             for binding in sequence.role_bindings)
        direct = assess_direct_role_binding_authority(sequence, observations, (),
            (phase_sequence_measurement("common-size", FiniteInterval(0, 500)),))
        phase = SimpleNamespace(best=sequence, direct_role_binding_authority=direct)
        contexts, placements = [], []
        for index, extent in enumerate((FiniteInterval(98, 101), second_width)):
            placement = first
            competition = SimpleNamespace(status=CrossFitStatus.RESOLVED, best=placement.cross_fit)
            measured = calibrate_source_frame_height(initial, competition)
            source = SourceScanGeometry.from_axis_states(initial.frame_spec,
                initial.width_state.intersect_observed_extent(extent,
                    observation_ids=tuple(item.observation_id for item in observations)), measured.height_state)
            placement = replace(placement, placement_id=f"common-size:{index}", source_scan_geometry=source)
            placements.append(placement)
            contexts.append(SimpleNamespace(source_scan_geometry=source, competition=competition,
                membership_projection_complete=True, local_refinements_closed=True,
                membership_state=MembershipState.COMPLETE, membership_scope_states=(MembershipState.COMPLETE,)))
        keys = (("scope", 0), ("scope", 1))
        return initial, keys, tuple(p.placement_id for p in placements), (phase, phase), tuple(contexts), observations, tuple(placements)

    def test_common_measurement_keeps_different_conditional_states_and_native_outputs(self):
        initial, keys, ids, phases, contexts, observations, placements = self._problem()
        proof = prove_common_source_size(initial, keys, ids, phases, contexts, observations)
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        self.assertEqual(len(proof.width_pairs), 3)
        self.assertTrue(independent_frame_width_pairs(proof.width_pairs))
        self.assertAlmostEqual(proof.source_geometry.fixed_output_size.frame_width_px, 100)
        native = tuple(native_output(p) for p in placements)
        self.assertNotEqual(native[0].fixed_size, native[1].fixed_size)
        common = common_phase_output_footprint(placements, native, source_size_proof=proof)
        self.assertEqual(common.members, native)
        self.assertEqual(common.source_size_proof, proof)
        self.assertEqual(common.fixed_size, proof.source_geometry.fixed_output_size)
        self.assertTrue(common.budget_supported)
        with self.assertRaisesRegex(ValueError, "member set"):
            common_phase_output_footprint(tuple(reversed(placements)), tuple(reversed(native)), source_size_proof=proof)

    def test_independent_representative_conflict_is_not_replaced_by_interval_intersection(self):
        initial, keys, ids, phases, contexts, observations, _ = self._problem(FiniteInterval(99.5, 99.9))
        proof = prove_common_source_size(initial, keys, ids, phases, contexts, observations)
        self.assertIsNone(proof.source_geometry)
        self.assertIn(CommonSourceSizeGap.CONDITIONAL_SIZE_CONFLICT, proof.gaps)
        self.assertEqual(len(proof.width_pairs), 3)

    def test_scope_cannot_drop_a_slot_or_borrow_another_scope_size_proof(self):
        initial, keys, ids, phases, contexts, observations, placements = self._problem()
        proof = prove_common_source_size(initial, keys, ids, phases, contexts, observations)
        outputs = tuple(common_phase_output_footprint(placements,
            tuple(output_footprint_from_template_placement(p, project_format_placement(p),
                lane=_lane(), lane_ordinal=slot, layout="horizontal") for p in placements),
            source_size_proof=proof) for slot in (1, 2, 3))
        scope = PhaseScopeOutputProof("scope", 3, proof, outputs, None, proof.work_units)
        self.assertEqual(scope.state, EvidenceState.SUPPORTED)
        with self.assertRaisesRegex(ValueError, "named evidence"):
            replace(scope, common_outputs=outputs[:1])
        foreign = replace(proof, member_keys=(("other", 0), ("other", 1)))
        borrowed = replace(outputs[0], source_size_proof=foreign)
        with self.assertRaisesRegex(ValueError, "named evidence"):
            replace(scope, common_outputs=(borrowed, *outputs[1:]))

    def test_missing_third_member_and_incomplete_cross_cannot_borrow_evidence(self):
        initial, keys, ids, phases, contexts, observations, _ = self._problem()
        proof = prove_common_source_size(initial, (*keys, ("scope", 2)), (*ids, None),
                                        (*phases, None), (*contexts, None), observations)
        self.assertEqual(len(proof.member_keys), 3)
        self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)
        self.assertIn(CommonSourceSizeGap.MEMBER_EVIDENCE_UNAVAILABLE, proof.gaps)
        contexts[1].membership_projection_complete = False
        incomplete = prove_common_source_size(initial, keys, ids, phases, contexts, observations)
        self.assertIn(CommonSourceSizeGap.INDEPENDENT_HEIGHT_PAIR_UNAVAILABLE, incomplete.gaps)

    def test_native_measurements_cannot_be_deleted_or_replaced_in_a_supported_proof(self):
        initial, keys, ids, phases, contexts, observations, _ = self._problem()
        proof = prove_common_source_size(initial, keys, ids, phases, contexts, observations)
        with self.assertRaisesRegex(ValueError, "independent native"):
            replace(proof, width_pairs=proof.width_pairs[:1])
        with self.assertRaisesRegex(ValueError, "native measurements"):
            replace(proof, height_pair=replace(proof.height_pair, height_px=FiniteInterval.exact(239)))
        with self.assertRaisesRegex(ValueError, "complete named"):
            replace(proof, member_keys=keys[:1])

    def test_contact_coordinate_grant_is_not_an_independent_width_measurement(self):
        initial, _, _, phases, _, observations, _ = self._problem()
        phase = phases[0]
        fact = phase.direct_role_binding_authority.facts[1]
        contact = replace(fact, bases=(DirectRoleAuthorityBasis.SHARED_CONTACT_EDGE,))
        self.assertTrue(contact.has_unconditional_coordinate_authority)
        self.assertFalse(contact.has_topology_independent_coordinate_authority)
        changed = replace(phase.direct_role_binding_authority,
                          facts=(phase.direct_role_binding_authority.facts[0], contact,
                                 *phase.direct_role_binding_authority.facts[2:]))
        measured, _ = complete_frame_width_observations(SimpleNamespace(best=phase.best,
            direct_role_binding_authority=changed), observations, initial.width_state.extent_projection_px())
        self.assertEqual(tuple(ordinal for ordinal, _ in measured), (2, 3))
        first, second = (pair for _, pair in measured)
        duplicate = replace(second, start_evidence_group_id=first.end_evidence_group_id)
        self.assertFalse(independent_frame_width_pairs((first, duplicate)))
        same_observation = replace(second, start_observation_id=first.end_observation_id)
        self.assertFalse(independent_frame_width_pairs((first, same_observation)))


if __name__ == "__main__":
    unittest.main()
