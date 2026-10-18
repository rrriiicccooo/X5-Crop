from __future__ import annotations

from dataclasses import replace
from typing import get_type_hints
import unittest

from tools.regression.report_validation import _read_common_proof
from tools.tests.template_test_support import (
    phase_edge,
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_lattice_authority import direct_role_constraint_rank
from x5crop.detection.photo_geometry.template_model import (
    SequenceBindingUse,
    TemplateSearchReceipt,
    phase_lattice_fit_from_absolute,
)
from x5crop.detection.photo_geometry.template_phase_candidate_model import _BoundFit
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectedBinding,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
)
from x5crop.detection.photo_geometry.template_phase import _carry_native_phase_diagnostic
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_source_clipped import (
    SourceClippedPhaseDiagnostic,
    SourceClippedPhaseRetention,
    _deduplicate_classes,
    carry_source_clipped_phase_retention,
    select_source_clipped_phase_retention,
)
from x5crop.detection.photo_geometry.template_source_domain import PhaseSourceDomain
from x5crop.domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    ObservationId,
    WorkspaceExtent,
)
from x5crop.report.read_models import typed_read_model


def _domain(width=350):
    return PhaseSourceDomain("lane:test", Box(0, 0, width, 50), WorkspaceExtent(width, 50), BoundaryAxis.X)


def _fit(roles=(0, 1, 2), *, phase=-50.0, direction=1, residual=0.0):
    original = placement_sequence(phase_template(3), missing=tuple(i for i in range(6) if i not in roles))
    template = replace(original.template, direction=direction,
        phase_lattice_authority=replace(original.template.phase_lattice_authority, minimum_slot_offset=-5))
    positions = tuple(phase + direction * (slot * 120.0 + edge * 100.0) for slot in range(3) for edge in range(2))
    intervals = tuple(FiniteInterval.exact(value) for value in positions)
    bindings = tuple(None if binding is None else replace(binding,
        canonical_position_px=positions[i], fit_position_interval_px=intervals[i],
        full_position_interval_px=intervals[i]) for i, binding in enumerate(original.role_bindings))
    lattice = phase_lattice_fit_from_absolute(template, absolute_phase_px=phase, period_px=120.0, uncertainty_px=0.0)
    assert lattice is not None
    return replace(original, template=template, phase_lattice_fit=lattice,
        model_role_positions_px=positions, model_role_intervals_px=intervals,
        model_full_role_intervals_px=intervals, role_bindings=bindings, residual_sum_px=residual)


def _record(fit, *, output=None, failed=False, supported=None, contradicted=(),
            intrinsic=None, outer=(), rank=None, raw_compatible=False, output_compatible=True):
    bound = tuple(i for i, binding in enumerate(fit.role_bindings) if binding is not None)
    supported = bound if supported is None else supported
    intrinsic = bound if intrinsic is None else intrinsic
    facts = []
    for i in bound:
        binding = fit.role_bindings[i]
        state = EvidenceState.CONTRADICTED if i in contradicted else EvidenceState.SUPPORTED if i in supported else EvidenceState.UNAVAILABLE
        bases = () if state == EvidenceState.UNAVAILABLE else (
            (DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,) if i in intrinsic else
            (DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,)
        )
        if i in outer and bases:
            bases = (*bases, DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY)
        facts.append(DirectRoleAuthorityFact(i, i // 2 + 1,
            BoundaryRole.START if i % 2 == 0 else BoundaryRole.END,
            binding.observation_id, binding.evidence_group_id,
            2 if DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR in bases else 3,
            bases, (ObservationId(f"conflict:{i}"),) if state == EvidenceState.CONTRADICTED else (),
            state, (1, 2) if DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR in bases else (),
            (ObservationId(f"outer:{i}"),) if DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY in bases else ()))
    state = EvidenceState.CONTRADICTED if contradicted else EvidenceState.UNAVAILABLE if any(f.state == EvidenceState.UNAVAILABLE for f in facts) else EvidenceState.SUPPORTED
    authority = DirectRoleBindingAuthority(state, tuple(facts), tuple(f.role_index for f in facts if f.state != EvidenceState.SUPPORTED), None if state == EvidenceState.SUPPORTED else "preserved authority failure")
    failed = failed or bool(contradicted)
    effective = fit if failed or output is None else output
    rank = direct_role_constraint_rank(effective, authority.supported_role_indices) if rank is None else rank
    outcome = (
        PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION if contradicted else
        PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE if failed else
        PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID if state == EvidenceState.UNAVAILABLE else
        PhaseCandidateProjectionOutcome.UNCHANGED
    )
    projection = PhaseCandidateAuthorityProjection(authority, outcome,
        None if failed else PhaseCandidateProjectionBasis.CALIBRATED_NOMINAL_GRID if state == EvidenceState.UNAVAILABLE else PhaseCandidateProjectionBasis.DIRECT_BINDINGS,
        tuple(PhaseCandidateProjectedBinding(f.role_index, f.observation_id) for f in facts if f.state == EvidenceState.UNAVAILABLE),
        rank, "preserved projection failure" if failed else None)
    return _BoundFit(fit, raw_compatible), None if failed else _BoundFit(effective, output_compatible), projection


