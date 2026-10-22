"""Only replayable native contradictions release common-output obligations."""

from dataclasses import replace
import unittest

from tools.tests.test_template_adjacency_topology_contract import _unbound_separator_case
from tools.tests import test_template_phase_membership_contract as membership_fixture
from tools.tests.test_native_grid_association_contract import _phase
from tools.tests.template_test_support import phase_sequence_measurement
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_adjacency_topology import assess_phase_candidate_adjacency
from x5crop.detection.photo_geometry.template_common_source_size import CommonSourceSizeGap, prove_common_source_size
from x5crop.detection.photo_geometry.template_member_refutation import phase_member_physical_refutation
from x5crop.detection.photo_geometry.template_phase_admission import assess_phase_member_admission, admission_proof_work_bound
from x5crop.detection.photo_geometry.template_native_grid_association import (
    NativeGridAssociationProof, NativeGridBoundaryBasis, NativeGridBoundarySource, NativeGridGapFact,
)
from x5crop.detection.photo_geometry.template_phase_output import (
    CompletePhaseOutputProof, PhaseMemberDisposition, PhaseMemberOutputGap, PhaseMemberOutputProof,
    PhaseMemberOutputWork, PhaseScopeOutputProof,
)


def _grid(gap=FiniteInterval(-8., -4.), *, authorized=True, feasible=True):
    end = NativeGridBoundarySource(1, NativeGridBoundaryBasis.NATIVE, 1,
        ObservationId("end"), FiniteInterval(10., 12.), authorized, False)
    start = NativeGridBoundarySource(2, NativeGridBoundaryBasis.NATIVE, 2,
        ObservationId("start"), FiniteInterval(4., 6.), True, False)
    fact = NativeGridGapFact(1, end, start, gap if feasible else None,
        -6. if gap is None else gap.center, feasible)
    return NativeGridAssociationProof("a" * 64, (fact,), 3, 4, 2)


def _refuted_member(scope_id="scope", ordinal=0):
    fit, edges, band, _, _ = _unbound_separator_case()
    measurement = phase_sequence_measurement("refutation", FiniteInterval(0., 600.))
    adjacency = assess_phase_candidate_adjacency(fit, edges, (band,), (measurement,))
    admission = assess_phase_member_admission(fit, fit, holder_span_px=FiniteInterval(0., 500.), source_domain=None)
    return PhaseMemberOutputProof(scope_id, ordinal, None, None, _phase(fit), None, adjacency,
        None, None, (), (), (PhaseMemberOutputGap.NATIVE_ADJACENCY_CONTRADICTED,), None,
        PhaseMemberOutputWork(physical_refutation_check_count=2,
            admission_check_bound=admission_proof_work_bound(len(fit.role_bindings))), admission=admission)


def _unknown_member(scope_id, ordinal, gap=PhaseMemberOutputGap.PROJECTION_FAILED):
    return PhaseMemberOutputProof(scope_id, ordinal, None, None, None, None, None, None, None,
        (), (), (gap,), None, PhaseMemberOutputWork())


