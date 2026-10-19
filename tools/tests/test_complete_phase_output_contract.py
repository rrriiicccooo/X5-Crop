"""Counterexamples for complete membership and independent proof replay."""

from dataclasses import replace
import unittest

from tools.regression.phase_output_validation import assert_replayed_facts
from tools.tests import test_template_phase_membership_contract as membership_fixture
from tools.tests.template_test_support import placement_sequence, placement_template
from x5crop.domain import EvidenceState
from x5crop.run_local_identity import run_local_id, source_identity_scope
from x5crop.detection.photo_geometry.template_phase_output import (
    CompletePhaseOutputProof, PhaseMemberOutputProof, PhaseMemberOutputGap, PhaseMemberOutputWork,
)


class CompletePhaseOutputContractTest(unittest.TestCase):
    def test_third_unqualified_member_cannot_disappear_from_complete_proof(self):
        fit = placement_sequence(placement_template(3))
        fixture = membership_fixture.TemplatePhaseMembershipContractTest()
        scope = fixture._scope(fit.template, tuple(fixture._member(fit, index) for index in range(3)),
                               fixture._receipt(hypotheses=3))
        members = tuple(PhaseMemberOutputProof(scope.scope_id, index,
            None, None, None, None, None, None, None, (), (),
            (PhaseMemberOutputGap.PROJECTION_NOT_EVALUATED,), None, PhaseMemberOutputWork())
            for index in range(3))
        complete = CompletePhaseOutputProof((scope,), members, (), "missing qualification", 0, 0, False)
        self.assertEqual(complete.state, EvidenceState.UNAVAILABLE)
        with self.assertRaisesRegex(ValueError, "omitted or changed"):
            replace(complete, members=members[:2])
        with self.assertRaisesRegex(ValueError, "complete member set"):
            replace(complete, common_outputs=(object(),))

    def test_replay_preserves_registered_native_ids_geometry_and_identity_graph(self):
        expected = {"id": "source-scan-geometry:1", "reference": "source-scan-geometry:1",
                    "native_id": "native-photo-line:7", "interval": [10.0, 12.0]}
        assert_replayed_facts(expected, dict(expected, id="source-scan-geometry:4",
                                            reference="source-scan-geometry:4"))
        for actual in (dict(expected, reference="source-scan-geometry:4"),
                       dict(expected, native_id="native-photo-line:8"),
                       dict(expected, interval=[10.0, 11.0])):
            with self.subTest(actual=actual), self.assertRaisesRegex(ValueError, "physical facts changed"):
                assert_replayed_facts(expected, actual)

    def test_work_receipt_does_not_allow_a_second_member_search(self):
        with self.assertRaisesRegex(ValueError, "single reconstruction"):
            PhaseMemberOutputWork(late_projection_count=2)
        with self.assertRaisesRegex(ValueError, "nonnegative integers"):
            PhaseMemberOutputWork(cross_context_count=True)

    def test_replay_restores_registered_line_names_and_reserves_existing_ordinals(self):
        with source_identity_scope(reserved_ids=("format-role-bound-line:7",),
                registered_keys=(("format-role-bound-line", ("top", "native:1"), "format-role-bound-line:3"),)):
            self.assertEqual(run_local_id("format-role-bound-line", "top", "native:1"), "format-role-bound-line:3")
            self.assertEqual(run_local_id("format-role-bound-line", "bottom", "native:2"), "format-role-bound-line:8")
        with source_identity_scope():
            self.assertEqual(run_local_id("format-role-bound-line", "top", "native:1"), "format-role-bound-line:1")

    def test_distinct_physical_keys_cannot_alias_one_registered_identity(self):
        with self.assertRaisesRegex(ValueError, "aliases different physical keys"):
            with source_identity_scope(registered_keys=(("p", ("a",), "p:3"), ("p", ("b",), "p:3"))):
                pass

    def test_membership_proposal_observation_ids_are_native_facts(self):
        with self.assertRaisesRegex(ValueError, "physical facts changed"):
            assert_replayed_facts({"observation_id": "membership-proposal-line:1"},
                                  {"observation_id": "membership-proposal-line:2"})
