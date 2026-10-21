from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from scipy.optimize import linprog

from tools.tests.template_test_support import phase_template, placement_sequence
from x5crop.detection.photo_geometry import template_feasible_geometry
from x5crop.detection.photo_geometry import template_native_grid_association as native
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_feasible_geometry import (
    sequence_feasible_system,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    SourceFrameWidthAuthority,
    SourceFrameWidthAuthorityFailureKind,
    SourceFrameWidthAuthorityPlacementScope,
)
from x5crop.detection.photo_geometry.template_model import (
    FrameWidthInferenceAssessment,
    LatticeParameterFitBasis,
    SequenceBindingUse,
    SourceFrameWidthAuthorityBasis,
    TemplateSearchReceipt,
)
from x5crop.detection.photo_geometry.template_nominal_grid_model import (
    CalibratedNominalGridEvidence,
    CalibratedNominalGridFitState,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval


def _direct_authority(fit, role_indices: tuple[int, ...]):
    facts = []
    for role_index in role_indices:
        binding = fit.role_bindings[role_index]
        if binding is None:
            continue
        facts.append(
            DirectRoleAuthorityFact(
                role_index=role_index,
                lane_ordinal=role_index // 2 + 1,
                role=(
                    BoundaryRole.START
                    if role_index % 2 == 0
                    else BoundaryRole.END
                ),
                observation_id=binding.observation_id,
                evidence_group_id=binding.evidence_group_id,
                independent_support_region_count=3,
                bases=(DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,),
                blocking_material_conflict_ids=(),
                state=EvidenceState.SUPPORTED,
            )
        )
    if not facts:
        return None
    return DirectRoleBindingAuthority(
        state=EvidenceState.SUPPORTED,
        facts=tuple(facts),
        unsupported_role_indices=(),
        reason=None,
    )


def _nominal_state(
    fit,
    anchors: tuple[int, ...],
    *,
    prior_id: str = "native-grid-test-prior",
    scale: PositiveInterval | None = None,
    frame_width_mm: FiniteInterval | None = None,
    pitch_mm: FiniteInterval | None = None,
    canonical_scale: float | None = None,
):
    scale = PositiveInterval.exact(1.0) if scale is None else scale
    frame_width_mm = (
        FiniteInterval.exact(100.0)
        if frame_width_mm is None
        else frame_width_mm
    )
    pitch_mm = (
        FiniteInterval.exact(120.0) if pitch_mm is None else pitch_mm
    )
    canonical_scale = (
        (scale.minimum + scale.maximum) / 2.0
        if canonical_scale is None
        else canonical_scale
    )
    identities = tuple(fit.role_bindings[index].observation_id for index in anchors)
    state = CalibratedNominalGridFitState(
        prior_id=prior_id,
        scale_px_per_mm=scale,
        frame_width_mm=frame_width_mm,
        pitch_mm=pitch_mm,
        canonical_scale_px_per_mm=canonical_scale,
        phase_anchor_role_indices=anchors,
        phase_anchor_observation_ids=identities,
        retained_direct_constraint_rank=min(3, len(anchors)),
    )
    unobserved_frames = tuple(
        ordinal + 1
        for ordinal in range(fit.template.count)
        if fit.role_bindings[2 * ordinal] is None
        and fit.role_bindings[2 * ordinal + 1] is None
    )
    evidence = CalibratedNominalGridEvidence(
        evidence_id=f"{prior_id}:evidence",
        state=EvidenceState.SUPPORTED,
        prior_id=prior_id,
        phase_anchor_role_indices=anchors,
        phase_anchor_observation_ids=identities,
        inferred_adjacency_ordinals=tuple(range(1, fit.template.count)),
        unobserved_frame_ordinals=unobserved_frames,
        covering_query_ids=(f"query:{prior_id}",),
        failure_kind=None,
        reason=None,
    )
    return state, evidence


def _phase(
    fit,
    *,
    anchors: tuple[int, ...] = (),
    direct_roles: tuple[int, ...] = (),
    prior_id: str = "native-grid-test-prior",
    scale: PositiveInterval | None = None,
    frame_width_mm: FiniteInterval | None = None,
    pitch_mm: FiniteInterval | None = None,
    canonical_scale: float | None = None,
):
    if anchors:
        state, evidence = _nominal_state(
            fit,
            anchors,
            prior_id=prior_id,
            scale=scale,
            frame_width_mm=frame_width_mm,
            pitch_mm=pitch_mm,
            canonical_scale=canonical_scale,
        )
        fit = replace(
            fit,
            lattice_parameter_fit_basis=LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
            calibrated_nominal_grid_fit_state=state,
        )
    else:
        evidence = None
    receipt = TemplateSearchReceipt(
        observation_count=len(fit.bound_observation_ids),
        role_count=len(fit.role_bindings),
        phase_lookup_count=0,
        role_binding_count=0,
        adjacency_relation_evaluation_count=0,
        local_refinement_lookup_count=0,
        local_refinement_binding_count=0,
        phase_hypothesis_count=0,
        phase_offset_lookup_count=0,
        direct_observation_count=len(fit.bound_observation_ids),
        inferred_role_count=len(fit.unbound_role_indices),
    )
    return PhaseFitResult(
        template=fit.template,
        best=fit,
        runner_up=None,
        status=PhaseFitStatus.UNRESOLVED,
        ambiguity_reason="native/Grid contract fixture remains unresolved",
        receipt=receipt,
        registered_direct_observation_ids=fit.bound_observation_ids,
        failure_kind=PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE,
        direct_role_binding_authority=_direct_authority(fit, direct_roles),
        calibrated_nominal_grid_evidence=evidence,
    )


def _base_phase(*, native_authorized=True, grid_authorized=True):
    fit = placement_sequence(phase_template(2), missing=(2, 3))
    return _phase(
        fit,
        anchors=(0, 1) if grid_authorized else (),
        direct_roles=(0, 1) if native_authorized else (),
    )


def _reverse_phase():
    template = replace(phase_template(2), direction=-1)
    original = placement_sequence(phase_template(2), missing=(0, 1))
    positions = (-100.0, -200.0, -220.0, -320.0)
    intervals = tuple(FiniteInterval.exact(value) for value in positions)
    bindings = tuple(
        None
        if binding is None
        else replace(
            binding,
            canonical_position_px=positions[index],
            fit_position_interval_px=intervals[index],
            full_position_interval_px=intervals[index],
        )
        for index, binding in enumerate(original.role_bindings)
    )
    lattice = replace(
        original.phase_lattice_fit,
        authority=template.phase_lattice_authority,
        direction=-1,
        canonical_absolute_phase_px=-100.0,
        absolute_phase_interval_px=FiniteInterval.exact(-100.0),
    )
    fit = replace(
        original,
        template=template,
        phase_lattice_fit=lattice,
        model_role_positions_px=positions,
        model_role_intervals_px=intervals,
        model_full_role_intervals_px=intervals,
        role_bindings=bindings,
    )
    return _phase(fit, anchors=(2, 3), direct_roles=(2, 3))


def _two_relation_phase():
    fit = placement_sequence(phase_template(3), missing=(2, 3))
    return _phase(
        fit,
        anchors=(0, 1, 4, 5),
        direct_roles=(0, 1, 4, 5),
    )


def _scaled_phase():
    original_template = phase_template(2)
    lattice_authority = replace(
        original_template.phase_lattice_authority,
        period_px=FiniteInterval.exact(121.6),
    )
    template = replace(
        original_template,
        template_id="native-grid-scale-proof",
        frame_width_px=FiniteInterval(110.0, 121.0),
        pitch_px=FiniteInterval(119.0, 123.0),
        phase_lattice_authority=lattice_authority,
        nominal_gap_px=FiniteInterval(0.0, 20.0),
    )
    original = placement_sequence(original_template, missing=(2, 3))
    positions = (100.0, 215.2, 221.6, 336.8)
    intervals = (
        FiniteInterval.exact(100.0),
        FiniteInterval(110.0, 230.0),
        FiniteInterval(200.0, 240.0),
        FiniteInterval(300.0, 360.0),
    )
    bindings = list(original.role_bindings)
    for index in (0, 1):
        binding = bindings[index]
        assert binding is not None
        bindings[index] = replace(
            binding,
            canonical_position_px=positions[index],
            fit_position_interval_px=intervals[index],
            full_position_interval_px=intervals[index],
        )
    lattice = replace(
        original.phase_lattice_fit,
        authority=lattice_authority,
        canonical_period_px=121.6,
        cycle_phase_interval_px=FiniteInterval.exact(100.0),
        canonical_cycle_phase_px=100.0,
        absolute_phase_interval_px=FiniteInterval.exact(100.0),
        canonical_absolute_phase_px=100.0,
    )
    pitch = replace(
        original.pitch_fit,
        frame_width_px=template.frame_width_px,
        gap_interval_px=template.gap_prior_px,
        pitch_interval_px=template.pitch_px,
        canonical_frame_width_px=115.2,
        canonical_pitch_px=121.6,
    )
    fit = replace(
        original,
        template=template,
        phase_lattice_fit=lattice,
        pitch_fit=pitch,
        model_role_positions_px=positions,
        model_role_intervals_px=intervals,
        model_full_role_intervals_px=intervals,
        role_bindings=tuple(bindings),
    )
    return _phase(
        fit,
        anchors=(0, 1),
        direct_roles=(0, 1),
        prior_id="native-grid-scale-proof",
        scale=PositiveInterval.exact(3.2),
        frame_width_mm=FiniteInterval.exact(36.0),
        pitch_mm=FiniteInterval.exact(38.0),
        canonical_scale=3.2,
    )


def _partial_native_phase(*, local_parent=False):
    original = placement_sequence(phase_template(3), missing=(1, 2, 3))
    binding = original.role_bindings[0]
    assert binding is not None
    inference = FrameWidthInferenceAssessment(
        state=EvidenceState.SUPPORTED,
        inferred_role_indices=(1,),
        supporting_frame_ordinals=(),
        width_px=PositiveInterval.exact(100.0),
        canonical_width_px=100.0,
        observation_ids=(
            ObservationId("width:one"),
            ObservationId("width:two"),
            ObservationId("width:three"),
        ),
        authority_id="same-width-authority",
        authority_basis=SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE,
        failure_kind=None,
    )
    fit = replace(original, frame_width_inference=inference)
    anchors = (0,)
    if local_parent:
        bindings = list(fit.role_bindings)
        bindings[0] = replace(bindings[0], use=SequenceBindingUse.LOCAL_REFINEMENT)
        fit = replace(fit, role_bindings=tuple(bindings), phase_support_coverage=2.0)
        anchors = (4, 5)
    phase = _phase(fit, anchors=anchors, direct_roles=(0, 4, 5))
    width = SourceFrameWidthAuthority(
        authority_id="same-width-authority",
        state=EvidenceState.SUPPORTED,
        placement_scope=SourceFrameWidthAuthorityPlacementScope.RESOLVED_PLACEMENT,
        placement_integer_slot_offset=fit.phase_lattice_fit.integer_slot_offset,
        placement_phase_anchor_observation_ids=tuple(
            b.observation_id if b is not None and b.use == SequenceBindingUse.PHASE_ANCHOR else None
            for b in fit.role_bindings),
        supporting_role_observation_ids=(
            binding.observation_id,
            None,
            None,
            None,
            fit.role_bindings[4].observation_id,
            fit.role_bindings[5].observation_id,
        ),
        basis=SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE,
        supporting_frame_ordinals=(),
        supporting_constraint_ids=("width:c1", "width:c2", "width:c3"),
        width_px=FiniteInterval.exact(100.0),
        canonical_width_px=100.0,
        observation_ids=(
            binding.observation_id,
            fit.role_bindings[4].observation_id,
            fit.role_bindings[5].observation_id,
        ),
        failure_kind=None,
        reason=None,
    )
    return phase, width


def _failed_width_authority() -> SourceFrameWidthAuthority:
    return SourceFrameWidthAuthority(
        authority_id="foreign-unavailable-width",
        state=EvidenceState.UNAVAILABLE,
        placement_scope=None,
        placement_integer_slot_offset=None,
        placement_phase_anchor_observation_ids=(),
        supporting_role_observation_ids=(),
        basis=None,
        supporting_frame_ordinals=(),
        supporting_constraint_ids=(),
        width_px=None,
        canonical_width_px=None,
        observation_ids=(),
        failure_kind=SourceFrameWidthAuthorityFailureKind.SOURCE_WIDTH_CLOSURE_UNAVAILABLE,
        reason="synthetic unavailable width",
    )


def _typed_source(
    role_index: int,
    basis: native.NativeGridBoundaryBasis,
    *,
    authorized: bool = True,
) -> native.NativeGridBoundarySource:
    if basis == native.NativeGridBoundaryBasis.GRID:
        return native.NativeGridBoundarySource(
            role_index,
            basis,
            None,
            None,
            None,
            authorized,
            False,
        )
    return native.NativeGridBoundarySource(
        role_index,
        basis,
        role_index,
        ObservationId(f"native:{role_index}"),
        FiniteInterval.exact(float(role_index)),
        authorized,
        False,
    )


class NativeGridAssociationContractTests(unittest.TestCase):
    def test_supported_gap_matches_an_independent_lp_oracle(self) -> None:
        phase = _base_phase()
        proof = native.assess_native_grid_association(phase)
        fact = proof.facts[0]
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        self.assertIsNotNone(fact.signed_gap_interval_px)
        self.assertEqual(fact.signed_gap_interval_px, FiniteInterval.exact(20.0))
        self.assertEqual(fact.canonical_signed_gap_px, 20.0)
        self.assertTrue(fact.end.coordinate_authorized)
        self.assertTrue(fact.next_start.coordinate_authorized)

        system, _ = sequence_feasible_system(phase.best)
        objective = np.zeros(len(system.bounds), dtype=np.float64)
        objective[1] = -1.0
        objective[2] = 1.0
        lower = linprog(
            objective,
            A_ub=system.inequalities[0],
            b_ub=system.inequalities[1],
            bounds=system.bounds,
            method="highs",
        )
        upper = linprog(
            -objective,
            A_ub=system.inequalities[0],
            b_ub=system.inequalities[1],
            bounds=system.bounds,
            method="highs",
        )
        self.assertTrue(lower.success and upper.success)
        assert fact.signed_gap_interval_px is not None
        self.assertAlmostEqual(fact.signed_gap_interval_px.minimum, lower.fun)
        self.assertAlmostEqual(fact.signed_gap_interval_px.maximum, -upper.fun)

    def test_unqualified_endpoint_skips_lp_and_keeps_unavailable_geometry(self) -> None:
        cases = (
            _phase(
                placement_sequence(phase_template(2), missing=(2, 3)),
                direct_roles=(0, 1),
            ),
            _phase(
                placement_sequence(phase_template(2), missing=(2, 3)),
                anchors=(0, 1),
            ),
        )
        for phase in cases:
            with self.subTest(phase=phase):
                with patch.object(native, "linprog", wraps=native.linprog) as solver:
                    proof = native.assess_native_grid_association(phase)
                self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)
                self.assertEqual(proof.lp_solve_count, 0)
                self.assertEqual(solver.call_count, 0)
                for fact in proof.facts:
                    self.assertIsNone(fact.signed_gap_interval_px)
                    self.assertIsNone(fact.joint_system_feasible)

    def test_two_authorized_relations_reuse_the_same_lp_objective(self) -> None:
        phase = _two_relation_phase()
        with patch.object(native, "linprog", wraps=native.linprog) as solver:
            proof = native.assess_native_grid_association(phase)
        self.assertEqual(len(proof.facts), 2)
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        self.assertEqual(proof.lp_solve_count, 2)
        self.assertEqual(solver.call_count, 2)
        self.assertLessEqual(proof.lp_solve_count, 2 * len(proof.facts))
        self.assertEqual(
            tuple(fact.signed_gap_interval_px for fact in proof.facts),
            (FiniteInterval.exact(20.0), FiniteInterval.exact(20.0)),
        )

    def test_shared_scale_removes_uncorrelated_cross_zero_gap(self) -> None:
        phase = _scaled_phase()
        proof = native.assess_native_grid_association(phase)
        fact = proof.facts[0]
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        assert fact.signed_gap_interval_px is not None
        self.assertAlmostEqual(fact.signed_gap_interval_px.minimum, 6.4)
        self.assertAlmostEqual(fact.signed_gap_interval_px.maximum, 6.4)
        self.assertGreaterEqual(fact.signed_gap_interval_px.minimum, 0.0)
        # The uncorrelated pixel marginals alone span -2..13.  The actual LP
        # uses the registered W=36s/P=38s state and therefore cannot choose
        # those independent, geometry-inconsistent endpoints.
        self.assertLess(119.0 - 121.0, 0.0)
        self.assertGreater(123.0 - 110.0, 0.0)

    def test_local_native_keeps_full_interval_and_never_becomes_anchor(self) -> None:
        fit = placement_sequence(phase_template(2), missing=(2, 3))
        binding = fit.role_bindings[1]
        assert binding is not None
        local = replace(
            binding,
            use=SequenceBindingUse.LOCAL_REFINEMENT,
            fit_position_interval_px=FiniteInterval.exact(200.0),
            full_position_interval_px=FiniteInterval(150.0, 250.0),
        )
        fit = replace(
            fit,
            role_bindings=(fit.role_bindings[0], local, None, None),
            phase_support_coverage=1.0,
        )
        proof = native.assess_native_grid_association(
            _phase(fit, anchors=(0,), direct_roles=(0, 1))
        )
        fact = proof.facts[0]
        self.assertEqual(fact.end.basis, native.NativeGridBoundaryBasis.NATIVE)
        self.assertEqual(fact.end.native_full_interval_px, FiniteInterval(150.0, 250.0))
        self.assertEqual(fact.signed_gap_interval_px, FiniteInterval(-30.0, 70.0))
        self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)

    def test_partial_height_coordinate_cannot_supply_unconditional_counterevidence(self) -> None:
        phase = _base_phase()
        original = native.assess_native_grid_association(phase)
        authority = phase.direct_role_binding_authority
        facts = tuple(replace(f, bases=(DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,),
                              independent_support_region_count=2, trace_coordinates_px=(0, 10))
                      if f.role_index == 1 else f for f in authority.facts)
        conditional = replace(phase, direct_role_binding_authority=replace(authority, facts=facts))
        with patch.object(native, "linprog", wraps=linprog) as solver:
            proof = native.assess_native_grid_association(conditional)
        self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(proof.facts[0].joint_system_feasible)
        self.assertFalse(proof.facts[0].end.coordinate_authorized)
        self.assertEqual(solver.call_count, 0)
        self.assertFalse(original.matches_inputs(conditional, None))

    def test_grid_checks_partial_height_anchors_away_from_the_actual_gap(self) -> None:
        phase = _base_phase()
        authority = phase.direct_role_binding_authority
        facts = tuple(replace(f, bases=(DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,),
                              independent_support_region_count=2, trace_coordinates_px=(0, 10))
                      if f.role_index == 0 else f for f in authority.facts)
        conditional = replace(phase, direct_role_binding_authority=replace(authority, facts=facts))
        with patch.object(native, "linprog", wraps=linprog) as solver:
            proof = native.assess_native_grid_association(conditional)
        self.assertTrue(proof.facts[0].end.coordinate_authorized)
        self.assertFalse(proof.facts[0].next_start.coordinate_authorized)
        self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(solver.call_count, 0)

    def test_reverse_direction_preserves_signed_positive_gap(self) -> None:
        proof = native.assess_native_grid_association(_reverse_phase())
        fact = proof.facts[0]
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        self.assertEqual(fact.signed_gap_interval_px, FiniteInterval.exact(20.0))
        self.assertEqual(fact.canonical_signed_gap_px, 20.0)
        self.assertEqual(fact.end.basis, native.NativeGridBoundaryBasis.GRID)
        self.assertEqual(fact.next_start.basis, native.NativeGridBoundaryBasis.NATIVE_ANCHOR)

    def test_foreign_common_width_cannot_authorize_an_inferred_native_role(self) -> None:
        phase, width = _partial_native_phase(local_parent=True)
        with patch.object(native, "linprog", wraps=native.linprog) as solver:
            authorized = native.assess_native_grid_association(
                phase,
                source_frame_width_authority=width,
            )
        self.assertEqual(authorized.state, EvidenceState.SUPPORTED)
        self.assertEqual(authorized.facts[0].end.basis, native.NativeGridBoundaryBasis.NATIVE_WIDTH)
        self.assertEqual(authorized.facts[0].signed_gap_interval_px, FiniteInterval.exact(20.0))
        self.assertEqual(solver.call_count, authorized.lp_solve_count)
        self.assertLessEqual(solver.call_count, 2 * len(authorized.facts))

        foreign = replace(width, authority_id="different-width-authority")
        with patch.object(native, "linprog", wraps=native.linprog) as solver:
            rejected = native.assess_native_grid_association(
                phase,
                source_frame_width_authority=foreign,
            )
        self.assertEqual(rejected.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(rejected.facts[0].signed_gap_interval_px)
        self.assertEqual(rejected.lp_solve_count, solver.call_count)
        self.assertLessEqual(solver.call_count, 2)

    def test_existing_grid_anchor_keeps_its_own_width_without_source_width_inference(self) -> None:
        phase, _width = _partial_native_phase()
        phase = replace(phase, best=replace(phase.best, frame_width_inference=None))
        proof = native.assess_native_grid_association(phase)
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        self.assertEqual(proof.facts[0].end.basis, native.NativeGridBoundaryBasis.ANCHOR_GRID_WIDTH)
        self.assertEqual(proof.facts[0].signed_gap_interval_px, FiniteInterval.exact(20.0))

    def test_canonical_negative_or_unenclosed_gap_cannot_use_a_favorable_lp_point(self) -> None:
        fit = placement_sequence(phase_template(2), missing=(2, 3))
        binding = fit.role_bindings[1]
        assert binding is not None
        canonical_negative = replace(
            binding,
            canonical_position_px=250.0,
            fit_position_interval_px=FiniteInterval(200.0, 250.0),
            full_position_interval_px=FiniteInterval(200.0, 250.0),
        )
        changed = replace(
            fit,
            role_bindings=(fit.role_bindings[0], canonical_negative, None, None),
        )
        proof = native.assess_native_grid_association(
            _phase(changed, anchors=(0,), direct_roles=(0, 1))
        )
        self.assertEqual(proof.state, EvidenceState.UNAVAILABLE)
        self.assertLess(proof.facts[0].canonical_signed_gap_px, 0.0)
        self.assertTrue(proof.facts[0].signed_gap_interval_px.contains(0.0))

        end = _typed_source(1, native.NativeGridBoundaryBasis.NATIVE)
        start = _typed_source(2, native.NativeGridBoundaryBasis.GRID)
        outside = native.NativeGridGapFact(
            relation_ordinal=1,
            end=end,
            next_start=start,
            signed_gap_interval_px=FiniteInterval(0.0, 10.0),
            canonical_signed_gap_px=20.0,
            joint_system_feasible=True,
        )
        self.assertEqual(outside.state, EvidenceState.UNAVAILABLE)

    def test_authorized_all_negative_fact_is_counterevidence_but_unqualified_is_unavailable(self) -> None:
        end = _typed_source(1, native.NativeGridBoundaryBasis.NATIVE)
        start = _typed_source(2, native.NativeGridBoundaryBasis.GRID)
        contradicted = native.NativeGridGapFact(
            relation_ordinal=1,
            end=end,
            next_start=start,
            signed_gap_interval_px=FiniteInterval(-30.0, -10.0),
            canonical_signed_gap_px=-20.0,
            joint_system_feasible=True,
        )
        self.assertEqual(contradicted.state, EvidenceState.CONTRADICTED)
        unauthorized = native.NativeGridGapFact(
            relation_ordinal=1,
            end=replace(end, coordinate_authorized=False),
            next_start=start,
            signed_gap_interval_px=FiniteInterval(-30.0, -10.0),
            canonical_signed_gap_px=-20.0,
            joint_system_feasible=True,
        )
        self.assertEqual(unauthorized.state, EvidenceState.UNAVAILABLE)

    def test_no_applicable_normal_relation_returns_none_without_building_lp_system(self) -> None:
        phase = _phase(placement_sequence(phase_template(2)))
        with patch.object(
            template_feasible_geometry,
            "sequence_feasible_system",
            wraps=template_feasible_geometry.sequence_feasible_system,
        ) as feasible:
            self.assertIsNone(native.assess_native_grid_association(phase))
        self.assertEqual(feasible.call_count, 0)

    def test_non_infeasible_solver_failure_is_not_physical_counterevidence(self) -> None:
        phase = _base_phase()
        failure = SimpleNamespace(
            status=4,
            success=False,
            x=None,
            message="synthetic solver failure",
        )
        with patch.object(native, "linprog", return_value=failure):
            with self.assertRaisesRegex(RuntimeError, "solver failed"):
                native.assess_native_grid_association(phase)

    def test_joint_projection_roundoff_hulls_outward_and_rejects_large_inversion(self) -> None:
        for delta in (1.0e-10, 1.0e-4):
            calls = []

            def inverted_extrema(*args, **kwargs):
                result = linprog(*args, **kwargs)
                calls.append(result)
                result.x = result.x.copy()
                result.x[2] += delta if len(calls) == 1 else -delta
                return result

            with self.subTest(delta=delta), patch.object(native, "linprog", side_effect=inverted_extrema):
                if delta > 1.0e-7:
                    with self.assertRaisesRegex(RuntimeError, "extrema disagree"):
                        native.assess_native_grid_association(_base_phase())
                else:
                    proof = native.assess_native_grid_association(_base_phase())
                    interval = proof.facts[0].signed_gap_interval_px
                    self.assertLess(interval.minimum, 20.0)
                    self.assertGreater(interval.maximum, 20.0)

    def test_infeasible_system_is_recorded_without_omitting_the_relation(self) -> None:
        failure = SimpleNamespace(status=2, success=False, x=None, message="infeasible")
        with patch.object(native, "linprog", return_value=failure) as solver:
            proof = native.assess_native_grid_association(_base_phase())
        self.assertEqual(proof.state, EvidenceState.CONTRADICTED)
        self.assertEqual(len(proof.facts), 1)
        self.assertFalse(proof.facts[0].joint_system_feasible)
        self.assertIsNone(proof.facts[0].signed_gap_interval_px)
        self.assertEqual(proof.lp_solve_count, solver.call_count)
        self.assertEqual(solver.call_count, 1)

    def test_feasibility_cannot_change_between_objective_extrema(self) -> None:
        phase = _base_phase()
        system, _ = sequence_feasible_system(phase.best)
        success = linprog(np.zeros(len(system.bounds)), A_ub=system.inequalities[0],
                          b_ub=system.inequalities[1], bounds=system.bounds)
        failure = SimpleNamespace(status=2, success=False, x=None, message="infeasible")
        with patch.object(native, "linprog", side_effect=(success, failure)):
            with self.assertRaisesRegex(RuntimeError, "changed feasibility"):
                native.assess_native_grid_association(phase)

    def test_fingerprint_binds_fit_full_intervals_and_width_identity(self) -> None:
        phase = _base_phase()
        proof = native.assess_native_grid_association(phase)
        self.assertTrue(proof.matches_inputs(phase, None))

        binding = phase.best.role_bindings[1]
        assert binding is not None
        changed_binding = replace(
            binding,
            full_position_interval_px=FiniteInterval(199.0, 201.0),
        )
        changed_fit = replace(
            phase.best,
            role_bindings=(phase.best.role_bindings[0], changed_binding, None, None),
        )
        changed_phase = replace(phase, best=changed_fit)
        self.assertFalse(proof.matches_inputs(changed_phase, None))
        self.assertFalse(proof.matches_inputs(phase, _failed_width_authority()))

    def test_bounds_and_typed_resource_fields_reject_bool_or_invalid_counts(self) -> None:
        self.assertEqual(native.native_grid_work_bound(4), 576)
        self.assertEqual(native.native_grid_bytes_bound(4), 36864)
        for value in (True, 1.0, 0, -2, 3):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    native.native_grid_work_bound(value)
                with self.assertRaises(ValueError):
                    native.native_grid_bytes_bound(value)

        with self.assertRaises(ValueError):
            native.NativeGridBoundarySource(
                role_index=1,
                basis=native.NativeGridBoundaryBasis.GRID,
                native_role_index=None,
                observation_id=None,
                native_full_interval_px=None,
                coordinate_authorized=1,
                shared_width_authorized=False,
            )
        with self.assertRaises(ValueError):
            native.NativeGridGapFact(
                relation_ordinal=1,
                end=_typed_source(1, native.NativeGridBoundaryBasis.NATIVE),
                next_start=_typed_source(2, native.NativeGridBoundaryBasis.GRID),
                signed_gap_interval_px=FiniteInterval.exact(1.0),
                canonical_signed_gap_px=1.0,
                joint_system_feasible=1,
            )


if __name__ == "__main__":
    unittest.main()
