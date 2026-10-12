"""Common-output authority must cover every H interpretation before selection."""

from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_template,
    placement_compose,
)
from tools.tests.cross_fixture_support import (
    _problem,
    aspect_input,
    binding,
    _supported_aspect_ratio,
)
from tools.tests.output_fixture_support import (
    _authority,
    _case,
    _clear_content,
    _lane,
    _observation,
    _placement,
    _select,
    _selected_output_gate_fact,
    registration,
    translated_h,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.photo_geometry.content_veto_model import (
    ContentVetoAssessment,
    ContentVetoFact,
    ContentVetoReason,
)
from x5crop.detection.photo_geometry.line_observations import (
    PhotoBoundaryObservation,
    RobustLineFitReceipt,
    SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.template_common_output import (
    assess_common_h_output_authority,
    common_h_fit_members,
    materialize_common_h_output,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus
from x5crop.detection.photo_geometry.template_cross_support import SupportFitStatus
from x5crop.detection.photo_geometry.template_family_membership import (
    MembershipState,
    enumerate_membership_scope,
)
from x5crop.detection.photo_geometry.template_output import common_direct_use_budget_assessment
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_registration import membership_projection_coverage
from x5crop.detection.photo_geometry.template_selection import (
    select_lane_template_placement,
    select_template_source,
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
        placements = (first, translated_h(first, 30))
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
