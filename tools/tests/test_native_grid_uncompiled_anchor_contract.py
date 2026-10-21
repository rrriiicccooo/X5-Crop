"""Missing nominal state must retain its original coordinate obligations."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.test_native_grid_association_contract import _base_phase, _phase
from tools.tests.template_test_support import phase_template, placement_sequence
from x5crop.detection.photo_geometry import template_native_grid_association as native
from x5crop.detection.photo_geometry.template_direct_role_authority import DirectRoleAuthorityBasis
from x5crop.detection.photo_geometry.template_model import SequenceBindingUse
from x5crop.domain import EvidenceState, ObservationId


def uncompiled_phase():
    return _phase(placement_sequence(phase_template(2), missing=(2, 3)), direct_roles=(0, 1))


def replace_anchor_fact(phase, **changes):
    authority = phase.direct_role_binding_authority
    fact = replace(authority.facts[0], **changes)
    facts = (fact, *authority.facts[1:])
    unsupported = tuple(f.role_index for f in facts if f.state != EvidenceState.SUPPORTED)
    return replace(phase, direct_role_binding_authority=replace(authority, facts=facts,
        unsupported_role_indices=unsupported,
        state=EvidenceState.UNAVAILABLE if unsupported else EvidenceState.SUPPORTED,
        reason="original anchor has no independent coordinate proof" if unsupported else None))


class NativeGridUncompiledAnchorContractTests(unittest.TestCase):
    def proof_without_lp(self, phase):
        with patch.object(native, "linprog", side_effect=AssertionError("uncompiled Grid cannot run LP")):
            proof = native.assess_native_grid_association(phase)
        self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(proof.grid_authority_failure, "nominal_grid_state_missing")
        self.assertEqual(proof.lp_solve_count, 0)
        self.assertTrue(all(f.joint_system_feasible is None for f in proof.facts))
        return proof

    def test_available_anchor_facts_do_not_invent_a_compiled_grid(self):
        phase = uncompiled_phase()
        original = phase.best
        proof = self.proof_without_lp(phase)
        self.assertEqual(proof.uncompiled_grid_anchor_role_indices, (0, 1))
        self.assertEqual(proof.unqualified_grid_anchor_role_indices, ())
        self.assertEqual(proof.unqualified_native_role_indices, ())
        self.assertIs(phase.best, original)
        self.assertIsNone(phase.best.calibrated_nominal_grid_fit_state)

    def test_unavailable_original_anchor_is_not_hidden_by_missing_state(self):
        phase = replace_anchor_fact(uncompiled_phase(), bases=(), state=EvidenceState.UNAVAILABLE,
                                    independent_support_region_count=2)
        proof = self.proof_without_lp(phase)
        self.assertEqual(proof.uncompiled_grid_anchor_role_indices, (0, 1))
        self.assertEqual(proof.unqualified_grid_anchor_role_indices, (0,))
        self.assertEqual(proof.unqualified_native_role_indices, (0,))
        self.assertTrue(proof.facts[0].end.coordinate_authorized)
        self.assertFalse(proof.facts[0].next_start.coordinate_authorized)

    def test_absent_original_anchor_fact_remains_unqualified(self):
        phase = uncompiled_phase()
        phase = replace(phase, direct_role_binding_authority=replace(
            phase.direct_role_binding_authority, facts=phase.direct_role_binding_authority.facts[1:]))
        proof = self.proof_without_lp(phase)
        self.assertEqual(proof.unqualified_grid_anchor_role_indices, (0,))

    def test_partial_height_fact_cannot_close_an_uncompiled_anchor(self):
        phase = replace_anchor_fact(uncompiled_phase(),
            bases=(DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,),
            independent_support_region_count=2, trace_coordinates_px=(10, 20))
        proof = self.proof_without_lp(phase)
        self.assertEqual(proof.unqualified_grid_anchor_role_indices, (0,))

    def test_foreign_observation_fact_cannot_hide_the_original_anchor(self):
        phase = replace_anchor_fact(uncompiled_phase(), observation_id=ObservationId("foreign:edge"))
        proof = self.proof_without_lp(phase)
        self.assertEqual(proof.unqualified_grid_anchor_role_indices, (0,))

    def test_local_coordinate_gap_is_not_an_original_anchor_obligation(self):
        phase = uncompiled_phase()
        fit = replace(phase.best, role_bindings=(phase.best.role_bindings[0],
            replace(phase.best.role_bindings[1], use=SequenceBindingUse.LOCAL_REFINEMENT), None, None),
            phase_support_coverage=1.0)
        phase = replace(phase, best=fit, direct_role_binding_authority=replace(
            phase.direct_role_binding_authority, facts=phase.direct_role_binding_authority.facts[:1]))
        proof = self.proof_without_lp(phase)
        self.assertEqual(proof.uncompiled_grid_anchor_role_indices, (0,))
        self.assertEqual(proof.unqualified_grid_anchor_role_indices, ())
        self.assertEqual(proof.unqualified_native_role_indices, (1,))

    def test_compiled_grid_keeps_its_original_projection_and_has_no_pending_anchors(self):
        phase = _base_phase()
        proof = native.assess_native_grid_association(phase)
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        self.assertEqual(proof.lp_solve_count, 2)
        self.assertEqual(proof.uncompiled_grid_anchor_role_indices, ())
        with self.assertRaises(ValueError):
            replace(proof, uncompiled_grid_anchor_role_indices=(0,))

    def test_uncompiled_ledger_rejects_malformed_or_borrowed_role_lists(self):
        proof = self.proof_without_lp(replace_anchor_fact(uncompiled_phase(),
            bases=(), state=EvidenceState.UNAVAILABLE, independent_support_region_count=2))
        for value in ((1, 0), (0, 0), (True,), (-1,)):
            with self.subTest(indices=value), self.assertRaises(ValueError):
                replace(proof, uncompiled_grid_anchor_role_indices=value)
        with self.assertRaises(ValueError):
            replace(proof, unqualified_native_role_indices=())


if __name__ == "__main__":
    unittest.main()
