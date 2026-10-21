from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import phase_template, placement_sequence
from tools.tests.test_native_grid_association_contract import (
    _partial_native_phase,
    _phase,
)
from x5crop.detection.photo_geometry import template_native_grid_association as native
from x5crop.detection.photo_geometry.template_model import (
    ContactRelation,
    OverlapRelation,
    SeparatorRelation,
    SeparatorRelationKind,
    SequenceBindingUse,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval


def _local_cross_zero_phase():
    """One authorized phase anchor plus one independently authorized local edge."""
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
        template=replace(
            fit.template,
            frame_width_px=PositiveInterval(50.0, 150.0),
        ),
        role_bindings=(fit.role_bindings[0], local, None, None),
        phase_support_coverage=1.0,
    )
    return _phase(fit, anchors=(0,), direct_roles=(0, 1))


def _measured_native_target_phase(*, measured: bool):
    """A local END followed by a missing Frame, with an optional prior separator."""
    fit = placement_sequence(phase_template(4), missing=(4, 5))
    bindings = list(fit.role_bindings)
    for index in (2, 3):
        binding = bindings[index]
        assert binding is not None
        bindings[index] = replace(
            binding,
            use=SequenceBindingUse.LOCAL_REFINEMENT,
            fit_position_interval_px=FiniteInterval(
                binding.canonical_position_px - 40.0,
                binding.canonical_position_px + 40.0,
            ),
            full_position_interval_px=FiniteInterval(
                binding.canonical_position_px - 40.0,
                binding.canonical_position_px + 40.0,
            ),
        )
    relations = ()
    if measured:
        end = bindings[1]
        next_start = bindings[2]
        assert end is not None and next_start is not None
        relations = (
            SeparatorRelation(
                relation_ordinal=1,
                kind=SeparatorRelationKind.NORMAL,
                delta_interval_px=FiniteInterval.exact(0.0),
                canonical_delta_px=0.0,
                separator_band_observation_id=ObservationId("separator:one"),
                end_edge_observation_id=end.observation_id,
                next_start_edge_observation_id=next_start.observation_id,
                signed_gap_interval_px=FiniteInterval.exact(20.0),
                canonical_signed_gap_px=20.0,
            ),
        )
    fit = replace(
        fit,
        template=replace(
            fit.template,
            frame_width_px=PositiveInterval(80.0, 120.0),
        ),
        role_bindings=tuple(bindings),
        adjacency_relations=relations,
        phase_support_coverage=3.0,
    )
    return _phase(
        fit,
        anchors=(0, 1, 6, 7),
        direct_roles=(0, 1, 2, 3, 6, 7),
    )


def _contact_shared_native_phase():
    """A typed Contact relation whose shared edge appears in two role slots."""
    fit = placement_sequence(phase_template(4), missing=(4, 5))
    bindings = list(fit.role_bindings)
    positions = (100.0, 200.0, 200.0, 300.0, 320.0, 420.0, 440.0, 540.0)
    shared = ObservationId("contact:shared")
    original = bindings[1]
    assert original is not None
    shared_binding = replace(
        original,
        use=SequenceBindingUse.LOCAL_REFINEMENT,
        observation_id=shared,
        evidence_group_id=shared,
        canonical_position_px=200.0,
        fit_position_interval_px=FiniteInterval.exact(200.0),
        full_position_interval_px=FiniteInterval(180.0, 220.0),
    )
    # SequenceFit requires the exact same typed binding for a shared Contact edge.
    bindings[1] = shared_binding
    bindings[2] = shared_binding
    for index in (3, 6, 7):
        binding = bindings[index]
        assert binding is not None
        bindings[index] = replace(
            binding,
            use=(
                SequenceBindingUse.LOCAL_REFINEMENT
                if index == 3
                else binding.use
            ),
            canonical_position_px=positions[index],
            fit_position_interval_px=FiniteInterval.exact(positions[index]),
            full_position_interval_px=FiniteInterval(
                positions[index] - 20.0,
                positions[index] + 20.0,
            ),
        )
    contact = ContactRelation(
        relation_ordinal=1,
        contact_observation_id=ObservationId("contact:observation"),
        physical_edge_id=shared,
        shared_edge_observation_id=shared,
        delta_interval_px=FiniteInterval.exact(-20.0),
        canonical_delta_px=-20.0,
        supporting_observation_ids=(shared,),
    )
    intervals = tuple(FiniteInterval.exact(value) for value in positions)
    full_intervals = tuple(
        FiniteInterval(value - 20.0, value + 20.0)
        if index in (1, 2, 3)
        else FiniteInterval.exact(value)
        for index, value in enumerate(positions)
    )
    fit = replace(
        fit,
        template=replace(
            fit.template,
            frame_width_px=PositiveInterval(80.0, 120.0),
        ),
        model_role_positions_px=positions,
        model_role_intervals_px=intervals,
        model_full_role_intervals_px=full_intervals,
        role_bindings=tuple(bindings),
        adjacency_relations=(contact,),
        phase_support_coverage=2.0,
    )
    return _phase(
        fit,
        anchors=(0, 6, 7),
        direct_roles=(0, 1, 2, 3, 6, 7),
    ), shared