class PhaseMemberRefutationContractTest(unittest.TestCase):
    def test_missing_qualification_and_failure_labels_do_not_exclude_a_member(self):
        for gap in (PhaseMemberOutputGap.HOLDER_ADMISSION_UNAVAILABLE,
                    PhaseMemberOutputGap.PROJECTION_FAILED,
                    PhaseMemberOutputGap.RESIDUAL_INCOMPATIBLE,
                    PhaseMemberOutputGap.OUTPUT_BUDGET_UNAVAILABLE,
                    PhaseMemberOutputGap.NATIVE_ADJACENCY_CONTRADICTED):
            proof = _unknown_member("scope", 0, gap)
            self.assertIsNone(proof.physical_refutation)
            self.assertEqual(proof.disposition, PhaseMemberDisposition.UNRESOLVED)

    def test_native_refutation_keeps_the_native_witness_and_original_gaps(self):
        member = _refuted_member()
        self.assertEqual(member.disposition, PhaseMemberDisposition.PHYSICALLY_REFUTED)
        self.assertEqual(member.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(member.physical_refutation.registered_partner_conflicts,
                         member.adjacency.registered_role_associations)
        self.assertEqual(member.gaps, (PhaseMemberOutputGap.NATIVE_ADJACENCY_CONTRADICTED,))
        with self.assertRaisesRegex(ValueError, "own final phase"):
            replace(member, phase_assessment=None)
        with self.assertRaisesRegex(ValueError, "refutation work"):
            replace(member, work=replace(member.work, physical_refutation_check_count=0))
        with self.assertRaisesRegex(ValueError, "producer identity"):
            replace(member, admission=None, work=replace(member.work, admission_check_bound=0))

    def test_only_a_complete_authorized_negative_or_infeasible_grid_fact_refutes(self):
        self.assertIsNotNone(phase_member_physical_refutation(None, _grid()))
        self.assertIsNotNone(phase_member_physical_refutation(None, _grid(None, feasible=False)))
        self.assertIsNone(phase_member_physical_refutation(None, _grid(FiniteInterval(-1., 1.))))
        self.assertIsNone(phase_member_physical_refutation(None, _grid(authorized=False)))
        self.assertIsNone(phase_member_physical_refutation(None, None))

    def test_complete_partition_releases_only_the_proved_refutation(self):
        seed = _refuted_member()
        fit = seed.phase_assessment.best
        fixture = membership_fixture.TemplatePhaseMembershipContractTest()
        scope = fixture._scope(fit.template, tuple(fixture._member(fit, index) for index in range(3)),
                               replace(fixture._receipt(hypotheses=3), role_count=len(fit.role_bindings)))
        refuted = replace(seed, scope_id=scope.scope_id)
        members = (refuted, _unknown_member(scope.scope_id, 1), _unknown_member(scope.scope_id, 2))
        scale = PositiveInterval.exact(10.)
        initial = SourceScanGeometry.create(FramePhysicalSpec(36., 24., 2.),
            width_scale_px_per_mm=scale, height_scale_px_per_mm=scale)
        keys = ((scope.scope_id, 1), (scope.scope_id, 2))
        size = prove_common_source_size(initial, keys, (None, None), (None, None), (None, None), ())
        scoped = PhaseScopeOutputProof(scope.scope_id, fit.template.count, size, (), "unknown members", size.work_units,
                                      ((scope.scope_id, 0),))
        complete = CompletePhaseOutputProof((scope,), members, (), "unknown members", size.work_units,
            0, False, source_size_proof=size, scope_outputs=(scoped,))
        self.assertEqual(complete.refuted_member_keys, ((scope.scope_id, 0),))
        self.assertEqual(complete.common_member_keys, keys)
        self.assertEqual(len(complete.members), 3)
        self.assertEqual(complete.state, EvidenceState.UNAVAILABLE)
        with self.assertRaisesRegex(ValueError, "source size omitted"):
            replace(complete, source_size_proof=replace(size, member_keys=keys[:1], placement_ids=(None,),
                                                      conditional_extents=(None,)))
        with self.assertRaisesRegex(ValueError, "scope common window omitted"):
            replace(complete, scope_outputs=(replace(scoped, refuted_member_keys=()),))
        with self.assertRaisesRegex(ValueError, "omitted or changed"):
            replace(complete, members=members[1:])

    def test_empty_remainder_cannot_vacuously_prove_a_common_window(self):
        scale = PositiveInterval.exact(10.)
        initial = SourceScanGeometry.create(FramePhysicalSpec(36., 24., 2.),
            width_scale_px_per_mm=scale, height_scale_px_per_mm=scale)
        proof = prove_common_source_size(initial, (), (), (), (), ())
        self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(proof.gaps, (CommonSourceSizeGap.EMPTY_MEMBER_SET,))
        self.assertIsNone(proof.source_geometry)
        self.assertEqual(proof.work_units, 0)

    def test_foreign_refutation_cannot_be_attached_to_a_producer_with_another_binding(self):
        member = _refuted_member()
        foreign_fit, _, _, _, _ = _unbound_separator_case(1)
        fixture = membership_fixture.TemplatePhaseMembershipContractTest()
        scope = fixture._scope(foreign_fit.template, (fixture._member(foreign_fit, 0),),
            replace(fixture._receipt(hypotheses=1), role_count=len(foreign_fit.role_bindings)))
        member = replace(member, scope_id=scope.scope_id)
        with self.assertRaisesRegex(ValueError, "admission borrowed another producer"):
            CompletePhaseOutputProof((scope,), (member,), (), "refuted", 0, 0, False)
