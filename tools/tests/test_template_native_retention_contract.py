from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_template,
    placement_sequence,
    placement_template,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_native_retention import (
    carry_native_phase_retention,
    select_native_phase_retention,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_candidates import _BoundFit
from x5crop.detection.photo_geometry.template_phase_model import (
    NativeEndpointPhaseDiagnostic,
    NativeEndpointSelectionBasis,
    NativePhaseRetention,
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId


class NativeRetentionContractTests(unittest.TestCase):
    def _authority(
        self,
        fit,
        *,
        bases=(),
        contradicted: tuple[int, ...] = (),
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

    def _record(self, fit, *, output=None, failed=False, bases=(), contradicted=()):
        authority = self._authority(
            fit,
            bases=bases,
            contradicted=contradicted,
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
        self.assertIsNotNone(selected.diagnostic)
        assert selected.diagnostic is not None
        self.assertIs(selected.diagnostic.fit, outer_fit)
        self.assertEqual(
            selected.diagnostic.selection_basis,
            NativeEndpointSelectionBasis.OUTER_MATERIAL_TERMINAL,
        )

        lower = replace(placement_sequence(template), residual_sum_px=9.0)
        higher = replace(placement_sequence(template), residual_sum_px=1.0)
        ranked = select_native_phase_retention(
            (self._record(lower), self._record(higher))
        )
        assert ranked.diagnostic is not None
        self.assertIs(ranked.diagnostic.fit, higher)

        tie_first = placement_sequence(template)
        tie_second = replace(tie_first)
        tied = select_native_phase_retention(
            (self._record(tie_first), self._record(tie_second))
        )
        assert tied.diagnostic is not None
        self.assertIs(tied.diagnostic.fit, tie_first)

    def test_success_uses_existing_output_and_failure_keeps_input_and_ledger(self):
        template = placement_template(3)
        input_fit = replace(placement_sequence(template), residual_sum_px=100.0)
        output_fit = replace(placement_sequence(template), residual_sum_px=0.0)
        successful = select_native_phase_retention(
            (self._record(input_fit, output=output_fit),)
        )
        assert successful.diagnostic is not None
        self.assertIs(successful.diagnostic.fit, output_fit)
        self.assertTrue(successful.diagnostic.projection.eligible)

        contradicted = self._record(
            input_fit,
            failed=True,
            contradicted=(0,),
        )
        failed = select_native_phase_retention((contradicted,))
        assert failed.diagnostic is not None
        self.assertIs(failed.diagnostic.fit, input_fit)
        self.assertIs(failed.diagnostic.projection, contradicted[2])
        self.assertEqual(
            failed.diagnostic.projection.input_direct_role_authority.state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(
            failed.diagnostic.projection.input_direct_role_authority.facts[0].state,
            EvidenceState.CONTRADICTED,
        )

    def test_completed_projection_precedes_raw_rank_within_terminal_class(self):
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
        self.assertGreater(failed.diagnostic.rank, successful.diagnostic.rank)
        for records in ((failed_record, successful_record),
                        (successful_record, failed_record)):
            selected = select_native_phase_retention(records)
            self.assertIs(selected.diagnostic.fit, projected)
            self.assertTrue(selected.diagnostic.projection.eligible)
        carried = carry_native_phase_retention(successful, failed)
        self.assertIs(carried.diagnostic.fit, projected)

        # A distinct outer-material terminal explanation remains represented
        # even when its original projection carries contradictory facts.
        outer_record = self._record(
            raw, failed=True, contradicted=(0,), bases=(
                DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,
            ),
        )
        selected = select_native_phase_retention((successful_record, outer_record))
        self.assertIs(selected.diagnostic.fit, raw)
        self.assertIs(selected.diagnostic.projection, outer_record[2])
        self.assertFalse(selected.diagnostic.projection.eligible)

    def test_output_deleted_or_changed_terminal_binding_cannot_borrow_input_fact(self):
        template = placement_template(3)
        input_fit = placement_sequence(template)
        deleted = placement_sequence(template, missing=(0, 1))
        self.assertIsNone(
            select_native_phase_retention(
                (self._record(input_fit, output=deleted),)
            ).diagnostic
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
        self.assertIsNone(
            select_native_phase_retention(
                (self._record(input_fit, output=changed),)
            ).diagnostic
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
        self.assertIsNone(select_native_phase_retention((first_only_record,)).diagnostic)

        partial = self._record(
            fit,
            bases=(DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,),
        )
        self.assertIsNone(select_native_phase_retention((partial,)).diagnostic)
        outer_only = self._record(
            fit,
            bases=(DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,),
        )
        self.assertIsNone(select_native_phase_retention((outer_only,)).diagnostic)

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
            2 * len(retained.diagnostic.projection.input_direct_role_authority.facts)
            if retained.diagnostic is not None
            else 0,
        )
        assert retained.diagnostic is not None
        self.assertIs(retained.diagnostic.fit, first)

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
        assert carried.diagnostic is not None
        self.assertIs(carried.diagnostic.fit, second)
        self.assertEqual(carried.carry_comparison_count, 1)

        tied = carry_native_phase_retention(
            prior,
            prior,
            template=template,
            registered_direct_observation_ids=registered,
        )
        assert tied.diagnostic is not None
        self.assertIs(tied.diagnostic.fit, first)

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
        assert retention.diagnostic is not None
        diagnostic = retention.diagnostic
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
        template = phase_template(3)
        observations = tuple(
            phase_edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((100.0, 200.0, 220.0, 320.0, 340.0, 440.0))
        )
        result = fit_template_phase(observations, template)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        record = self._record(result.best)
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


if __name__ == "__main__":
    unittest.main()