def _overlap_native_phase():
    """A measured negative-gap relation before the native/Grid transition."""
    fit = placement_sequence(phase_template(4), missing=(4, 5))
    bindings = list(fit.role_bindings)
    positions = (100.0, 200.0, 190.0, 290.0, 310.0, 410.0, 430.0, 530.0)
    for index in (2, 3, 6, 7):
        binding = bindings[index]
        assert binding is not None
        bindings[index] = replace(
            binding,
            use=(
                SequenceBindingUse.LOCAL_REFINEMENT
                if index in (2, 3)
                else binding.use
            ),
            canonical_position_px=positions[index],
            fit_position_interval_px=FiniteInterval.exact(positions[index]),
            full_position_interval_px=FiniteInterval(
                positions[index] - 40.0,
                positions[index] + 40.0,
            ),
        )
    overlap = OverlapRelation(
        relation_ordinal=1,
        overlap_observation_id=ObservationId("overlap:one"),
        end_edge_observation_id=bindings[1].observation_id,
        next_start_edge_observation_id=bindings[2].observation_id,
        signed_gap_interval_px=FiniteInterval.exact(-10.0),
        canonical_signed_gap_px=-10.0,
        delta_interval_px=FiniteInterval.exact(-30.0),
        canonical_delta_px=-30.0,
        supporting_observation_ids=(
            bindings[1].observation_id,
            bindings[2].observation_id,
        ),
    )
    intervals = tuple(FiniteInterval.exact(value) for value in positions)
    full_intervals = tuple(
        FiniteInterval(value - 40.0, value + 40.0)
        if index in (2, 3)
        else FiniteInterval.exact(value)
        for index, value in enumerate(positions)
    )
    fit = replace(
        fit,
        template=replace(
            fit.template,
            frame_width_px=PositiveInterval(80.0, 120.0),
        ),
        model_role_positions_px=positions,
        model_role_intervals_px=intervals,
        model_full_role_intervals_px=full_intervals,
        role_bindings=tuple(bindings),
        adjacency_relations=(overlap,),
        phase_support_coverage=3.0,
    )
    return _phase(
        fit,
        anchors=(0, 1, 6, 7),
        direct_roles=(0, 1, 2, 3, 6, 7),
    )


