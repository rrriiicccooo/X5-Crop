"""Routing guards for per-hypothesis constraints, independent of eligibility."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools.tests.template_runtime_test_support import prepared_template_lane
from tools.tests.template_test_support import phase_edge
from x5crop.detection.photo_geometry.detector import _placements
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateProjectionOutcome as Projection,
    PhaseFailureKind,
    PhaseFitStatus,
)
from x5crop.domain import EvidenceState, ObservationId, PositiveInterval


class ConditionalPlacementContractTest(unittest.TestCase):
    def setUp(self) -> None:
        base = prepared_template_lane()
        self.primary_authority = SimpleNamespace(state=EvidenceState.SUPPORTED)
        self.runner_authority = SimpleNamespace(state=EvidenceState.SUPPORTED)
        self.runner_direct = SimpleNamespace(state=EvidenceState.SUPPORTED)
        self.phase = SimpleNamespace(
            best=object(), runner_up=object(),
            status=PhaseFitStatus.AMBIGUOUS,
            failure_kind=PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
            global_lattice_authority=self.primary_authority,
            direct_role_binding_authority=SimpleNamespace(state=EvidenceState.SUPPORTED),
            best_phase_candidate_authority_projection=SimpleNamespace(outcome=Projection.UNCHANGED),
            runner_phase_candidate_authority_projection=SimpleNamespace(outcome=Projection.PROJECTED),
        )
        self.width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PositiveInterval(90.0, 110.0),
            matches_placement=Mock(return_value=False),
        )
        phase_input = replace(
            base.phase_input,
            observations=(phase_edge("primary-only:W", 100.0),),
            global_lattice_evidence=replace(
                base.phase_input.global_lattice_evidence,
                frame_width_observation_ids=(ObservationId("primary-only:W"),),
            ),
        )
        # Only orchestration is mocked; physical projection and identity guards
        # have separate real-model coverage in feasible_geometry_contract.
        self.prepared = SimpleNamespace(
            phase_competition=self.phase,
            cross_competition=SimpleNamespace(best=object(), runner_up=None),
            source_frame_width_authority=self.width,
            phase_input=phase_input,
        )

    def route(self):
        with patch(
            "x5crop.detection.photo_geometry.detector._compose",
            side_effect=lambda prepared, **kwargs: SimpleNamespace(
                placement_id=id(kwargs["sequence_fit"]), **kwargs,
            ),
        ) as compose, patch(
            "x5crop.detection.photo_geometry.detector.assess_direct_role_binding_authority",
            return_value=self.runner_direct,
        ) as direct, patch(
            "x5crop.detection.photo_geometry.detector.assess_global_lattice_authority",
            return_value=self.runner_authority,
        ) as lattice:
            result = _placements(self.prepared, source_geometry=object())
        self.assertEqual(compose.call_count, 2)
        self.assertIs(result[0].sequence_fit, self.phase.best)
        self.assertIs(result[1].sequence_fit, self.phase.runner_up)
        return result, direct, lattice

    def test_each_hypothesis_uses_own_authority_and_foreign_width_is_removed(self) -> None:
        result, direct, lattice = self.route()
        self.assertIs(result[0].global_lattice_authority, self.primary_authority)
        self.assertIs(result[1].global_lattice_authority, self.runner_authority)
        direct.assert_called_once_with(
            self.phase.runner_up, self.prepared.phase_input.observations,
            self.prepared.phase_input.separator_bands,
            self.prepared.phase_input.sequence_measurement_sets,
            outer_material_boundaries=self.prepared.phase_input.outer_material_boundaries,
            authorized_source_frame_width_px=None,
        )
        lattice.assert_called_once()
        self.assertIs(lattice.call_args.args[0], self.phase.runner_up)
        self.assertEqual(lattice.call_args.args[1].global_lattice_evidence.frame_width_observation_ids, ())
        self.assertIs(lattice.call_args.kwargs["direct_role_authority"], self.runner_direct)
        self.assertEqual(len(self.prepared.phase_input.global_lattice_evidence.frame_width_observation_ids), 1)
        self.assertEqual(self.phase.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(self.phase.failure_kind, PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS)

    def test_matching_width_keeps_exact_input_and_registered_rank(self) -> None:
        self.width.matches_placement.return_value = True
        _, direct, lattice = self.route()
        self.width.matches_placement.assert_called_once_with(self.phase.runner_up)
        self.assertIs(direct.call_args.kwargs["authorized_source_frame_width_px"], self.width.width_px)
        self.assertIs(lattice.call_args.args[1], self.prepared.phase_input)

    def test_other_phase_failures_do_not_consume_conditional_constraints(self) -> None:
        for failure in PhaseFailureKind:
            if failure == PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS:
                continue
            with self.subTest(failure=failure):
                self.phase.failure_kind = failure
                result, direct, lattice = self.route()
                self.assertTrue(all(item.global_lattice_authority is None for item in result))
                direct.assert_not_called()
                lattice.assert_not_called()

    def test_failed_projection_cannot_supply_conditional_constraints(self) -> None:
        for outcome in (Projection.DIRECT_ROLE_CONTRADICTION, Projection.DIRECT_LATTICE_CONFLICT,
                        Projection.REFIT_UNAVAILABLE, Projection.DISCRETE_IDENTITY_CHANGED):
            with self.subTest(outcome=outcome):
                self.phase.best_phase_candidate_authority_projection.outcome = outcome
                self.phase.runner_phase_candidate_authority_projection.outcome = outcome
                result, direct, lattice = self.route()
                self.assertTrue(all(item.global_lattice_authority is None for item in result))
                direct.assert_not_called()
                lattice.assert_not_called()

    def test_unavailable_direct_or_lattice_keeps_unconstrained_hypothesis(self) -> None:
        self.phase.direct_role_binding_authority.state = EvidenceState.UNAVAILABLE
        self.runner_direct.state = EvidenceState.UNAVAILABLE
        result, direct, lattice = self.route()
        self.assertTrue(all(item.global_lattice_authority is None for item in result))
        direct.assert_called_once()
        lattice.assert_not_called()
        self.runner_direct.state = EvidenceState.SUPPORTED
        self.runner_authority.state = EvidenceState.UNAVAILABLE
        result, _, lattice = self.route()
        self.assertIsNone(result[1].global_lattice_authority)
        lattice.assert_called_once()

    def test_resolved_phase_keeps_existing_primary_only_sequence_behavior(self) -> None:
        self.phase.status = PhaseFitStatus.RESOLVED
        self.phase.failure_kind = None
        result, direct, lattice = self.route()
        self.assertIs(result[0].global_lattice_authority, self.primary_authority)
        self.assertIsNone(result[1].global_lattice_authority)
        direct.assert_not_called()
        lattice.assert_not_called()
