from __future__ import annotations

from dataclasses import replace
import math
import unittest
from unittest.mock import patch

from tools.tests.template_test_support import phase_template, placement_sequence
from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.detection.photo_geometry.template_phase_admission import (
    PhaseMemberAdmissionProof,
    admission_proof_bytes_bound,
    admission_proof_work_bound,
    assess_phase_member_admission,
)
from x5crop.detection.photo_geometry.template_source_domain import (
    PhaseSourceDomain,
)
from x5crop.domain import Box, FiniteInterval, ObservationId, WorkspaceExtent


def _source_domain(
    *,
    lane_id: str = "lane:proof",
    box: Box = Box(0, 0, 500, 100),
    extent: WorkspaceExtent = WorkspaceExtent(500, 100),
) -> PhaseSourceDomain:
    return PhaseSourceDomain(lane_id, box, extent, BoundaryAxis.X)


def _move_fit(fit, offset: float):
    def move_interval(interval: FiniteInterval) -> FiniteInterval:
        return FiniteInterval(
            interval.minimum + offset,
            interval.maximum + offset,
        )

    bindings = tuple(
        None
        if binding is None
        else replace(
            binding,
            canonical_position_px=binding.canonical_position_px + offset,
            fit_position_interval_px=move_interval(binding.fit_position_interval_px),
            full_position_interval_px=move_interval(binding.full_position_interval_px),
        )
        for binding in fit.role_bindings
    )
    return replace(
        fit,
        model_role_positions_px=tuple(
            value + offset for value in fit.model_role_positions_px
        ),
        model_role_intervals_px=tuple(
            move_interval(interval) for interval in fit.model_role_intervals_px
        ),
        model_full_role_intervals_px=tuple(
            move_interval(interval)
            for interval in fit.model_full_role_intervals_px
        ),
        role_bindings=bindings,
    )


def _reverse_fit(fit):
    template = replace(fit.template, direction=-1)
    phase_lattice = replace(
        fit.phase_lattice_fit,
        direction=-1,
        canonical_absolute_phase_px=-100.0,
        absolute_phase_interval_px=FiniteInterval.exact(-100.0),
    )
    return replace(
        fit,
        template=template,
        phase_lattice_fit=phase_lattice,
        model_role_positions_px=tuple(reversed(fit.model_role_positions_px)),
        model_role_intervals_px=tuple(reversed(fit.model_role_intervals_px)),
        model_full_role_intervals_px=tuple(
            reversed(fit.model_full_role_intervals_px)
        ),
        role_bindings=tuple(reversed(fit.role_bindings)),
    )


class PhaseAdmissionProofContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = phase_template(2)
        self.base_fit = placement_sequence(self.template)
        self.holder = FiniteInterval(0.0, 500.0)
        self.domain = _source_domain()

    def test_normal_in_domain_admission_replays_both_owner_facts(self) -> None:
        with (
            patch(
                "x5crop.detection.photo_geometry.template_phase_competition._candidate_respects_holder",
                wraps=__import__(
                    "x5crop.detection.photo_geometry.template_phase_competition",
                    fromlist=["_candidate_respects_holder"],
                )._candidate_respects_holder,
            ) as holder_owner,
            patch(
                "x5crop.detection.photo_geometry.template_source_domain.source_clipped_terminal_roles",
                wraps=__import__(
                    "x5crop.detection.photo_geometry.template_source_domain",
                    fromlist=["source_clipped_terminal_roles"],
                ).source_clipped_terminal_roles,
            ) as source_owner,
        ):
            proof = assess_phase_member_admission(
                self.base_fit,
                self.base_fit,
                holder_span_px=self.holder,
                source_domain=self.domain,
            )
        self.assertEqual(holder_owner.call_count, 2)
        self.assertEqual(source_owner.call_count, 2)
        self.assertTrue(proof.original_holder_admitted)
        self.assertTrue(proof.current_holder_admitted)
        self.assertTrue(proof.original_source_domain_admitted)
        self.assertTrue(proof.current_source_domain_admitted)
        self.assertEqual(proof.original_source_terminal_role_indices, ())
        self.assertEqual(proof.current_source_terminal_role_indices, ())
        self.assertTrue(
            proof.matches_inputs(
                self.base_fit,
                self.base_fit,
                self.holder,
                self.domain,
            )
        )

    def test_source_clipped_terminal_is_distinct_from_holder_admission(self) -> None:
        clipped = _move_fit(self.base_fit, -200.0)
        proof = assess_phase_member_admission(
            clipped,
            self.base_fit,
            holder_span_px=self.holder,
            source_domain=self.domain,
        )
        self.assertFalse(proof.original_holder_admitted)
        self.assertTrue(proof.current_holder_admitted)
        self.assertTrue(proof.original_source_domain_admitted)
        self.assertTrue(proof.current_source_domain_admitted)
        self.assertEqual(proof.original_source_terminal_role_indices, (0,))
        self.assertEqual(proof.current_source_terminal_role_indices, ())
        self.assertFalse(hasattr(proof, "approved"))

    def test_current_holder_failure_is_retained_even_when_original_was_admitted(self) -> None:
        invalid_current = _move_fit(self.base_fit, -300.0)
        proof = assess_phase_member_admission(
            self.base_fit,
            invalid_current,
            holder_span_px=self.holder,
            source_domain=self.domain,
        )
        self.assertTrue(proof.original_holder_admitted)
        self.assertFalse(proof.current_holder_admitted)
        self.assertFalse(proof.current_source_domain_admitted)
        self.assertEqual(proof.current_source_terminal_role_indices, ())

    def test_unbound_source_terminal_retains_missing_native_evidence(self) -> None:
        clipped = _move_fit(self.base_fit, -200.0)
        clipped = replace(clipped, role_bindings=(None, *clipped.role_bindings[1:]), phase_support_coverage=1.0)
        proof = assess_phase_member_admission(clipped, clipped,
            holder_span_px=self.holder, source_domain=self.domain)
        self.assertFalse(proof.current_holder_admitted)
        self.assertTrue(proof.current_source_domain_admitted)
        self.assertEqual(len(proof.current_holder_violations), 1)
        v = proof.current_holder_violations[0]
        self.assertEqual(v.role_index, 0)
        self.assertTrue(v.source_terminal_clipped)
        self.assertIsNone(v.observation_id)
        self.assertIsNone(v.native_full_interval_px)
        with self.assertRaises(ValueError):
            replace(proof, current_holder_admitted=True)
        with self.assertRaises(ValueError):
            replace(proof, current_holder_violations=())

    def test_holder_violation_cannot_borrow_another_native_binding(self) -> None:
        clipped = _move_fit(self.base_fit, -200.0)
        proof = assess_phase_member_admission(clipped, clipped,
            holder_span_px=self.holder, source_domain=self.domain)
        self.assertEqual(proof.current_holder_violations[0].observation_id,
                         clipped.role_bindings[0].observation_id)
        borrowed = replace(proof.current_holder_violations[0], observation_id=ObservationId('unrelated-native'))
        forged = replace(proof, current_holder_violations=(borrowed,))
        self.assertFalse(forged.matches_current_fit(clipped))
        self.assertFalse(forged.matches_inputs(clipped, clipped, self.holder, self.domain))

    def test_violation_keeps_the_original_binding_numeric_tolerance(self) -> None:
        clipped = _move_fit(self.base_fit, -200.0)
        binding = clipped.role_bindings[0]
        interval = FiniteInterval.exact(binding.canonical_position_px + 5.0e-10)
        binding = replace(binding, fit_position_interval_px=FiniteInterval.exact(binding.canonical_position_px),
                          full_position_interval_px=interval)
        clipped = replace(clipped, role_bindings=(binding, *clipped.role_bindings[1:]))
        proof = assess_phase_member_admission(clipped, clipped,
            holder_span_px=self.holder, source_domain=self.domain)
        self.assertEqual(proof.current_holder_violations[0].native_full_interval_px, interval)
        self.assertFalse(proof.current_holder_admitted)

    def test_source_domain_classification_rejects_internal_wrong_side_and_empty_geometry(self) -> None:
        cases = (
            ("internal role", _move_fit(self.base_fit, -300.0), self.domain),
            (
                "wrong source side",
                _move_fit(self.base_fit, -200.0),
                _source_domain(box=Box(100, 0, 400, 100)),
            ),
            ("zero visible frame", _move_fit(self.base_fit, -400.0), self.domain),
        )
        for name, fit, domain in cases:
            with self.subTest(name=name):
                proof = assess_phase_member_admission(
                    fit,
                    fit,
                    holder_span_px=self.holder,
                    source_domain=domain,
                )
                self.assertFalse(proof.original_source_domain_admitted)
                self.assertFalse(proof.current_source_domain_admitted)
                self.assertEqual(proof.original_source_terminal_role_indices, ())
                self.assertEqual(proof.current_source_terminal_role_indices, ())

    def test_reverse_direction_uses_reverse_terminal_and_source_side(self) -> None:
        reverse = _move_fit(_reverse_fit(self.base_fit), 199.0)
        proof = assess_phase_member_admission(
            reverse,
            reverse,
            holder_span_px=FiniteInterval(0.0, 500.0),
            source_domain=self.domain,
        )
        self.assertEqual(proof.direction, -1)
        self.assertTrue(proof.original_source_domain_admitted)
        self.assertEqual(proof.original_source_terminal_role_indices, (0,))

        wrong_side = _source_domain(box=Box(0, 0, 400, 100))
        rejected = assess_phase_member_admission(
            reverse,
            reverse,
            holder_span_px=FiniteInterval(0.0, 400.0),
            source_domain=wrong_side,
        )
        self.assertFalse(rejected.original_source_domain_admitted)
        self.assertEqual(rejected.original_source_terminal_role_indices, ())

    def test_none_source_domain_has_no_source_state_or_terminals(self) -> None:
        proof = assess_phase_member_admission(
            self.base_fit,
            self.base_fit,
            holder_span_px=self.holder,
            source_domain=None,
        )
        self.assertIsNone(proof.original_source_domain_admitted)
        self.assertIsNone(proof.current_source_domain_admitted)
        self.assertEqual(proof.original_source_terminal_role_indices, ())
        self.assertEqual(proof.current_source_terminal_role_indices, ())
        self.assertTrue(proof.matches_inputs(self.base_fit, self.base_fit, self.holder, None))

    def test_mismatched_fit_identity_and_replay_inputs_are_rejected(self) -> None:
        other_template = placement_sequence(phase_template(3))
        with self.assertRaises(ValueError):
            assess_phase_member_admission(
                self.base_fit,
                other_template,
                holder_span_px=self.holder,
                source_domain=self.domain,
            )

        with self.assertRaises(ValueError):
            assess_phase_member_admission(
                self.base_fit,
                _reverse_fit(self.base_fit),
                holder_span_px=self.holder,
                source_domain=self.domain,
            )

        proof = assess_phase_member_admission(
            self.base_fit,
            _move_fit(self.base_fit, 1.0),
            holder_span_px=self.holder,
            source_domain=self.domain,
        )
        self.assertFalse(
            proof.matches_inputs(
                self.base_fit,
                _move_fit(self.base_fit, 2.0),
                self.holder,
                self.domain,
            )
        )
        self.assertFalse(proof.matches_inputs(self.base_fit, self.base_fit, None, self.domain))
        self.assertFalse(
            proof.matches_inputs(
                self.base_fit,
                self.base_fit,
                self.holder,
                _source_domain(lane_id="lane:other"),
            )
        )

    def test_proof_structure_and_static_bounds_reject_invalid_values(self) -> None:
        proof = assess_phase_member_admission(
            self.base_fit,
            self.base_fit,
            holder_span_px=self.holder,
            source_domain=self.domain,
        )
        for value in (True, 1.0, 0, -2, 3):
            with self.subTest(role_count=value):
                with self.assertRaises((TypeError, ValueError)):
                    admission_proof_work_bound(value)
                with self.assertRaises((TypeError, ValueError)):
                    admission_proof_bytes_bound(value)
        self.assertEqual(admission_proof_work_bound(4), 24)
        self.assertEqual(admission_proof_bytes_bound(4), 4096)

        invalid = (
            {"direction": True},
            {"holder_slack_px": math.nan},
            {"holder_slack_px": -1.0},
            {"original_model_role_positions_px": [100.0] * 4},
            {"original_model_role_positions_px": (True, 200, 220, 320)},
            {"original_source_terminal_role_indices": (1,)},
            {"original_holder_admitted": 1},
            {"source_domain": None, "original_source_domain_admitted": False},
            {"original_source_domain_admitted": None},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(proof, **changes)


if __name__ == "__main__":
    unittest.main()
