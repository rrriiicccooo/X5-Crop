from __future__ import annotations

from dataclasses import replace
from itertools import permutations
import unittest

from tools.tests.template_test_support import placement_sequence, placement_template
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_native_retention import (
    _deduplicate_classes,
    carry_native_phase_retention,
    select_native_phase_retention,
)
from x5crop.detection.photo_geometry.template_model import LatticeParameterFitBasis, TemplateSearchReceipt
from x5crop.detection.photo_geometry.template_lattice_authority import direct_role_constraint_rank
from x5crop.detection.photo_geometry.template_nominal_grid_model import CalibratedNominalGridFitState
from x5crop.detection.photo_geometry.template_phase_candidate_model import _BoundFit
from x5crop.detection.photo_geometry.template_phase_model import (
    NativeEndpointPhaseDiagnostic,
    NativeEndpointSelectionBasis,
    NativeEndpointGeometryBasis,
    NativePhaseRetention,
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseFitResult,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval


class NativeRetentionContractTests(unittest.TestCase):
    def _grid_fit(self, fit):
        anchors = tuple(i for i, binding in enumerate(fit.role_bindings) if binding is not None)
        return replace(
            fit, lattice_parameter_fit_basis=LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
            calibrated_nominal_grid_fit_state=CalibratedNominalGridFitState(
                prior_id="unit-grid", scale_px_per_mm=PositiveInterval.exact(10.0),
                frame_width_mm=FiniteInterval.exact(10.0), pitch_mm=FiniteInterval.exact(12.0),
                canonical_scale_px_per_mm=10.0, phase_anchor_role_indices=anchors,
                phase_anchor_observation_ids=tuple(fit.role_bindings[i].observation_id for i in anchors),
                retained_direct_constraint_rank=direct_role_constraint_rank(fit, anchors),
            ),
        )

    def _authority(
        self,
        fit,
        *,
        bases=(),
        contradicted: tuple[int, ...] = (),
        intrinsic_roles: tuple[int, ...] | None = None,
    ):
        terminal_indices = tuple(
            index
            for index, binding in enumerate(fit.role_bindings)
            if binding is not None
        )
        facts = []
        for role_index in sorted(set(terminal_indices)):
            binding = fit.role_bindings[role_index]
            if binding is None:
                continue
            role_bases = tuple(bases) or (
                DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
            )
            if intrinsic_roles is not None and role_index not in intrinsic_roles:
                role_bases = (DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,)
            if role_index in contradicted:
                state = EvidenceState.CONTRADICTED
                conflicts = (ObservationId(f"conflict:{role_index}"),)
            else:
                state = EvidenceState.SUPPORTED
                conflicts = ()
            if DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR in role_bases:
                support_region_count = 2
                trace_coordinates = (1, 2)
            else:
                support_region_count = 3
                trace_coordinates = ()
            outer_ids = (
                (ObservationId(f"outer:{role_index}"),)
                if DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY in role_bases
                else ()
            )
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
                    independent_support_region_count=support_region_count,
                    bases=role_bases,
                    blocking_material_conflict_ids=conflicts,
                    state=state,
                    trace_coordinates_px=trace_coordinates,
                    supporting_outer_material_observation_ids=outer_ids,
                )
            )
        state = (
            EvidenceState.CONTRADICTED
            if contradicted
            else EvidenceState.SUPPORTED
        )
        return DirectRoleBindingAuthority(
            state=state,
            facts=tuple(facts),
            unsupported_role_indices=tuple(sorted(contradicted)),
            reason="contradicted" if contradicted else None,
        )

    def _projection(self, authority, *, failed=False):
        if failed:
            outcome = (
                PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION
                if authority.state == EvidenceState.CONTRADICTED
                else PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE
            )
            basis = None
            reason = "preserved failure"
        else:
            outcome = PhaseCandidateProjectionOutcome.UNCHANGED
            basis = PhaseCandidateProjectionBasis.DIRECT_BINDINGS
            reason = None
        return PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=outcome,
            basis=basis,
            projected_out_bindings=(),
            retained_direct_constraint_rank=3,
            reason=reason,
        )

    def _record(
        self, fit, *, output=None, failed=False, bases=(), contradicted=(),
        intrinsic_roles=None,
    ):
        authority = self._authority(
            fit,
            bases=bases,
            contradicted=contradicted,
            intrinsic_roles=intrinsic_roles,
        )
        return (
            _BoundFit(fit, fit.residual_sum_px <= 10.0),
            None
            if failed
            else _BoundFit(
                fit if output is None else output,
                (fit if output is None else output).residual_sum_px <= 10.0,
            ),
            self._projection(authority, failed=failed),
        )

    def _class_records(self, template, residuals=(0.0, 0.0, 0.0, 0.0)):
        last_start = 2 * template.count - 2
        return tuple(
            self._record(
                replace(placement_sequence(template), residual_sum_px=residual),
                intrinsic_roles=(first, last_start + last),
            )
            for (first, last), residual in zip(
                ((0, 0), (0, 1), (1, 0), (1, 1)), residuals,
            )
        )

    def _phase_result(self, fit):
        return PhaseFitResult(
            template=fit.template,
            best=fit,
            runner_up=None,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason="unresolved test placement",
            failure_kind=PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE,
            registered_direct_observation_ids=fit.bound_observation_ids,
            receipt=TemplateSearchReceipt(
                observation_count=len(fit.bound_observation_ids),
                role_count=len(fit.role_bindings),
                phase_lookup_count=0,
                role_binding_count=0,
                adjacency_relation_evaluation_count=0,
                local_refinement_lookup_count=0,
                local_refinement_binding_count=0,
                phase_hypothesis_count=0,
                phase_offset_lookup_count=0,
                direct_observation_count=0,
                inferred_role_count=0,
            ),
        )

    def test_four_classes_preserve_same_fit_with_different_projection_ledgers(self):
        template = placement_template(3)
        records = self._class_records(template)
        retained = select_native_phase_retention(records)
        self.assertEqual(retained.role_class_indices, (0, 1, 2, 3) + (None,) * 8)
        self.assertEqual(len(retained.diagnostics), 4)
        for index, diagnostic in enumerate(retained.diagnostics):
            self.assertEqual(diagnostic.role_class_memberships, (index,))
            self.assertEqual(diagnostic.fit, retained.diagnostics[0].fit)
            self.assertIs(diagnostic.projection, records[index][2])
        self.assertNotEqual(retained.diagnostics[0].projection, retained.diagnostics[1].projection)
        self.assertEqual(retained.class_membership_count, 4)
        self.assertEqual(retained.class_comparison_count, 0)
        self.assertEqual(retained.deduplication_comparison_count, 6)

    def test_one_complete_diagnostic_can_represent_all_four_classes(self):
        fit = placement_sequence(placement_template(3))
        retained = select_native_phase_retention((self._record(fit),))
        self.assertEqual(retained.role_class_indices, (0, 0, 0, 0) + (None,) * 8)
        self.assertEqual(len(retained.diagnostics), 1)
        self.assertEqual(retained.diagnostics[0].role_class_memberships, (0, 1, 2, 3))
        self.assertEqual(retained.class_membership_count, 4)
        self.assertEqual(retained.deduplication_comparison_count, 3)

    def test_deduplication_preserves_residual_and_full_joint_interval_identity(self):
        fit = placement_sequence(placement_template(3))
        diagnostic = select_native_phase_retention((self._record(fit),)).diagnostics[0]
        residual_variant = replace(diagnostic, residual_compatible=False)
        interval_variant = replace(
            diagnostic,
            fit=replace(fit, model_full_role_intervals_px=tuple(
                FiniteInterval(interval.minimum - 1.0, interval.maximum + 1.0)
                for interval in fit.model_full_role_intervals_px
            )),
        )
        variants, mapping, comparisons = _deduplicate_classes((
            diagnostic, residual_variant, interval_variant, diagnostic,
        ) + (None,) * 8)
        self.assertEqual(variants, (diagnostic, residual_variant, interval_variant))
        self.assertEqual(mapping, (0, 1, 2, 0) + (None,) * 8)
        self.assertEqual(comparisons, 4)

    def test_count_one_uses_actual_overlapping_terminal_roles(self):
        fit = placement_sequence(placement_template(1))
        for intrinsic, mapping, classes in (
            ((0,), (0, None, None, None), (0,)),
            ((1,), (None, None, None, 0), (3,)),
            ((0, 1), (0, 0, 0, 0), (0, 1, 2, 3)),
        ):
            with self.subTest(intrinsic=intrinsic):
                retained = select_native_phase_retention((
                    self._record(fit, intrinsic_roles=intrinsic),
                ))
                self.assertEqual(retained.role_class_indices, mapping + (None,) * 8)
                self.assertEqual(len(retained.diagnostics), 1)
                self.assertEqual(retained.diagnostics[0].role_class_memberships, classes)

    def test_partial_class_maps_preserve_first_reference_order(self):
        records = self._class_records(placement_template(3))
        retained = select_native_phase_retention((records[3], records[1]))
        self.assertEqual(retained.role_class_indices, (None, 0, None, 1) + (None,) * 8)
        self.assertIs(retained.diagnostics[0].projection, records[1][2])
        self.assertIs(retained.diagnostics[1].projection, records[3][2])

    def test_outer_class_wins_before_rank_and_intrinsic_rank_reuses_bound_rank(self):
        template = placement_template(3)
        intrinsic_fit = replace(
            placement_sequence(template),
            residual_sum_px=0.0,
            phase_support_coverage=1.0,
        )
        outer_fit = replace(
            placement_sequence(template),
            residual_sum_px=100.0,
            phase_support_coverage=0.1,
        )
        records = (
            self._record(intrinsic_fit),
            self._record(
                outer_fit,
                bases=(
                    DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                    DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,
                ),
            ),
        )
        selected = select_native_phase_retention(records)
        self.assertTrue(selected.diagnostics)
        assert selected.diagnostics[0] is not None
        self.assertIs(selected.diagnostics[0].fit, outer_fit)
        self.assertEqual(
            selected.diagnostics[0].selection_basis,
            NativeEndpointSelectionBasis.OUTER_MATERIAL_TERMINAL,
        )

        lower = replace(placement_sequence(template), residual_sum_px=9.0)
        higher = replace(placement_sequence(template), residual_sum_px=1.0)
        ranked = select_native_phase_retention(
            (self._record(lower), self._record(higher))
        )
        assert ranked.diagnostics[0] is not None
        self.assertIs(ranked.diagnostics[0].fit, higher)

        tie_first = placement_sequence(template)
        tie_second = replace(tie_first)
        tied = select_native_phase_retention(
            (self._record(tie_first), self._record(tie_second))
        )
        assert tied.diagnostics[0] is not None
        self.assertIs(tied.diagnostics[0].fit, tie_first)

    def test_success_uses_existing_output_and_failure_keeps_input_and_ledger(self):
        template = placement_template(3)
        input_fit = replace(placement_sequence(template), residual_sum_px=100.0)
        output_fit = replace(placement_sequence(template), residual_sum_px=0.0)
        successful = select_native_phase_retention(
            (self._record(input_fit, output=output_fit),)
        )
        assert successful.diagnostics[0] is not None
        self.assertIs(successful.diagnostics[0].fit, output_fit)
        self.assertTrue(successful.diagnostics[0].projection.eligible)

        contradicted = self._record(
            input_fit,
            failed=True,
            contradicted=(0,),
        )
        failed = select_native_phase_retention((contradicted,))
        assert failed.diagnostics[0] is not None
        self.assertIs(failed.diagnostics[0].fit, input_fit)
        self.assertIs(failed.diagnostics[0].projection, contradicted[2])
        self.assertEqual(
            failed.diagnostics[0].projection.input_direct_role_authority.state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(
            failed.diagnostics[0].projection.input_direct_role_authority.facts[0].state,
            EvidenceState.CONTRADICTED,
        )

    def test_completed_and_failed_geometries_keep_separate_terminal_classes(self):
        template = placement_template(3)
        projected = replace(
            placement_sequence(template), residual_sum_px=9.0,
            phase_support_coverage=0.1,
        )
        raw = replace(
            placement_sequence(template), residual_sum_px=0.0,
            phase_support_coverage=1.0,
        )
        successful_record = self._record(projected)
        failed_record = self._record(raw, failed=True)
        successful = select_native_phase_retention((successful_record,))
        failed = select_native_phase_retention((failed_record,))
        self.assertGreater(failed.diagnostics[0].rank, successful.diagnostics[0].rank)
        for records in ((failed_record, successful_record),
                        (successful_record, failed_record)):
            selected = select_native_phase_retention(records)
            self.assertIs(selected.diagnostics[0].fit, projected)
            self.assertTrue(selected.diagnostics[0].projection.eligible)
            self.assertIs(selected.diagnostics[1].fit, raw)
            self.assertIs(selected.diagnostics[1].projection, failed_record[2])
            self.assertEqual(selected.role_class_indices, (0,) * 4 + (None,) * 4 + (1,) * 4)
        carried = carry_native_phase_retention(successful, failed)
        self.assertIs(carried.diagnostics[0].fit, projected)
        self.assertIs(carried.diagnostics[1].fit, raw)

        # A distinct outer-material terminal explanation remains represented
        # even when its original projection carries contradictory facts.
        outer_record = self._record(
            raw, failed=True, contradicted=(0,), bases=(
                DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,
            ),
        )
        selected = select_native_phase_retention((successful_record, outer_record))
        self.assertIs(selected.diagnostics[0].fit, projected)
        self.assertIs(selected.diagnostics[1].fit, raw)
        self.assertIs(selected.diagnostics[1].projection, outer_record[2])
        self.assertFalse(selected.diagnostics[1].projection.eligible)

    def test_direct_grid_and_failed_input_cannot_displace_each_other(self):
        direct = placement_sequence(placement_template(3))
        grid = self._grid_fit(placement_sequence(direct.template, missing=(2, 3)))
        records = (self._record(direct), self._record(grid), self._record(direct, failed=True))
        for ordered in permutations(records):
            retained = select_native_phase_retention(ordered)
            self.assertEqual(tuple(d.geometry_basis for d in retained.diagnostics), tuple(NativeEndpointGeometryBasis))
            self.assertEqual(retained.role_class_indices, (0,) * 4 + (1,) * 4 + (2,) * 4)
            self.assertIs(retained.diagnostics[0].fit, direct)
            self.assertIs(retained.diagnostics[1].fit, grid)
            self.assertIs(retained.diagnostics[2].projection, records[2][2])
            self.assertFalse(retained.diagnostics[2].projection.eligible)
        carried = carry_native_phase_retention(
            select_native_phase_retention(records[:1]), select_native_phase_retention(records[1:]),
        )
        self.assertEqual(carried.role_class_indices, (0,) * 4 + (1,) * 4 + (2,) * 4)
        with self.assertRaisesRegex(ValueError, "invented a role class"):
            replace(carried, role_class_indices=(1,) * 4 + (0,) * 4 + (2,) * 4)

    def test_twelve_distinct_representatives_reach_the_exact_fixed_bound(self):
        template = placement_template(3)
        direct = self._class_records(template)
        grid = tuple(self._record(self._grid_fit(record[0].fit), intrinsic_roles=roles)
                     for record, roles in zip(direct, ((0, 4), (0, 5), (1, 4), (1, 5)), strict=True))
        failed = tuple(self._record(record[0].fit, failed=True, intrinsic_roles=roles)
                       for record, roles in zip(direct, ((0, 4), (0, 5), (1, 4), (1, 5)), strict=True))
        retained = select_native_phase_retention((*direct, *grid, *failed))
        self.assertEqual(retained.role_class_indices, tuple(range(12)))
        self.assertEqual(len(retained.diagnostics), 12)
        self.assertEqual(retained.class_membership_count, 12)
        self.assertEqual(retained.deduplication_comparison_count, 66)
        with self.assertRaisesRegex(ValueError, "exceeds twelve"):
            replace(retained, diagnostics=(*retained.diagnostics, retained.diagnostics[0]))
        carried = carry_native_phase_retention(retained, retained)
        self.assertEqual(carried.role_class_indices, tuple(range(12)))
        self.assertEqual(carried.carry_comparison_count, 12)
        self.assertEqual(carried.deduplication_comparison_count, 198)

    def test_output_deleted_or_changed_terminal_binding_cannot_borrow_input_fact(self):
        template = placement_template(3)
        input_fit = placement_sequence(template)
        deleted = placement_sequence(template, missing=(0, 1))
        self.assertFalse(
            select_native_phase_retention(
                (self._record(input_fit, output=deleted),)
            ).diagnostics
        )
        changed_binding = replace(
            input_fit.role_bindings[0],
            observation_id=ObservationId("changed:0"),
            evidence_group_id=ObservationId("changed-group:0"),
        )
        changed_binding_end = replace(
            input_fit.role_bindings[1],
            observation_id=ObservationId("changed:1"),
            evidence_group_id=ObservationId("changed-group:1"),
        )
        changed = replace(
            input_fit,
            role_bindings=(
                changed_binding,
                changed_binding_end,
                *input_fit.role_bindings[2:],
            ),
        )
        self.assertFalse(
            select_native_phase_retention(
                (self._record(input_fit, output=changed),)
            ).diagnostics
        )

    def test_missing_intrinsic_partial_or_outer_only_terminal_facts_are_empty(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        first_only = replace(
            self._authority(fit),
            facts=self._authority(fit).facts[:2],
        )
        first_only_record = (
            _BoundFit(fit, True),
            _BoundFit(fit, True),
            self._projection(first_only),
        )
        self.assertFalse(select_native_phase_retention((first_only_record,)).diagnostics)

        partial = self._record(
            fit,
            bases=(DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,),
        )
        self.assertFalse(select_native_phase_retention((partial,)).diagnostics)
        outer_only = self._record(
            fit,
            bases=(DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,),
        )
        self.assertFalse(select_native_phase_retention((outer_only,)).diagnostics)

    def test_joint_fit_variants_are_scanned_without_endpoint_deduplication(self):
        template = placement_template(3)
        first = placement_sequence(template)
        second = replace(
            first,
            pitch_fit=replace(
                first.pitch_fit,
                gap_interval_px=FiniteInterval(19.0, 21.0),
            ),
            model_full_role_intervals_px=tuple(
                FiniteInterval(interval.minimum - 1.0, interval.maximum + 1.0)
                for interval in first.model_full_role_intervals_px
            ),
        )
        retained = select_native_phase_retention(
            (self._record(first), self._record(second))
        )
        self.assertEqual(retained.record_scan_count, 2)
        self.assertEqual(
            retained.fact_check_count,
            2 * len(retained.diagnostics[0].projection.input_direct_role_authority.facts)
            if retained.diagnostics[0] is not None
            else 0,
        )
        assert retained.diagnostics[0] is not None
        self.assertIs(retained.diagnostics[0].fit, first)

    def test_carry_compares_two_complete_diagnostics_and_checks_context(self):
        template = placement_template(3)
        first = replace(placement_sequence(template), residual_sum_px=9.0)
        second = replace(placement_sequence(template), residual_sum_px=1.0)
        prior = select_native_phase_retention((self._record(first),))
        current = select_native_phase_retention((self._record(second),))
        registered = first.bound_observation_ids
        carried = carry_native_phase_retention(
            prior,
            current,
            template=template,
            registered_direct_observation_ids=registered,
        )
        assert carried.diagnostics[0] is not None
        self.assertIs(carried.diagnostics[0].fit, second)
        self.assertEqual(carried.carry_comparison_count, 4)

        tied = carry_native_phase_retention(
            prior,
            prior,
            template=template,
            registered_direct_observation_ids=registered,
        )
        assert tied.diagnostics[0] is not None
        self.assertIs(tied.diagnostics[0].fit, first)

        different_template = replace(template, template_id="different-template")
        different_fit = placement_sequence(different_template)
        different = select_native_phase_retention((self._record(different_fit),))
        with self.assertRaises(ValueError):
            carry_native_phase_retention(prior, different)
        with self.assertRaises(ValueError):
            carry_native_phase_retention(
                prior,
                current,
                template=template,
                registered_direct_observation_ids=registered[:-1],
            )

    def test_typed_invalid_indices_and_projection_identity_are_rejected(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        record = self._record(fit)
        retention = select_native_phase_retention((record,))
        assert retention.diagnostics[0] is not None
        diagnostic = retention.diagnostics[0]
        with self.assertRaises(ValueError):
            replace(diagnostic, terminal_role_indices=(0, 1, 99))
        with self.assertRaises(ValueError):
            replace(diagnostic, terminal_role_indices=(0,))
        wrong_projection = self._projection(
            self._authority(placement_sequence(template, missing=(0, 1))),
        )
        with self.assertRaises(ValueError):
            NativeEndpointPhaseDiagnostic(
                fit=fit,
                projection=wrong_projection,
                residual_compatible=True,
                terminal_role_indices=diagnostic.terminal_role_indices,
                selection_basis=diagnostic.selection_basis,
            )
        mismatched_fact = replace(
            record[2].input_direct_role_authority.facts[0],
            observation_id=ObservationId("unrelated:fit-binding"),
            evidence_group_id=ObservationId("unrelated:fit-group"),
        )
        mismatched_authority = replace(
            record[2].input_direct_role_authority,
            facts=(
                mismatched_fact,
                *record[2].input_direct_role_authority.facts[1:],
            ),
            state=EvidenceState.SUPPORTED,
            unsupported_role_indices=(),
            reason=None,
        )
        mismatched_projection = replace(
            record[2],
            input_direct_role_authority=mismatched_authority,
        )
        with self.assertRaises(ValueError):
            NativeEndpointPhaseDiagnostic(
                fit=fit,
                projection=mismatched_projection,
                residual_compatible=True,
                terminal_role_indices=diagnostic.terminal_role_indices,
                selection_basis=diagnostic.selection_basis,
            )

    def test_receipt_empty_and_scan_bounds_are_typed(self):
        self.assertEqual(NativePhaseRetention(), NativePhaseRetention())
        with self.assertRaises(ValueError):
            NativePhaseRetention(record_scan_count=0, role_count=2)
        with self.assertRaises(ValueError):
            NativePhaseRetention(record_scan_count=1, role_count=1)
        with self.assertRaises(ValueError):
            NativePhaseRetention(record_scan_count=1, role_count=3)
        with self.assertRaises(ValueError):
            NativePhaseRetention(
                record_scan_count=1,
                fact_check_count=3,
                role_count=2,
            )
        with self.assertRaises(ValueError):
            NativePhaseRetention(
                record_scan_count=1,
                carry_comparison_count=1,
                role_count=2,
            )

    def test_phase_result_private_handoff_validates_template_ids_and_bound_status(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        result = self._phase_result(fit)
        record = self._record(fit)
        retention = select_native_phase_retention((record,))
        retained = replace(result, _native_phase_retention=retention)
        self.assertIs(retained._native_phase_retention, retention)
        with self.assertRaises(ValueError):
            replace(
                result,
                _native_phase_retention=retention,
                registered_direct_observation_ids=(),
            )
        with self.assertRaises(ValueError):
            replace(
                result,
                best=None,
                runner_up=None,
                status=PhaseFitStatus.BOUND_EXCEEDED,
                failure_kind=PhaseFailureKind.OBSERVATION_BOUND_EXCEEDED,
                ambiguity_reason="bounded",
                winner_basis=None,
                _native_phase_retention=retention,
            )

    def test_phase_result_checks_all_diagnostics_not_only_first(self):
        template = placement_template(3)
        fit = placement_sequence(template)
        changed_binding = replace(
            fit.role_bindings[-1],
            observation_id=ObservationId("unregistered:last"),
            evidence_group_id=ObservationId("unregistered:last"),
        )
        changed = replace(fit, role_bindings=(*fit.role_bindings[:-1], changed_binding))
        retention = select_native_phase_retention((
            self._record(fit, intrinsic_roles=(0, 4)),
            self._record(changed, intrinsic_roles=(1, 5)),
        ))
        self.assertEqual(len(retention.diagnostics), 2)
        with self.assertRaises(ValueError):
            replace(self._phase_result(fit), _native_phase_retention=retention)
        registered = (*fit.bound_observation_ids, ObservationId("unregistered:last"))
        result = replace(self._phase_result(fit), registered_direct_observation_ids=registered)
        self.assertIs(replace(result, _native_phase_retention=retention)._native_phase_retention, retention)

    def test_carry_compares_each_class_and_preserves_prior_ties_and_failures(self):
        template = placement_template(3)
        prior_records = self._class_records(template, (9.0, 1.0, 5.0, 0.0))
        prior_records = (*prior_records[:3], self._record(
            prior_records[3][0].fit, failed=True, intrinsic_roles=(1, 5),
            contradicted=(5,),
        ))
        current_records = self._class_records(template, (1.0, 9.0, 5.0, 9.0))
        current_es = current_records[2][0].fit
        current_es = replace(
            current_es,
            model_full_role_intervals_px=tuple(
                FiniteInterval(interval.minimum - 1.0, interval.maximum + 1.0)
                for interval in current_es.model_full_role_intervals_px
            ),
        )
        current_records = (*current_records[:2], self._record(
            current_es, intrinsic_roles=(1, 4),
        ), current_records[3])
        prior = select_native_phase_retention(prior_records)
        current = select_native_phase_retention(current_records)
        carried = carry_native_phase_retention(prior, current)
        self.assertEqual(carried.role_class_indices, (0, 1, 2, 3) + (None,) * 7 + (4,))
        self.assertIs(carried.diagnostics[0], current.diagnostics[0])
        self.assertIs(carried.diagnostics[1], prior.diagnostics[1])
        self.assertIs(carried.diagnostics[2], prior.diagnostics[2])
        self.assertIs(carried.diagnostics[3], current.diagnostics[3])
        self.assertIs(carried.diagnostics[4], prior.diagnostics[3])
        self.assertEqual(carried.carry_comparison_count, 3)
        self.assertEqual(carried.class_membership_count, 8)
        self.assertEqual(carried.deduplication_comparison_count, 22)
        self.assertGreater(carried.peak_temporary_bytes, prior.peak_temporary_bytes)
        self.assertEqual(prior.diagnostics[3].projection.input_direct_role_authority.state,
                         EvidenceState.CONTRADICTED)

    def test_empty_inputs_and_noop_carry_preserve_receipts(self):
        empty = NativePhaseRetention()
        self.assertEqual(select_native_phase_retention(None), empty)
        self.assertEqual(select_native_phase_retention(()), empty)
        self.assertEqual(carry_native_phase_retention(None, empty), empty)
        fit = placement_sequence(placement_template(3))
        retained = select_native_phase_retention((self._record(fit),))
        self.assertIs(carry_native_phase_retention(None, retained), retained)
        self.assertIs(carry_native_phase_retention(retained, empty), retained)
        self.assertIs(carry_native_phase_retention(empty, retained), retained)

    def test_forged_class_mapping_duplicate_or_unreferenced_diagnostics_are_rejected(self):
        retained = select_native_phase_retention(self._class_records(placement_template(3)))
        for mapping in ((0, 1, 2), (0, 1, 2, 4), (True, 1, 2, 3),
                        (-1, 1, 2, 3), (1, 0, 2, 3), (0, None, 2, 3),
                        (0, 0, 2, 3)):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                replace(retained, role_class_indices=mapping)
        with self.assertRaises(ValueError):
            replace(retained, diagnostics=(*retained.diagnostics, retained.diagnostics[0]))
        all_classes = select_native_phase_retention((self._record(placement_sequence(placement_template(3))),))
        with self.assertRaisesRegex(ValueError, "lost a represented class"):
            replace(all_classes, role_class_indices=(0,) + (None,) * 11)
        with self.assertRaises(ValueError):
            replace(all_classes, diagnostics=all_classes.diagnostics * 2,
                    role_class_indices=(0, 1, 0, 1))
        with self.assertRaises(TypeError):
            replace(retained, diagnostics=list(retained.diagnostics))

    def test_class_work_and_deduplication_receipt_bounds_are_typed(self):
        fit = placement_sequence(placement_template(3))
        record = self._record(fit)
        retained = select_native_phase_retention((record, record))
        self.assertEqual(retained.record_scan_count, 2)
        self.assertEqual(retained.fact_check_count, 2 * len(fit.role_bindings))
        self.assertEqual(retained.class_membership_count, 8)
        self.assertEqual(retained.class_comparison_count, 4)
        self.assertEqual(retained.deduplication_comparison_count, 3)
        self.assertGreater(retained.peak_temporary_bytes, 0)
        for field, value in (("class_membership_count", 9),
                             ("class_comparison_count", 9),
                             ("carry_comparison_count", 13),
                             ("deduplication_comparison_count", 199),
                             ("class_membership_count", True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(retained, **{field: value})
        for field in ("class_membership_count", "class_comparison_count",
                      "carry_comparison_count", "deduplication_comparison_count"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                NativePhaseRetention(**{field: 1})


if __name__ == "__main__":
    unittest.main()
