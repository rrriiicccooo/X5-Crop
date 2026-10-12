from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_edge as edge,
    phase_sequence_measurement,
    phase_template as template,
    transformed_phase_edge as transformed_edge,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.template_model import (
    LatticeParameterFitBasis,
    PhaseLatticeAuthority,
    SequenceBindingUse,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase import fit_template_phase_with_adjacency_relations
from x5crop.detection.photo_geometry.template_phase_candidate_model import _BoundFit
from x5crop.detection.photo_geometry.template_phase_observations import _facts
from x5crop.detection.photo_geometry.template_phase_projection import project_candidate_to_authorized_direct_roles
from x5crop.detection.photo_geometry.template_phase_model import (
    GlobalLatticeAuthorityBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from tools.tests.phase_test_support import _fit_with_independent_source_width


class TemplatePhaseGridContractTest(unittest.TestCase):
    def test_consecutive_unobserved_adjacencies_use_proven_grid_when_covered(
        self,
    ) -> None:
        specs = (
            ("gap:start:1", 40.0, BoundaryRole.START),
            ("gap:start:2", 160.0, BoundaryRole.START),
            ("gap:end:2", 260.0, BoundaryRole.END),
            ("gap:start:3", 280.0, BoundaryRole.START),
            ("gap:end:3", 380.0, BoundaryRole.END),
            ("gap:start:4", 400.0, BoundaryRole.START),
            ("gap:start:5", 520.0, BoundaryRole.START),
            ("gap:end:6", 740.0, BoundaryRole.END),
        )
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for identity, coordinate, role in specs
        )

        phase_input = TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(6),
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                    template(6)
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 800.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "complete-consecutive-gap",
                        FiniteInterval(0.0, 800.0),
                    ),
                ),
            )
        result = _fit_with_independent_source_width(
            phase_input,
            tuple(
                ObservationId(identity)
                for identity in (
                    "gap:start:2",
                    "gap:end:2",
                    "gap:start:3",
                    "gap:end:3",
                )
            ),
            (2, 3),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.phase_support_locations,
            (0, 1, 2, 3, 4, 6),
        )
        assert result.best.frame_width_inference is not None
        self.assertEqual(
            result.best.frame_width_inference.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            result.best.frame_width_inference.supporting_frame_ordinals,
            (2, 3),
        )
        assert result.global_lattice_authority is not None
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 3)
        self.assertEqual(
            result.global_lattice_authority.basis,
            GlobalLatticeAuthorityBasis.DIRECT_ROLE_SYSTEM,
        )
        self.assertTrue(
            all(
                item.state.value == "complete"
                for item in result.adjacency_observation_coverage
                if item.normal_inference_required
            )
        )
        assert result.outer_frame_observation_authority is not None
        self.assertEqual(
            result.outer_frame_observation_authority.state.value,
            "supported",
        )

    def test_calibrated_grid_authorizes_an_unobserved_internal_frame(
        self,
    ) -> None:
        specs = (
            ("internal:start:1", 40.0, BoundaryRole.START),
            ("internal:start:2", 160.0, BoundaryRole.START),
            ("internal:end:2", 260.0, BoundaryRole.END),
            ("internal:start:3", 280.0, BoundaryRole.START),
            ("internal:end:3", 380.0, BoundaryRole.END),
            ("internal:start:4", 400.0, BoundaryRole.START),
            ("internal:end:6", 740.0, BoundaryRole.END),
        )
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for identity, coordinate, role in specs
        )

        phase_input = TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(6),
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                    template(6)
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 800.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "complete-internal-frame-gap",
                        FiniteInterval(0.0, 800.0),
                    ),
                ),
            )
        result = _fit_with_independent_source_width(
            phase_input,
            tuple(
                ObservationId(identity)
                for identity in (
                    "internal:start:2",
                    "internal:end:2",
                    "internal:start:3",
                    "internal:end:3",
                )
            ),
            (2, 3),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNone(result.failure_kind)
        assert result.best is not None
        self.assertEqual(
            result.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
        )
        self.assertIsNotNone(result.best.calibrated_nominal_grid_fit_state)
        assert result.calibrated_nominal_grid_evidence is not None
        self.assertEqual(
            result.calibrated_nominal_grid_evidence.state,
            EvidenceState.SUPPORTED,
        )
        self.assertIsNone(
            result.calibrated_nominal_grid_evidence.failure_kind
        )
        self.assertEqual(
            result.calibrated_nominal_grid_evidence.unobserved_frame_ordinals,
            (5,),
        )

    def test_calibrated_grid_authorizes_an_unobserved_outer_frame(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for identity, coordinate, role in (
                ("start:2", 160.0, BoundaryRole.START),
                ("end:2", 260.0, BoundaryRole.END),
                ("start:3", 280.0, BoundaryRole.START),
                ("end:3", 380.0, BoundaryRole.END),
                ("start:4", 400.0, BoundaryRole.START),
                ("end:6", 740.0, BoundaryRole.END),
            )
        )

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(6),
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                    template(6)
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 800.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "complete-unanchored-outer-frame",
                        FiniteInterval(0.0, 800.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNone(result.failure_kind)
        assert result.best is not None
        self.assertEqual(
            result.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
        )
        assert result.calibrated_nominal_grid_evidence is not None
        self.assertEqual(
            result.calibrated_nominal_grid_evidence.state,
            EvidenceState.SUPPORTED,
        )
        self.assertIsNone(
            result.calibrated_nominal_grid_evidence.failure_kind
        )
        self.assertEqual(
            result.calibrated_nominal_grid_evidence.unobserved_frame_ordinals,
            (1, 5),
        )
        self.assertGreater(result.receipt.candidate_nominal_grid_solve_count, 0)
        self.assertEqual(
            result.receipt.candidate_nominal_grid_solve_count,
            result.receipt.candidate_nominal_grid_solve_success_count,
        )
        assert result.global_lattice_authority is not None
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 3)
        self.assertTrue(
            all(
                item.state.value == "complete"
                for item in result.adjacency_observation_coverage
            )
        )
        assert result.outer_frame_observation_authority is not None
        self.assertEqual(
            result.outer_frame_observation_authority.state.value,
            "unavailable",
        )
        self.assertFalse(
            result.outer_frame_observation_authority.first_frame_observation_ids
        )
        self.assertTrue(
            result.outer_frame_observation_authority.last_frame_observation_ids
        )

    def test_calibrated_grid_closes_rank_two_direct_system(self) -> None:
        observations = tuple(
            replace(
                edge(f"start:{slot}", 40.0 + 120.0 * slot),
                qualified_anchor_roles=(BoundaryRole.START,),
            )
            for slot in range(4)
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                    template(4)
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 520.0),
                phase_authority_px=FiniteInterval.exact(40.0),
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "rank-two-complete",
                        FiniteInterval(0.0, 520.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
        )
        assert result.calibrated_nominal_grid_evidence is not None
        self.assertEqual(
            result.calibrated_nominal_grid_evidence.state,
            EvidenceState.SUPPORTED,
        )
        assert result.global_lattice_authority is not None
        self.assertEqual(
            result.global_lattice_authority.direct_role_constraint_rank,
            2,
        )
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 2)

    def test_calibrated_grid_keeps_late_short_edge_validation_only(
        self,
    ) -> None:
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(98.0, 102.0),
        )
        direction = FiniteInterval.exact(0.0)
        registered_traces = tuple(range(0, 101, 10))

        def local(
            identity: str,
            coordinate: float,
            role: BoundaryRole,
            *,
            source_wide: bool = False,
        ) -> BoundaryEdgeObservation:
            traces = (0, 50, 100) if source_wide else (40, 80)
            support = len(traces) / len(registered_traces)
            return replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=traces,
                support_fraction=support,
                continuous_support_fraction=support,
                fit_residual_px=0.0 if source_wide else 20.0,
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=direction,
                full_direction_interval_degrees=direction,
                full_position_interval_px=(
                    FiniteInterval(coordinate - 0.2, coordinate + 0.2)
                    if source_wide
                    else FiniteInterval(coordinate - 1.2, coordinate + 1.2)
                ),
            )

        anchor = replace(
            local(
                "late-projection:anchor:start:1",
                100.0,
                BoundaryRole.START,
                source_wide=True,
            ),
            trace_coordinates_px=registered_traces,
            support_fraction=1.0,
            continuous_support_fraction=1.0,
        )
        weak_edges = (
            replace(
                local(
                    "late-projection:authorized-local:end:1",
                    201.0,
                    BoundaryRole.END,
                    source_wide=True,
                ),
                fit_residual_px=20.0,
            ),
            local(
                "late-projection:weak:start:2",
                221.0,
                BoundaryRole.START,
            ),
            local(
                "late-projection:weak:end:2",
                321.0,
                BoundaryRole.END,
            ),
        )

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=(anchor, *weak_edges),
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                    spec
                ),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=FiniteInterval(0.0, 360.0),
                phase_authority_px=FiniteInterval.exact(100.0),
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "late-selected-grid-projection",
                        FiniteInterval(0.0, 360.0),
                        trace_positions_px=registered_traces,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(_facts((weak_edges[0],))[0].direct)
        self.assertEqual(result.best.role_bindings[1].use, SequenceBindingUse.LOCAL_REFINEMENT)
        self.assertEqual(result.best.pitch_fit.observation_ids, (anchor.observation_id,))
        self.assertEqual(result.best.calibrated_nominal_grid_fit_state.retained_direct_constraint_rank, 1)
        self.assertEqual(
            result.best.binding_observation_ids,
            (
                anchor.observation_id,
                weak_edges[0].observation_id,
                None,
                None,
            ),
        )
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
        )
        self.assertEqual(
            tuple(
                (item.role_index, item.observation_id)
                for item in projection.projected_out_bindings
            ),
            tuple(
                (role_index, observation.observation_id)
                for role_index, observation in enumerate(
                    weak_edges[1:],
                    start=2,
                )
            ),
        )
        assert result.direct_role_binding_authority is not None
        self.assertEqual(
            result.direct_role_binding_authority.state,
            EvidenceState.SUPPORTED,
        )
        with self.assertRaisesRegex(ValueError, "unknown direct edge"):
            project_candidate_to_authorized_direct_roles(
                _BoundFit(result.best, True), result.direct_role_binding_authority,
                _facts((anchor,)), (), spec.roles, spec,
                result.best.adjacency_relations, result.best.pitch_fit.pitch_interval_px,
                FiniteInterval.exact(100.0), None, calibrated_nominal_grid_prior(spec),
            )
        self.assertEqual(
            result.receipt.selected_direct_role_projection_evaluation_count,
            1,
        )
        self.assertEqual(
            result.receipt.selected_direct_role_projection_binding_count,
            2,
        )
        self.assertEqual(result.receipt.selected_nominal_grid_solve_count, 1)
        self.assertEqual(
            result.receipt.selected_nominal_grid_solve_success_count,
            1,
        )

        conflicting_edges = (
            weak_edges[0],
            local(
                "late-projection:conflict:start:2",
                222.0,
                BoundaryRole.START,
            ),
            weak_edges[2],
        )
        conflict = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=(anchor, *conflicting_edges),
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=(
                    calibrated_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=FiniteInterval(0.0, 360.0),
                phase_authority_px=FiniteInterval.exact(100.0),
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "late-selected-grid-validation-conflict",
                        FiniteInterval(0.0, 360.0),
                        trace_positions_px=registered_traces,
                    ),
                ),
            )
        )
        self.assertEqual(conflict.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            conflict.failure_kind,
            PhaseFailureKind.CALIBRATED_NOMINAL_GRID_CONFLICT,
        )
        assert conflict.best_phase_candidate_authority_projection is not None
        self.assertEqual(
            conflict.best_phase_candidate_authority_projection.outcome,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT,
        )
        self.assertIn("role indices: 2", conflict.ambiguity_reason or "")

    def test_direct_rank_lattice_keeps_late_short_edge_validation_only(
        self,
    ) -> None:
        spec = replace(
            template(3),
            frame_width_px=PositiveInterval(98.0, 102.0),
        )
        direction = FiniteInterval.exact(0.0)

        def local(
            identity: str,
            coordinate: float,
            role: BoundaryRole,
            *,
            source_wide: bool = False,
        ) -> BoundaryEdgeObservation:
            traces = (0, 10, 20) if source_wide else (10, 20)
            support = 1.0 if source_wide else 2.0 / 3.0
            return replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=traces,
                support_fraction=support,
                continuous_support_fraction=support,
                fit_residual_px=0.0 if source_wide else 20.0,
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=direction,
                full_direction_interval_degrees=direction,
                full_position_interval_px=FiniteInterval(
                    coordinate - (0.2 if source_wide else 1.2),
                    coordinate + (0.2 if source_wide else 1.2),
                ),
            )

        direct_edges = tuple(
            local(identity, coordinate, role, source_wide=True)
            for identity, coordinate, role in (
                ("late-direct:start:1", 100.0, BoundaryRole.START),
                ("late-direct:end:1", 200.0, BoundaryRole.END),
                ("late-direct:start:2", 220.0, BoundaryRole.START),
                ("late-direct:end:2", 320.0, BoundaryRole.END),
                ("late-direct:start:3", 340.0, BoundaryRole.START),
            )
        )
        weak_end = local(
            "late-direct:weak:end:3",
            441.0,
            BoundaryRole.END,
        )

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=(*direct_edges, weak_end),
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(
                    spec
                ),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=FiniteInterval(0.0, 480.0),
                phase_authority_px=FiniteInterval.exact(100.0),
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "late-selected-direct-projection",
                        FiniteInterval(0.0, 480.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.FRAME_WIDTH_INFERENCE_UNAVAILABLE,
        )
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None and result.best is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.PROJECTED,
        )
        self.assertEqual(projection.retained_direct_constraint_rank, 3)
        self.assertEqual(
            tuple(
                (item.role_index, item.observation_id)
                for item in projection.projected_out_bindings
            ),
            ((5, weak_end.observation_id),),
        )
        self.assertIsNone(result.best.role_bindings[5])
        self.assertEqual(
            result.receipt.selected_direct_role_projection_evaluation_count,
            1,
        )
        self.assertEqual(
            result.receipt.selected_direct_role_projection_binding_count,
            1,
        )
        self.assertEqual(result.receipt.selected_nominal_grid_solve_count, 0)
        counterevidence = replace(
            projection,
            outcome=PhaseCandidateProjectionOutcome.DIRECT_LATTICE_CONFLICT,
            basis=None,
            reason="validation-only line left the direct lattice envelope",
        )
        self.assertFalse(counterevidence.eligible)

    def test_direct_phase_authority_preserves_calibrated_placement(self) -> None:
        observations = (
            edge("prior-start", 40.0),
            edge("prior-next-start", 160.0),
            edge("clutter-start", 55.0),
            edge("late-end", 260.0),
        )
        result = fit_template_phase(
            observations,
            template(2),
            phase_authority_px=FiniteInterval(38.0, 42.0),
        )
        self.assertIn(result.status, (PhaseFitStatus.RESOLVED, PhaseFitStatus.AMBIGUOUS))
        assert result.best is not None
        self.assertEqual(
            result.best.binding_observation_ids[0],
            ObservationId("prior-start"),
        )
        self.assertLessEqual(
            result.receipt.phase_hypothesis_count,
            result.receipt.observation_count * max(6, result.receipt.role_count),
        )

        shifted = fit_template_phase(
            tuple(
                edge(f"authority-shift:{index}", coordinate)
                for index, coordinate in enumerate((160.0, 260.0, 280.0, 380.0))
            ),
            template(2),
            phase_authority_px=FiniteInterval(38.0, 42.0),
        )
        self.assertEqual(shifted.status, PhaseFitStatus.RESOLVED)
        assert shifted.best is not None
        self.assertTrue(
            FiniteInterval(38.0, 42.0).contains(
                shifted.best.phase_lattice_fit.canonical_absolute_phase_px
            )
        )

    def test_phase_lattice_separates_cycle_and_integer_slot_offset(self) -> None:
        base = fit_template_phase(
            tuple(
                edge(f"base:{index}", coordinate)
                for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
            ),
            template(2),
        )
        shifted = fit_template_phase(
            tuple(
                edge(f"shifted:{index}", coordinate)
                for index, coordinate in enumerate((160.0, 260.0, 280.0, 380.0))
            ),
            template(2),
        )
        self.assertEqual(base.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(shifted.status, PhaseFitStatus.RESOLVED)
        assert base.best is not None and shifted.best is not None
        self.assertAlmostEqual(
            base.best.phase_lattice_fit.canonical_cycle_phase_px,
            shifted.best.phase_lattice_fit.canonical_cycle_phase_px,
        )
        self.assertEqual(base.best.phase_lattice_fit.integer_slot_offset, 0)
        self.assertEqual(shifted.best.phase_lattice_fit.integer_slot_offset, 1)
        self.assertAlmostEqual(
            shifted.best.phase_lattice_fit.canonical_absolute_phase_px
            - base.best.phase_lattice_fit.canonical_absolute_phase_px,
            120.0,
        )

    def test_translation_and_scale_transform_the_same_physical_answer(self) -> None:
        observations = tuple(
            edge(f"metamorphic:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
        )
        base = fit_template_phase(observations, template(2))
        translated = fit_template_phase(
            tuple(
                transformed_edge(item, offset=37.25)
                for item in observations
            ),
            template(2),
        )
        factor = 1.75
        scaled_template = TemplateSpec(
            template_id="test-template",
            frame_width_px=100.0 * factor,
            pitch_px=120.0 * factor,
            count=2,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=120.0 * factor,
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
            nominal_gap_px=20.0 * factor,
        )
        scaled = fit_template_phase(
            tuple(
                transformed_edge(item, scale=factor)
                for item in observations
            ),
            scaled_template,
        )

        for result in (base, translated, scaled):
            self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
            self.assertIsNotNone(result.best)
        assert base.best is not None
        assert translated.best is not None
        assert scaled.best is not None
        self.assertEqual(
            translated.best.binding_observation_ids,
            base.best.binding_observation_ids,
        )
        self.assertEqual(
            scaled.best.binding_observation_ids,
            base.best.binding_observation_ids,
        )
        for original, moved in zip(
            base.best.model_role_positions_px,
            translated.best.model_role_positions_px,
            strict=True,
        ):
            self.assertAlmostEqual(moved, original + 37.25)
        for original, resized in zip(
            base.best.model_role_positions_px,
            scaled.best.model_role_positions_px,
            strict=True,
        ):
            self.assertAlmostEqual(resized, original * factor)

    def test_fractional_pitch_never_accumulates_integer_rounding(self) -> None:
        width = 100.25
        pitch = 120.375
        phase = 33.125
        count = 12
        compiled = TemplateSpec(
            template_id="fractional-template",
            frame_width_px=width,
            pitch_px=pitch,
            count=count,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=pitch,
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
            nominal_gap_px=pitch - width,
        )
        observations = tuple(
            edge(
                f"fractional:{index}",
                phase + slot * pitch + (width if role else 0.0),
            )
            for slot in range(count)
            for role, index in ((False, 2 * slot), (True, 2 * slot + 1))
        )

        result = fit_template_phase(observations, compiled)

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertAlmostEqual(
            result.best.model_role_positions_px[-2],
            phase + (count - 1) * pitch,
            places=9,
        )
        self.assertAlmostEqual(
            result.best.model_role_positions_px[-1],
            phase + (count - 1) * pitch + width,
            places=9,
        )

    def test_role_free_shifted_edges_do_not_claim_an_integer_offset(self) -> None:
        constrained = replace(
            template(2),
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=120.0,
                cycle_origin_px=0.0,
                minimum_slot_offset=0,
                maximum_slot_offset=0,
            ),
        )
        result = fit_template_phase(
            tuple(
                edge(f"shifted:{index}", coordinate)
                for index, coordinate in enumerate(
                    (160.0, 260.0, 280.0, 380.0)
                )
            ),
            constrained,
        )
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        assert result.best is not None
        self.assertEqual(result.best.phase_lattice_fit.integer_slot_offset, 0)
        self.assertEqual(result.best.unbound_role_indices[:2], (0, 1))
        self.assertAlmostEqual(
            result.best.phase_lattice_fit.canonical_absolute_phase_px,
            40.0,
        )

    def test_clutter_does_not_move_global_fit(self) -> None:
        true_edges = (40.0, 140.0, 160.0, 260.0, 280.0, 380.0)
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((*true_edges, 999.0))
        )
        result = fit_template_phase(observations, template(3))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertAlmostEqual(
            result.best.phase_lattice_fit.canonical_absolute_phase_px,
            40.0,
        )
        self.assertEqual(result.best.phase_support_count, 4)

        weak_clutter = (*true_edges, 100.0)
        result = fit_template_phase(
            tuple(
                edge(
                    f"weak:{index}",
                    coordinate,
                    support_fraction=0.2 if index == len(weak_clutter) - 1 else 1.0,
                )
                for index, coordinate in enumerate(weak_clutter)
            ),
            template(3),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(result.best.phase_support_count, 4)

    def test_equal_supported_discrete_lattices_remain_ambiguous_after_joint_fit(
        self,
    ) -> None:
        coordinates = (10.0, 126.0, 227.0, 247.0, 350.0, 370.0, 470.0)
        roles = (
            BoundaryRole.START,
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.START,
            BoundaryRole.END,
        )
        observations = tuple(
            replace(
                edge(f"contradiction:{index}", coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for index, (coordinate, role) in enumerate(
                zip(coordinates, roles, strict=True)
            )
        )

        result = fit_template_phase(observations, template(3))

        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
        )
        self.assertIsNone(result.winner_basis)
        assert result.best is not None and result.runner_up is not None
        self.assertEqual(
            result.best.phase_support_count,
            result.runner_up.phase_support_count,
        )

    def test_residual_limit_is_inclusive_across_numeric_backends(self) -> None:
        coordinates = (10.0, 127.0, 227.0, 247.0, 350.0, 370.0, 470.0)
        roles = (
            BoundaryRole.START,
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.START,
            BoundaryRole.END,
        )
        observations = tuple(
            replace(
                edge(f"threshold:{index}", coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for index, (coordinate, role) in enumerate(
                zip(coordinates, roles, strict=True)
            )
        )

        result = fit_template_phase(observations, template(3))

        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
        )
        assert result.best is not None and result.runner_up is not None
        self.assertEqual(result.best.phase_support_count, 4)
        self.assertEqual(result.runner_up.phase_support_count, 4)
        self.assertAlmostEqual(result.runner_up.residual_sum_px, 9.0)


if __name__ == "__main__":
    unittest.main()