def _select(records, domain=None):
    return select_source_clipped_phase_retention(records, source_domain=domain or _domain())


def _phase_result(fit):
    return PhaseFitResult(fit.template, fit, None, PhaseFitStatus.UNRESOLVED, "synthetic unresolved",
        TemplateSearchReceipt(len(fit.bound_observation_ids), 6, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        fit.bound_observation_ids, PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE)


class SourceClippedRetentionContractTests(unittest.TestCase):
    def test_fixed_six_classes_and_both_clipped_complete_deduplication(self):
        records = tuple(_record(_fit(roles)) for roles in ((0,), (0, 1), (0, 1, 2)))
        retained = _select(records, _domain(250))
        self.assertEqual(retained.class_indices, (0, 1, 2, 0, 1, 2))
        self.assertEqual(len(retained.diagnostics), 3)
        self.assertEqual(retained.class_membership_count, 6)
        for i, diagnostic in enumerate(retained.diagnostics):
            self.assertEqual(diagnostic.constraint_rank, i + 1)
            self.assertEqual(diagnostic.class_memberships, (i, i + 3))
            self.assertEqual(diagnostic.clipped_role_indices, (0, 5))
        self.assertEqual(_select(records).class_indices, (0, 1, 2, None, None, None))

    def test_rank_zero_local_only_contradicted_only_and_partial_only_are_excluded(self):
        fit = _fit()
        bindings = tuple(None if binding is None else replace(binding, use=SequenceBindingUse.LOCAL_REFINEMENT) for binding in fit.role_bindings)
        with self.assertRaises(ValueError):
            replace(fit, role_bindings=bindings, phase_support_coverage=0.0)
        local_intrinsic_binding = replace(fit.role_bindings[0], use=SequenceBindingUse.LOCAL_REFINEMENT)
        local_intrinsic = replace(fit, role_bindings=(local_intrinsic_binding, *fit.role_bindings[1:]), phase_support_coverage=1.0)
        records = (
            _record(fit, supported=(), failed=True),
            _record(fit, contradicted=(0, 1, 2), rank=1),
            _record(fit, intrinsic=()),
            _record(local_intrinsic, intrinsic=(0,)),
        )
        for record in records:
            with self.subTest(record=record):
                self.assertFalse(_select((record,)).diagnostics)

    def test_exact_binding_mapping_and_original_rank_are_not_invented(self):
        fit = _fit()
        record = _record(fit)
        mismatch = replace(record[2].input_direct_role_authority.facts[0], observation_id=ObservationId("unrelated:0"))
        authority = replace(record[2].input_direct_role_authority, facts=(mismatch, *record[2].input_direct_role_authority.facts[1:]))
        bad = (*record[:2], replace(record[2], input_direct_role_authority=authority))
        with self.assertRaises(ValueError):
            _select((bad,))
        rank_mismatch = (*record[:2], replace(record[2], retained_direct_constraint_rank=2))
        self.assertFalse(_select((rank_mismatch,)).diagnostics)
        diagnostic = _select((record,)).diagnostics[0]
        with self.assertRaises(ValueError):
            replace(diagnostic, constraint_rank=2)
        with self.assertRaises(ValueError):
            replace(diagnostic, clipped_role_indices=(5,))

    def test_aggregate_intrinsic_anchor_and_mixed_contradiction_keep_exact_facts(self):
        record = _record(_fit((0,)))
        fact = replace(record[2].input_direct_role_authority.facts[0], bases=(DirectRoleAuthorityBasis.AGGREGATE_UNION,))
        authority = replace(record[2].input_direct_role_authority, facts=(fact,))
        aggregate = (*record[:2], replace(record[2], input_direct_role_authority=authority))
        self.assertIs(_select((aggregate,)).diagnostics[0].projection, aggregate[2])
        mixed = _record(_fit(), contradicted=(0,))
        diagnostic = _select((mixed,)).diagnostics[0]
        self.assertIs(diagnostic.projection, mixed[2])
        self.assertEqual(diagnostic.projection.input_direct_role_authority.state, EvidenceState.CONTRADICTED)
        self.assertEqual(diagnostic.constraint_rank, 2)
        singleton = _record(_fit((0,)))
        wrong = replace(singleton[2].input_direct_role_authority.facts[0], observation_id=ObservationId("unrelated:only"))
        wrong_authority = replace(singleton[2].input_direct_role_authority, facts=(wrong,))
        self.assertFalse(_select(((*singleton[:2], replace(singleton[2], input_direct_role_authority=wrong_authority)),)).diagnostics)

    def test_success_uses_output_clip_pattern_and_residual_flag_failure_keeps_full_input(self):
        raw, output = _fit((0,), phase=-50.0), _fit((0,), phase=50.0)
        record = _record(raw, output=output, raw_compatible=False, output_compatible=True)
        diagnostic = _select((record,)).diagnostics[0]
        self.assertIs(diagnostic.fit, output)
        self.assertEqual(diagnostic.clipped_role_indices, (5,))
        self.assertTrue(diagnostic.residual_compatible)
        failed = _record(raw, failed=True, raw_compatible=False)
        diagnostic = _select((failed,)).diagnostics[0]
        self.assertIs(diagnostic.fit, raw)
        self.assertIs(diagnostic.projection, failed[2])
        self.assertEqual(diagnostic.clipped_role_indices, (0,))
        self.assertFalse(diagnostic.residual_compatible)
        unclip = _fit((0,), phase=0.0)
        self.assertFalse(_select((_record(raw, output=unclip),)).diagnostics)

    def test_internal_lane_wrong_direction_and_empty_visible_frame_are_excluded(self):
        internal = replace(_domain(), sampling_authority_box=Box(0, 0, 250, 50))
        self.assertFalse(_select((_record(_fit()),), internal).diagnostics)
        for fit in (_fit(phase=-100.5), _fit(phase=-110.0), _fit(phase=-50.0, direction=-1)):
            self.assertFalse(_select((_record(fit),)).diagnostics)
        reverse = _select((_record(_fit(phase=290.0, direction=-1)),), _domain(250))
        self.assertEqual(reverse.diagnostics[0].clipped_role_indices, (0, 5))

    def test_same_fit_with_different_projection_and_rank_is_not_deduplicated(self):
        fit = _fit()
        low = _record(fit, supported=(0,), failed=True)
        high = _record(fit, supported=(0, 1), failed=True)
        retained = _select((low, high), _domain(250))
        self.assertEqual(retained.class_indices, (0, 1, None, 0, 1, None))
        self.assertEqual(retained.diagnostics[0].fit, retained.diagnostics[1].fit)
        self.assertNotEqual(retained.diagnostics[0].projection, retained.diagnostics[1].projection)
        self.assertEqual(len(retained.diagnostics), 2)
        self.assertEqual(_deduplicate_classes([retained.diagnostics[0], retained.diagnostics[1], None, None, None, None])[0], retained.diagnostics)

    def test_outer_then_eligible_then_original_rank_with_stable_first_ties(self):
        low, high = _fit((0,), residual=9.0), _fit((0,), residual=1.0)
        first, second = _record(low), _record(high)
        self.assertIs(_select((first, second)).diagnostics[0].fit, high)
        tied = replace(high, model_full_role_intervals_px=tuple(FiniteInterval(v.minimum - 1.0, v.maximum + 1.0) for v in high.model_full_role_intervals_px))
        self.assertIs(_select((second, _record(tied))).diagnostics[0].fit, high)
        failed = _record(high, failed=True, raw_compatible=True)
        self.assertIs(_select((failed, first)).diagnostics[0].fit, low)
        outer = _record(high, failed=True, outer=(0,))
        self.assertIs(_select((first, outer)).diagnostics[0].projection, outer[2])

    def test_supported_native_groups_precede_projection_success(self):
        eligible = _record(_fit((0, 1, 2)))
        stronger_native = _record(
            _fit((0, 1, 2, 3)), failed=True, raw_compatible=True,
        )
        selected = _select((eligible, stronger_native))
        self.assertIs(selected.diagnostics[0].projection, stronger_native[2])
        self.assertFalse(selected.diagnostics[0].projection.eligible)

        # An unsupported extra binding adds no native evidence and cannot
        # displace the completed projection just by inflating raw support.
        weak_extra = _record(
            _fit((0, 1, 2, 3)), failed=True, supported=(0, 1, 2),
            intrinsic=(0, 1, 2), raw_compatible=True,
        )
        self.assertIs(_select((weak_extra, eligible)).diagnostics[0].projection, eligible[2])

        correlated = _fit((0, 1, 2, 3))
        bindings = list(correlated.role_bindings)
        bindings[3] = replace(bindings[3], evidence_group_id=bindings[2].evidence_group_id)
        correlated = _record(
            replace(correlated, role_bindings=tuple(bindings)),
            failed=True, raw_compatible=True,
        )
        self.assertIs(_select((correlated, eligible)).diagnostics[0].projection, eligible[2])

    def test_carry_checks_domains_context_and_preserves_prior_key_ties(self):
        first = _select((_record(_fit((0,), residual=9.0)),))
        second = _select((_record(_fit((0,), residual=1.0)),))
        combined = carry_source_clipped_phase_retention(first, second)
        self.assertIs(combined.diagnostics[0], second.diagnostics[0])
        self.assertEqual(combined.carry_comparison_count, 1)
        tie_fit = replace(first.diagnostics[0].fit, model_full_role_intervals_px=tuple(
            FiniteInterval(value.minimum - 1.0, value.maximum + 1.0)
            for value in first.diagnostics[0].fit.model_full_role_intervals_px))
        tied_current = _select((_record(tie_fit),))
        self.assertIs(carry_source_clipped_phase_retention(first, tied_current).diagnostics[0], first.diagnostics[0])
        with self.assertRaises(ValueError):
            carry_source_clipped_phase_retention(first, _select((_record(_fit((0,))),), _domain(360)))
        with self.assertRaises(ValueError):
            carry_source_clipped_phase_retention(first, second, template=replace(first.template, template_id="different"))
        with self.assertRaises(ValueError):
            carry_source_clipped_phase_retention(first, second, registered_direct_observation_ids=())
        without_qualified_records = _select((_record(_fit(), supported=(), failed=True),), _domain(360))
        with self.assertRaises(ValueError):
            carry_source_clipped_phase_retention(first, without_qualified_records)
        self.assertIs(carry_source_clipped_phase_retention(None, first), first)
        self.assertIs(carry_source_clipped_phase_retention(SourceClippedPhaseRetention(), first), first)

    def test_receipt_and_class_mapping_bounds_reject_forged_work(self):
        record = _record(_fit((0,)))
        retained = _select((record, record), _domain(250))
        self.assertEqual(retained.record_scan_count, 2)
        self.assertEqual(retained.source_role_check_count, 12)
        self.assertEqual(retained.fact_check_count, 2)
        self.assertEqual(retained.class_membership_count, 4)
        self.assertEqual(retained.class_comparison_count, 2)
        self.assertGreater(retained.peak_temporary_bytes, 0)
        for name, value in (
            ("source_role_check_count", 13), ("fact_check_count", 13),
            ("constraint_rank_check_count", 3), ("class_membership_count", 5),
            ("class_comparison_count", 5), ("carry_comparison_count", 7),
            ("deduplication_comparison_count", 46), ("peak_temporary_bytes", 0),
            ("record_scan_count", True),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(retained, **{name: value})
        for mapping in ((0,), (True, None, None, 0, None, None), (0, 0, None, 0, None, None), (0, None, None, None, None, None)):
            with self.assertRaises(ValueError):
                replace(retained, class_indices=mapping)
        with self.assertRaises(ValueError):
            replace(retained, diagnostics=retained.diagnostics * 2)
        with self.assertRaises(ValueError):
            SourceClippedPhaseRetention(record_scan_count=1)
        self.assertEqual(select_source_clipped_phase_retention((record,), source_domain=None), SourceClippedPhaseRetention())

    def test_phase_private_handoff_is_typed_and_does_not_serialize(self):
        record = _record(_fit())
        retention = _select((record,))
        result = replace(_phase_result(record[0].fit), _source_clipped_phase_retention=retention)
        self.assertIs(get_type_hints(PhaseFitResult)["_source_clipped_phase_retention"].__args__[0], SourceClippedPhaseRetention)
        self.assertIs(get_type_hints(SourceClippedPhaseDiagnostic)["projection"], PhaseCandidateAuthorityProjection)
        raw = typed_read_model(result)
        self.assertNotIn("_source_clipped_phase_retention", raw)
        restored = _read_common_proof(raw, PhaseFitResult)
        self.assertEqual(typed_read_model(restored), raw)
        self.assertIsNone(restored._source_clipped_phase_retention)
        with self.assertRaises(ValueError):
            replace(result, registered_direct_observation_ids=())
        with self.assertRaises(TypeError):
            replace(result, _source_clipped_phase_retention=True)
        with self.assertRaises(ValueError):
            replace(result, status=PhaseFitStatus.BOUND_EXCEEDED, best=None,
                failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED)
        bounded = replace(result, status=PhaseFitStatus.BOUND_EXCEEDED, best=None,
            failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED, _source_clipped_phase_retention=None)
        self.assertIsNone(_carry_native_phase_diagnostic(bounded, result)._source_clipped_phase_retention)

    def test_real_phase_projection_pool_hands_off_only_its_existing_clipped_records(self):
        domain = _domain()
        holder = FiniteInterval(0.0, 349.0)
        observations = tuple(phase_edge(f"visible:{i}", position)
            for i, position in enumerate((50.0, 70.0, 170.0, 190.0, 290.0)))
        result = fit_template_phase(observations, phase_template(3), holder_span_px=holder,
            source_domain=domain,
            sequence_measurement_sets=(phase_sequence_measurement("visible-source", holder),))
        canonical = fit_template_phase(observations, phase_template(3), holder_span_px=holder,
            sequence_measurement_sets=(phase_sequence_measurement("visible-source", holder),))
        self.assertGreater(result.receipt.candidate_direct_role_projection_evaluation_count,
            canonical.receipt.candidate_direct_role_projection_evaluation_count)
        self.assertEqual(replace(result, receipt=canonical.receipt,
            _source_clipped_phase_retention=None), canonical)
        retained = result._source_clipped_phase_retention
        self.assertIsNotNone(retained)
        self.assertTrue(retained.diagnostics)
        self.assertTrue(all(item.source_domain is domain for item in retained.diagnostics))
        self.assertTrue(any(item.clipped_role_indices == (0,) for item in retained.diagnostics))
        carried = _carry_native_phase_diagnostic(result, result)
        self.assertIs(carried._source_clipped_phase_retention.diagnostics[0], retained.diagnostics[0])


if __name__ == "__main__":
    unittest.main()
