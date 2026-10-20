"""Counterexamples for complete membership and independent proof replay."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.regression.phase_output_validation import assert_replayed_facts
from tools.tests import test_template_phase_membership_contract as membership_fixture
from tools.tests.template_test_support import placement_sequence, placement_template
from x5crop.domain import EvidenceState
from x5crop.run_local_identity import run_local_id, source_identity_scope
from x5crop.detection.photo_geometry.template_phase_output import (
    CompletePhaseOutputProof, PhaseMemberOutputProof, PhaseMemberOutputGap, PhaseMemberOutputWork,
    _member_registration_ids,
    _build_complete_phase_output,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.domain import PositiveInterval
from x5crop.formats import FramePhysicalSpec


class CompletePhaseOutputContractTest(unittest.TestCase):
    def test_exhausted_complete_proof_keeps_all_keys_without_reconstructing_common_size(self):
        fit = placement_sequence(placement_template(3))
        fixture = membership_fixture.TemplatePhaseMembershipContractTest()
        scope = fixture._scope(fit.template, tuple(fixture._member(fit, index) for index in range(3)),
                               fixture._receipt(hypotheses=3))
        scale = PositiveInterval.exact(10.0)
        source = SourceScanGeometry.create(FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=scale, height_scale_px_per_mm=scale)
        lane = SimpleNamespace(phase_competition=SimpleNamespace(status=PhaseFitStatus.BOUND_EXCEEDED,
            competition_scopes=(scope,)), phase_input=SimpleNamespace(source_domain=None, observations=()),
            source_scan_geometry=source, coarse_support=SimpleNamespace(enclosing_side_facts=()),
            lane=SimpleNamespace(scan_canvas=SimpleNamespace(axis_scales=SimpleNamespace(
                width_axis_px_per_mm=scale, height_axis_px_per_mm=scale))))
        raw = SimpleNamespace(reserve_bytes=lambda facts: 0, reserved_bytes=0, retained_bytes=0,
                              lookup_count=0, preparation_count=0)
        with patch("x5crop.detection.photo_geometry.template_phase_output.prove_common_source_size",
                   side_effect=AssertionError("raw reconstruction ran after exhaustion")):
            proof = _build_complete_phase_output(lane, retained_review_bytes=0,
                preparation=raw, direct_preparation=raw)
        self.assertTrue(proof.bound_exceeded)
        self.assertEqual(len(proof.source_size_proof.member_keys), 3)
        self.assertEqual(proof.source_size_proof.work_units, 0)
        self.assertFalse(proof.common_outputs)

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
        with self.assertRaisesRegex(ValueError, "retain its own prerequisites"):
            replace(members[0], gaps=(PhaseMemberOutputGap.OUTPUT_PREREQUISITE_UNAVAILABLE,))

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

    def test_member_registration_order_survives_new_line_ordinal_changes(self):
        def line(identity, transition):
            return SimpleNamespace(observation_id=identity, role=BoundaryRole.TOP,
                                   transition_ids=(transition,))
        native = line("format-role-bound-line:11", "transition:a")
        left = _member_registration_ids((line("format-role-bound-line:12", "transition:b"), native))
        right = _member_registration_ids((native, line("format-role-bound-line:105", "transition:b")))
        assert_replayed_facts({"registration_observation_ids": list(left)},
                              {"registration_observation_ids": list(right)},
                              protected_native_ids={native.observation_id})
        with self.assertRaisesRegex(ValueError, "physical facts changed"):
            assert_replayed_facts({"registration_observation_ids": list(left)},
                                  {"registration_observation_ids": list(reversed(right))},
                                  protected_native_ids={native.observation_id})
