"""Common-output authority must cover every H interpretation before selection."""

from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.template_test_support import phase_edge, phase_template, placement_compose
from tools.tests.test_common_h_output_contract import registration
from tools.tests.test_common_output_contract import translated_h
from tools.tests.test_template_cross_contract import aspect_input, binding, _supported_aspect_ratio
from tools.tests.test_template_family_membership_contract import _problem
from tools.tests.test_template_output_contract import _lane, _placement, _selected_output_gate_fact
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.photo_geometry.content_veto_model import (
    ContentVetoAssessment, ContentVetoFact, ContentVetoReason,
)
from x5crop.detection.photo_geometry.line_observations import (
    PhotoBoundaryObservation, RobustLineFitReceipt, SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.template_common_output import (
    assess_common_h_output_authority, common_h_fit_members, materialize_common_h_output,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus
from x5crop.detection.photo_geometry.template_cross_support import SupportFitStatus
from x5crop.detection.photo_geometry.template_family_membership import (
    MembershipState, enumerate_membership_scope,
)
from x5crop.detection.photo_geometry.template_output import common_direct_use_budget_assessment
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_registration import membership_projection_coverage
from x5crop.detection.photo_geometry.template_selection import (
    select_lane_template_placement, select_template_source,
)


def _case(*, support_pair=False, aspect_height=None):
    spec = phase_template(1)
    phase = fit_template_phase((phase_edge("start", 40), phase_edge("end", 140)), spec)
    if support_pair:
        tops = (binding(BoundaryRole.TOP, "top", 100),)
        bottoms = tuple(binding(BoundaryRole.BOTTOM, f"bottom:{i}", 350 + i) for i in range(2))
        tops = tuple(replace(b, trace_position_intervals_px=(b.full_interval_px,) * 3) for b in tops)
        bottoms = tuple(replace(b, trace_position_intervals_px=(b.full_interval_px,) * 3) for b in bottoms)
    else:
        tops = tuple(binding(BoundaryRole.TOP, f"top:{i}", 100 + i) for i in range(2))
        bottoms = (binding(BoundaryRole.BOTTOM, "bottom", 340),)
    inputs = aspect_input(
        template=spec, fixed_height_px=FiniteInterval(230, 260), canonical_fixed_height_px=240,
        top_bindings=tops, bottom_bindings=bottoms,
    )
    if aspect_height is not None:
        inputs = replace(inputs, aperture_aspect_ratio_authority=_supported_aspect_ratio(aspect_height))
    cross = fit_template_cross(inputs)
    members, mapping = common_h_fit_members(cross, registration())
    placements = tuple(placement_compose(
        spec, phase.best, fit, frame_spec=FramePhysicalSpec(10.0, 25.0 if support_pair else 24.0, 2.0),
    ) for fit in members)
    common = materialize_common_h_output(placements, mapping, lane=_lane(), layout="horizontal")
    if common.failure is not None:
        raise AssertionError(common.failure)
    return phase, cross, inputs, common


def _authority(case, *, work=None, coverage=()):
    phase, cross, inputs, common = case
    return assess_common_h_output_authority(
        common, phase=phase, cross=cross, registration=work or registration(),
        membership_coverage=coverage, cross_input=inputs,
    )


def _select(case, authority, content):
    phase, cross, _inputs, common = case
    return select_lane_template_placement(
        lane_id=common.lane_id, best=common.placements[0], runner_up=common.placements[1],
        phase=phase, cross=cross, content_assessment=content,
        common_h_output=common, common_h_authority=authority,
    )


def _clear_content(common):
    return ContentVetoAssessment("common-content", common.placement_id, ())


def _observation(identity, transitions):
    return PhotoBoundaryObservation(
        observation_id=ObservationId(identity), role=BoundaryRole.TOP,
        line=SourceCoordinateLine(0, 1, 100, FiniteInterval(0, 100), BoundaryAxis.X),
        offset_interval_px=FiniteInterval.exact(100),
        fit_residual_px=0, angle_interval_degrees=FiniteInterval.exact(0),
        trace_support_count=len(transitions), queried_trace_count=len(transitions),
        independent_support_region_count=2, continuous_support_fraction=1,
        transition_ids=tuple(map(ObservationId, transitions)),
        fit_receipt=RobustLineFitReceipt("scipy_least_squares_huber", True, 1, 1, 0, 0),
        left_background_preference_fraction=1,
    )


class CommonHSelectionContractTest(unittest.TestCase):
    def test_complete_set_selects_only_common_identity_and_preserves_unresolved_cross(self):
        case = _case()
        phase, cross, _inputs, common = case
        authority = _authority(case)
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        selected = _select(case, authority, _clear_content(common))
        self.assertEqual(selected.selected_placement_id, common.placement_id)
        self.assertIs(selected.selected_output, common)
        self.assertNotIn(common.placement_id, authority.member_placement_ids)
        self.assertEqual(cross.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(cross.winner_basis)
        for member in common.placements:
            native = select_lane_template_placement(
                lane_id=common.lane_id, best=member, runner_up=None,
                phase=phase, cross=cross, content_assessment=None,
            )
            self.assertIsNone(native.selected_placement_id)
        self.assertEqual(tuple(m.envelope.placement_id for m in common.output_footprints[0].members),
                         authority.member_placement_ids)

    def test_one_conflicting_member_cannot_borrow_other_members_ratio_proof(self):
        case = _case(aspect_height=FiniteInterval(239.5, 240.5))
        authority = _authority(case)
        self.assertEqual(sum(a.blocks_cross_resolution for a in authority.aperture_aspect_ratio_authorities), 1)
        self.assertEqual(authority.failure.gap, GateGap.APERTURE_ASPECT_RATIO_DIRECT_CONFLICT)
        selected = _select(case, authority, _clear_content(case[3]))
        self.assertIsNone(selected.selected_placement_id)
        self.assertEqual(len(selected.common_h_output.placements), 2)

    def test_common_aperture_cannot_assume_each_members_pair_is_unique(self):
        case = _case(support_pair=True)
        _phase, cross, inputs, common = case
        self.assertEqual(cross.status, CrossFitStatus.UNRESOLVED)
        for bottom in inputs.bottom_bindings:
            singleton = fit_template_cross(replace(inputs, bottom_bindings=(bottom,)))
            self.assertEqual(singleton.best.boundary_use.value, "aperture_pair")
        # A uniquely authorized native aperture keeps its measured H, but
        # removing its competitors does not prove uniqueness in the full set.
        authority = _authority(case)
        self.assertTrue(all(s.status == SupportFitStatus.RESOLVED
                            for s in authority.enclosing_support_competitions))
        self.assertEqual(authority.failure.gap, GateGap.CROSS_AUTHORITY_UNAVAILABLE)
        self.assertIsNone(_select(case, authority, _clear_content(common)).selected_placement_id)

    def test_aggregate_complete_with_unsearched_scope_has_no_coverage_or_winner(self):
        scope = enumerate_membership_scope(**_problem({"A": (0, 10), "B": (20, 30)}, ()))
        self.assertEqual(scope.state, MembershipState.NO_INDEPENDENT_ANCHOR)
        work = replace(registration(), membership=replace(registration().membership, scopes=(scope,)))
        self.assertEqual(work.membership.state, MembershipState.COMPLETE)
        coverage = membership_projection_coverage(work.membership, (), ())
        self.assertIsNone(coverage)
        case = _case()
        authority = _authority(case, work=work, coverage=coverage)
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(_select(case, authority, _clear_content(case[3])).selected_placement_id)

    def test_unmaterialized_maximal_union_cannot_disappear_from_coverage(self):
        scope = enumerate_membership_scope(**_problem({"A": (0, 10), "B": (20, 30)}, {"A"}))
        self.assertEqual(scope.maximal_member_groups, ((ObservationId("A"), ObservationId("B")),))
        work = replace(registration(), membership=replace(registration().membership, scopes=(scope,)))
        atoms = (_observation("A", ("A:0", "A:10")), _observation("B", ("B:20", "B:30")))
        # A numerical failure leaves the original atoms, but no final union line.
        atom_bindings = tuple(replace(binding(BoundaryRole.TOP, str(atom.observation_id), 100),
                                      observation_id=atom.observation_id) for atom in atoms)
        self.assertIsNone(membership_projection_coverage(work.membership, atoms, atom_bindings))
        case = _case()
        authority = _authority(case, work=work, coverage=None)
        self.assertIsNone(_select(case, authority, _clear_content(case[3])).selected_placement_id)
        union = _observation("union", tuple(t for atom in atoms for t in atom.transition_ids))
        union_binding = replace(binding(BoundaryRole.TOP, "union", 100), observation_id=union.observation_id)
        coverage = membership_projection_coverage(work.membership, (*atoms, union), (union_binding,))
        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0].member_observation_ids, scope.maximal_member_groups[0])
        self.assertEqual(coverage[0].solver_observation_ids, (union.observation_id,))

    def test_common_output_requires_its_own_content_check_and_obeys_veto(self):
        case = _case()
        authority = _authority(case)
        common = case[3]
        with self.assertRaisesRegex(ValueError, "own content check"):
            _select(case, authority, None)
        native_content = ContentVetoAssessment("native-only", common.placements[0].placement_id, ())
        with self.assertRaisesRegex(ValueError, "actual complete output"):
            _select(case, authority, native_content)
        content = ContentVetoAssessment("veto-common", common.placement_id, (
            ContentVetoFact(ContentVetoReason.SLOT_CONTENT_CROPPED_IN, 1, BoundaryRole.TOP,
                            (ObservationId("outside-common-top"),)),
        ))
        selected = _select(case, authority, content)
        self.assertEqual(selected.state, EvidenceState.CONTRADICTED)
        self.assertEqual(selected.failure.gap, GateGap.CONTENT_VETO_REJECTED)
        self.assertIsNone(selected.selected_placement_id)

    def test_source_selection_preserves_common_id_and_shared_native_geometry(self):
        case = _case()
        common = case[3]
        selected = _select(case, _authority(case), _clear_content(common))
        geometry = common.placements[0].source_scan_geometry
        source = select_template_source((selected,), lane_ids=(common.lane_id,), shared_scan_geometry=geometry)
        self.assertEqual(source.selected_placement_ids, (common.placement_id,))
        self.assertEqual(source.shared_scan_geometry, geometry)
        self.assertTrue(all(p.source_scan_geometry == geometry for p in common.placements))

    def test_over_budget_common_retains_every_native_member_and_gate_rejects(self):
        first = _placement()
        placements = (first, translated_h(first, 20))
        common = materialize_common_h_output(placements, ((0, 1), ()), lane=_lane(), layout="horizontal")
        self.assertIsNone(common.failure)
        output = common.output_footprints[0]
        self.assertEqual(tuple(m.envelope.placement_id for m in output.members),
                         tuple(p.placement_id for p in placements))
        self.assertEqual(len(output.member_budgets), 2)
        budget = common_direct_use_budget_assessment(output)
        self.assertEqual(budget.state, EvidenceState.CONTRADICTED)
        # The existing Gate fixture reads these output facts, not placement type.
        gate_output = SimpleNamespace(
            enclosing_support_aperture_risk=None, saturation_facts=output.saturation_facts,
            source_authority_supported=output.source_authority_supported,
        )
        fact = _selected_output_gate_fact(gate_output, budget, code="direct_use_budget")
        self.assertEqual(fact.state, EvidenceState.CONTRADICTED)
        self.assertEqual(fact.gap, GateGap.DIRECT_USE_BUDGET_EXCEEDED)


if __name__ == "__main__":
    unittest.main()