class NativeGridIndependentConstraintsContractTests(unittest.TestCase):
    def test_measured_native_anchor_relation_tightens_target_gap(self) -> None:
        without_measurement = native.assess_native_grid_association(
            _measured_native_target_phase(measured=False)
        )
        with_measurement = native.assess_native_grid_association(
            _measured_native_target_phase(measured=True)
        )
        assert without_measurement is not None
        assert with_measurement is not None
        target_without = without_measurement.facts[0]
        target_with = with_measurement.facts[0]
        self.assertEqual(
            target_without.signed_gap_interval_px,
            FiniteInterval(-20.0, 60.0),
        )
        self.assertEqual(
            target_with.signed_gap_interval_px,
            FiniteInterval(0.0, 40.0),
        )
        self.assertEqual(with_measurement.state, EvidenceState.SUPPORTED)
        self.assertEqual(target_with.end.basis, native.NativeGridBoundaryBasis.NATIVE)
        self.assertEqual(target_with.next_start.basis, native.NativeGridBoundaryBasis.GRID)
        measured = [
            constraint
            for constraint in with_measurement.independent_constraints
            if constraint.kind == native.NativeGridConstraintKind.MEASURED_RELATION
        ]
        self.assertEqual(len(measured), 1)
        self.assertEqual(measured[0].ordinal, 1)
        self.assertEqual(measured[0].signed_span_interval_px, FiniteInterval.exact(20.0))

    def test_local_native_full_interval_keeps_redundant_cross_zero_gap(self) -> None:
        proof = native.assess_native_grid_association(_local_cross_zero_phase())
        assert proof is not None
        fact = proof.facts[0]
        self.assertEqual(fact.end.basis, native.NativeGridBoundaryBasis.NATIVE)
        self.assertEqual(fact.end.native_role_index, 1)
        self.assertEqual(fact.end.native_full_interval_px, FiniteInterval(150.0, 250.0))
        self.assertIn(ObservationId("sequence:1"), proof.native_variable_observation_ids)
        self.assertEqual(fact.signed_gap_interval_px, FiniteInterval(-30.0, 70.0))
        self.assertTrue(fact.signed_gap_interval_px.contains(0.0))
        self.assertEqual(fact.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            tuple(c.signed_span_interval_px for c in proof.independent_constraints),
            (FiniteInterval(50.0, 150.0),),
        )

    def test_physical_frame_constraint_uses_template_width_not_source_width(self) -> None:
        phase, source_width = _partial_native_phase()
        fit = replace(
            phase.best,
            template=replace(
                phase.best.template,
                frame_width_px=PositiveInterval(80.0, 120.0),
            ),
        )
        phase = replace(phase, best=fit)
        proof = native.assess_native_grid_association(
            phase,
            source_frame_width_authority=source_width,
        )
        assert proof is not None
        physical = [
            constraint
            for constraint in proof.independent_constraints
            if constraint.kind == native.NativeGridConstraintKind.NATIVE_FRAME_WIDTH
            and constraint.ordinal == 3
        ]
        self.assertEqual(len(physical), 1)
        self.assertEqual(physical[0].signed_span_interval_px, FiniteInterval(80.0, 120.0))
        self.assertEqual(source_width.width_px, FiniteInterval.exact(100.0))
        self.assertNotEqual(physical[0].signed_span_interval_px, source_width.width_px)

    def test_unauthorized_native_consumes_no_variable_or_lp_work(self) -> None:
        phase = _local_cross_zero_phase()
        phase = replace(
            phase,
            direct_role_binding_authority=replace(
                phase.direct_role_binding_authority,
                facts=tuple(
                    fact
                    for fact in phase.direct_role_binding_authority.facts
                    if fact.role_index != 1
                ),
            ),
        )
        proof = native.assess_native_grid_association(phase)
        assert proof is not None
        self.assertEqual(proof.native_variable_observation_ids, ())
        self.assertEqual(proof.independent_constraints, ())
        self.assertEqual(proof.variable_count, 0)
        self.assertEqual(proof.inequality_count, 0)
        self.assertEqual(proof.lp_solve_count, 0)
        self.assertFalse(proof.facts[0].end.coordinate_authorized)
        self.assertIsNone(proof.facts[0].signed_gap_interval_px)
        self.assertIsNone(proof.facts[0].joint_system_feasible)

    def test_measured_relation_requires_both_authorized_original_bindings(self) -> None:
        phase = _measured_native_target_phase(measured=True)
        authority = phase.direct_role_binding_authority
        assert authority is not None
        # The registered separator remains in the fit, but its START binding
        # loses unconditional coordinate authority.  It must not become an
        # independent physical inequality through the other endpoint.
        phase = replace(
            phase,
            direct_role_binding_authority=replace(
                authority,
                facts=tuple(fact for fact in authority.facts if fact.role_index != 2),
            ),
        )
        proof = native.assess_native_grid_association(phase)
        assert proof is not None
        self.assertFalse(any(
            constraint.kind == native.NativeGridConstraintKind.MEASURED_RELATION
            for constraint in proof.independent_constraints
        ))
        self.assertNotIn(ObservationId("sequence:2"), proof.native_variable_observation_ids)
        self.assertEqual(proof.facts[0].signed_gap_interval_px, FiniteInterval(-20.0, 60.0))

    def test_contact_shared_observation_is_one_native_variable(self) -> None:
        phase, shared = _contact_shared_native_phase()
        proof = native.assess_native_grid_association(phase)
        assert proof is not None
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)
        self.assertEqual(proof.native_variable_observation_ids.count(shared), 1)
        self.assertEqual(
            len(proof.native_variable_observation_ids),
            len(set(proof.native_variable_observation_ids)),
        )
        contact_constraints = [
            constraint
            for constraint in proof.independent_constraints
            if constraint.kind == native.NativeGridConstraintKind.MEASURED_RELATION
        ]
        self.assertEqual(len(contact_constraints), 1)
        self.assertEqual(contact_constraints[0].observation_ids, (shared, shared))
        self.assertEqual(contact_constraints[0].signed_span_interval_px, FiniteInterval.exact(0.0))

    def test_overlap_constraint_preserves_a_negative_signed_span(self) -> None:
        proof = native.assess_native_grid_association(_overlap_native_phase())
        assert proof is not None
        overlap_constraints = [
            constraint
            for constraint in proof.independent_constraints
            if constraint.kind == native.NativeGridConstraintKind.MEASURED_RELATION
        ]
        self.assertEqual(len(overlap_constraints), 1)
        self.assertEqual(
            overlap_constraints[0].signed_span_interval_px,
            FiniteInterval.exact(-10.0),
        )
        self.assertLess(overlap_constraints[0].signed_span_interval_px.maximum, 0.0)
        self.assertEqual(proof.state, EvidenceState.SUPPORTED)

    def test_unmeasured_adjacency_has_no_explicit_normal_gap_constraint(self) -> None:
        proof = native.assess_native_grid_association(
            _measured_native_target_phase(measured=False)
        )
        assert proof is not None
        self.assertTrue(all(
            constraint.kind == native.NativeGridConstraintKind.NATIVE_FRAME_WIDTH
            for constraint in proof.independent_constraints
        ))
        self.assertFalse(any(
            constraint.kind == native.NativeGridConstraintKind.MEASURED_RELATION
            for constraint in proof.independent_constraints
        ))
        self.assertLess(proof.facts[0].signed_gap_interval_px.minimum, 0.0)

    def test_impossible_native_frame_is_recorded_as_qualified_infeasible(self) -> None:
        phase = _local_cross_zero_phase()
        # The typed binding constructor correctly requires full >= fit.  Widen
        # the valid fixture first, then place its consumed native interval
        # wholly beyond the original physical Frame W to exercise real LP
        # infeasibility without mocking the solver.
        binding = phase.best.role_bindings[1]
        assert binding is not None
        object.__setattr__(binding, "full_position_interval_px", FiniteInterval(251.0, 260.0))
        proof = native.assess_native_grid_association(phase)
        assert proof is not None
        self.assertEqual(proof.state, EvidenceState.CONTRADICTED)
        self.assertEqual(proof.lp_solve_count, 1)
        self.assertEqual(proof.facts[0].joint_system_feasible, False)
        self.assertIsNone(proof.facts[0].signed_gap_interval_px)
        self.assertEqual(proof.facts[0].state, EvidenceState.CONTRADICTED)

    def test_fingerprint_rejects_consumed_native_interval_or_relation_change(self) -> None:
        local_phase = _local_cross_zero_phase()
        local_proof = native.assess_native_grid_association(local_phase)
        assert local_proof is not None
        local_binding = local_phase.best.role_bindings[1]
        assert local_binding is not None
        changed_binding = replace(
            local_binding,
            full_position_interval_px=FiniteInterval(145.0, 250.0),
        )
        changed_fit = replace(
            local_phase.best,
            role_bindings=(
                local_phase.best.role_bindings[0],
                changed_binding,
                None,
                None,
            ),
        )
        self.assertFalse(local_proof.matches_inputs(replace(local_phase, best=changed_fit), None))

        relation_phase = _measured_native_target_phase(measured=True)
        relation_proof = native.assess_native_grid_association(relation_phase)
        assert relation_proof is not None
        relation = relation_phase.best.adjacency_relations[0]
        changed_relation = replace(
            relation,
            signed_gap_interval_px=FiniteInterval(19.0, 21.0),
        )
        changed_relation_fit = replace(
            relation_phase.best,
            adjacency_relations=(changed_relation,),
        )
        self.assertFalse(
            relation_proof.matches_inputs(
                replace(relation_phase, best=changed_relation_fit),
                None,
            )
        )


if __name__ == "__main__":
    unittest.main()
