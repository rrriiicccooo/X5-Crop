"""Only replayable native contradictions release common-output obligations."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.test_template_adjacency_topology_contract import _unbound_separator_case
from tools.tests import test_template_phase_membership_contract as membership_fixture
from tools.tests import test_common_source_size_contract as size_fixture
from tools.tests.output_fixture_support import _lane
from tools.tests.test_native_grid_association_contract import _phase
from tools.tests.template_test_support import phase_edge, phase_separator, phase_sequence_measurement, unavailable_nominal_grid_prior
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
    PhaseMemberOutputWork, PhaseScopeOutputProof, PhaseMemberCrossInput, PhaseMemberCrossCompetition,
    PhaseMemberCrossContext, _build_complete_phase_output, _common_member_windows,
)
from x5crop.detection.photo_geometry.template_aspect_ratio_model import unavailable_aperture_aspect_ratio_authority
from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus, CrossSearchReceipt
from x5crop.detection.photo_geometry.template_family_membership import MembershipState
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_output import output_footprint_from_template_placement, template_direct_use_budget_assessment
from x5crop.detection.photo_geometry.template_placement import resolved_cross_support_domains_px
from x5crop.detection.photo_geometry.template_lattice_authority import assess_global_lattice_authority
from x5crop.detection.photo_geometry.template_outer_frame_authority import assess_outer_frame_observation_authority
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus, TemplatePhaseInput


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
    def test_physical_refutation_can_close_a_previously_blocked_complete_common_window(self):
        initial, _, _, _, _, observations, placements = size_fixture.CommonSourceSizeContractTest()._problem()
        fit = placements[0].sequence_fit
        measurement = phase_sequence_measurement("positive-refutation", FiniteInterval(0., 600.))
        bad_bindings = list(fit.role_bindings)
        bad_bindings[2] = None
        full = list(fit.model_full_role_intervals_px)
        full[1:3] = (FiniteInterval(180., 240.),) * 2
        bad = replace(fit, role_bindings=tuple(bad_bindings), model_full_role_intervals_px=tuple(full))
        bad_edges = list(observations)
        bad_edges[2] = phase_edge(str(observations[2].observation_id), 210.)
        band = phase_separator("positive-counterevidence", bad_edges[1], bad_edges[2], FiniteInterval(9.6, 10.4))
        bad_adjacency = assess_phase_candidate_adjacency(bad, tuple(bad_edges), (band,), (measurement,))
        self.assertEqual(bad_adjacency.state, EvidenceState.CONTRADICTED)
        fixture = membership_fixture.TemplatePhaseMembershipContractTest()
        scope = fixture._scope(fit.template, tuple(fixture._member(value, index)
            for index, value in enumerate((fit, fit, bad))), fixture._receipt(hypotheses=3))
        members = []
        for index, placement in enumerate(placements):
            adjacency = assess_phase_candidate_adjacency(fit, observations, (), (measurement,))
            phase = replace(_phase(fit), direct_role_binding_authority=adjacency.direct_role_authority,
                adjacency_observation_coverage=adjacency.coverage, adjacency_continuity_observations=adjacency.continuity)
            inputs = TemplatePhaseInput(observations=observations, separator_bands=(), template=fit.template,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(fit.template),
                sequence_measurement_sets=(measurement,), scale_px_per_mm=None,
                holder_span_px=scope.holder_span_px, phase_authority_px=None)
            phase = replace(phase, global_lattice_authority=assess_global_lattice_authority(fit, inputs,
                direct_role_authority=adjacency.direct_role_authority),
                outer_frame_observation_authority=assess_outer_frame_observation_authority(fit))
            own_initial = SourceScanGeometry.from_axis_states(initial.frame_spec,
                placement.source_scan_geometry.width_state, initial.height_state)
            cross = placement.cross_fit
            context = PhaseMemberCrossContext(placement.source_scan_geometry, own_initial,
                PhaseMemberCrossInput(fit.template, own_initial.height_state.extent_projection_px(),
                    own_initial.height_state.extent_projection_px().center, (resolved_cross_support_domains_px(fit),)),
                PhaseMemberCrossCompetition(CrossFitStatus.RESOLVED, cross, None,
                    CrossSearchReceipt(1, 1, 2, 1, 0, 1, 512, 512, 4096, 4096), None,
                    unavailable_aperture_aspect_ratio_authority()), MembershipState.COMPLETE,
                (MembershipState.COMPLETE,), True, True, (cross.direct_bindings[0].observation_id,),
                (cross.direct_bindings[1].observation_id,), cross.bound_observation_ids)
            projection = project_format_placement(placement)
            outputs = tuple(output_footprint_from_template_placement(placement, projection, lane=_lane(),
                lane_ordinal=ordinal, layout="horizontal") for ordinal in range(1, fit.template.count + 1))
            budgets = tuple(template_direct_use_budget_assessment(placement, output) for output in outputs)
            admission = assess_phase_member_admission(fit, fit, holder_span_px=scope.holder_span_px, source_domain=None)
            members.append(PhaseMemberOutputProof(scope.scope_id, index, None, None, phase, None, adjacency,
                context, placement, outputs, budgets, (), None, PhaseMemberOutputWork(
                    cross_context_count=1, cross_evaluated_fit_count=1, composition_count=1, projection_count=1,
                    projection_extreme_count=projection.extreme_evaluation_count, output_evaluation_count=3,
                    budget_evaluation_count=3, physical_refutation_check_count=1,
                    admission_check_bound=admission_proof_work_bound(6)), admission=admission))
        bad_admission = assess_phase_member_admission(bad, bad, holder_span_px=scope.holder_span_px, source_domain=None)
        rejected = PhaseMemberOutputProof(scope.scope_id, 2, None, None, _phase(bad), None, bad_adjacency,
            None, None, (), (), (PhaseMemberOutputGap.NATIVE_ADJACENCY_CONTRADICTED,), None,
            PhaseMemberOutputWork(physical_refutation_check_count=2, admission_check_bound=admission_proof_work_bound(6)),
            admission=bad_admission)
        keys = tuple((scope.scope_id, member.record_ordinal) for member in members)
        size = prove_common_source_size(initial, keys, tuple(m.placement.placement_id for m in members),
            tuple(m.phase_assessment for m in members), tuple(m.cross_context for m in members), observations)
        all_members = (*members, rejected)
        self.assertFalse(_common_member_windows(all_members, size, 1_000_000)[0])
        outputs, failure, spent, overflow = _common_member_windows(tuple(members), size, 1_000_000)
        self.assertIsNone(failure)
        self.assertFalse(overflow)
        self.assertEqual(len(outputs), 3)
        scoped = PhaseScopeOutputProof(scope.scope_id, 3, size, outputs, None, size.work_units + spent,
                                      ((scope.scope_id, 2),))
        complete = CompletePhaseOutputProof((scope,), all_members, outputs, None, size.work_units + spent, 0, False,
            common_work_units=size.work_units + spent, source_size_proof=size, scope_outputs=(scoped,))
        self.assertEqual(complete.state, EvidenceState.SUPPORTED)
        self.assertEqual(len(complete.members), 3)
        self.assertEqual(complete.common_member_keys, keys)
        lane = SimpleNamespace(
            phase_competition=SimpleNamespace(status=PhaseFitStatus.UNRESOLVED, competition_scopes=(scope,)),
            phase_input=SimpleNamespace(source_domain=None, observations=observations,
                separator_bands=(band,), sequence_measurement_sets=(measurement,)),
            source_scan_geometry=initial, coarse_support=SimpleNamespace(enclosing_side_facts=()), lane=_lane())
        preparation = SimpleNamespace(reserve_bytes=lambda facts: 0, reserved_bytes=0,
            retained_bytes=0, lookup_count=0, preparation_count=0)
        # Reuse the independently reconstructed witnesses above; run the actual
        # complete-ledger partition, common-size and common-window owners.
        with patch("x5crop.detection.photo_geometry.template_phase_output.assess_phase_member_output",
                   side_effect=all_members):
            built = _build_complete_phase_output(lane, retained_review_bytes=0,
                preparation=preparation, direct_preparation=preparation)
        self.assertEqual(built.state, EvidenceState.SUPPORTED)
        self.assertEqual(len(built.members), 3)
        self.assertEqual(built.common_member_keys, keys)
        self.assertEqual(built.refuted_member_keys, ((scope.scope_id, 2),))
        self.assertEqual(len(built.common_outputs), 3)
        self.assertEqual(len(built.scope_outputs[0].common_outputs), 3)

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
