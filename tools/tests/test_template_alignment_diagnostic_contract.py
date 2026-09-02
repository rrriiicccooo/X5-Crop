from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.template_alignment_diagnostic import (
    template_alignment_diagnostic,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_model import (
    SequenceBindingUse,
    SeparatorRelationKind,
    SeparatorRelation,
    SourceFrameWidthAuthorityBasis,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    apply_placement_source_frame_width,
    SourceFrameWidthAuthority,
    SourceFrameWidthAuthorityPlacementScope,
)
from x5crop.detection.photo_geometry.template_phase import (
    finalize_template_phase_candidate,
    fit_template_phase,
    fit_template_phase_candidate_with_adjacency_relations,
    refine_template_phase_with_source_frame_width,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_residual import ResidualPattern
from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    unavailable_nominal_grid_prior,
)


class TemplateAlignmentDiagnosticContractTest(unittest.TestCase):
    @staticmethod
    def _shift_observation(observation, delta: float):
        interval = FiniteInterval(
            observation.canonical_position_px + delta - 0.5,
            observation.canonical_position_px + delta + 0.5,
        )
        return replace(
            observation,
            discovery_interval_px=interval,
            canonical_position_px=observation.canonical_position_px + delta,
            fit_position_interval_px=interval,
            full_position_interval_px=interval,
        )

    def test_normal_fit_reports_direct_role_residuals_and_unbound_noise(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
                ("unbound", 700.0),
            )
        )
        phase = fit_template_phase(observations, template(2))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        diagnostic = template_alignment_diagnostic(phase, observations)
        self.assertEqual(diagnostic.pattern, ResidualPattern.NORMAL)
        self.assertEqual(len(diagnostic.role_residuals), 4)
        self.assertEqual(
            diagnostic.unbound_direct_observation_ids,
            (ObservationId("unbound"),),
        )
        self.assertLessEqual(
            diagnostic.maximum_absolute_role_residual_px or 0.0,
            1.0e-7,
        )

    def test_diagnostic_exposes_unknown_rank_and_adjacency_corridor(self) -> None:
        observations = tuple(
            replace(
                edge(name, coordinate),
                qualified_anchor_roles=(role,),
            )
            for name, coordinate, role in (
                ("start:1", 40.0, BoundaryRole.START),
                ("end:1", 140.0, BoundaryRole.END),
                ("start:2", 160.0, BoundaryRole.START),
                ("end:2", 260.0, BoundaryRole.END),
                ("start:3", 280.0, BoundaryRole.START),
            )
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=template(3),
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(
                template(3)
            ),
            scale_px_per_mm=None,
            holder_span_px=FiniteInterval(0.0, 400.0),
            phase_authority_px=FiniteInterval.exact(40.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "alignment-coverage",
                    FiniteInterval(0.0, 400.0),
                ),
            ),
        )
        candidate = fit_template_phase_candidate_with_adjacency_relations(
            phase_input
        )
        fit = candidate.result.best
        self.assertIsNotNone(fit)
        assert fit is not None
        width_ids = tuple(
            sorted(
                (
                    ObservationId("start:1"),
                    ObservationId("end:1"),
                    ObservationId("start:2"),
                    ObservationId("end:2"),
                ),
                key=str,
            )
        )
        source_width = SourceFrameWidthAuthority(
            authority_id="alignment-independent-source-width",
            state=EvidenceState.SUPPORTED,
            placement_scope=(
                SourceFrameWidthAuthorityPlacementScope.RESOLVED_PLACEMENT
            ),
            placement_integer_slot_offset=(
                fit.phase_lattice_fit.integer_slot_offset
            ),
            placement_phase_anchor_observation_ids=tuple(
                binding.observation_id
                if binding is not None
                and binding.use == SequenceBindingUse.PHASE_ANCHOR
                else None
                for binding in fit.role_bindings
            ),
            supporting_role_observation_ids=tuple(
                binding.observation_id
                if binding is not None
                and binding.observation_id in set(width_ids)
                else None
                for binding in fit.role_bindings
            ),
            basis=(
                SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES
            ),
            supporting_frame_ordinals=(1, 2),
            supporting_constraint_ids=(),
            width_px=FiniteInterval(
                fit.pitch_fit.frame_width_px.minimum,
                fit.pitch_fit.frame_width_px.maximum,
            ),
            canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
            observation_ids=width_ids,
            failure_kind=None,
            reason=None,
        )
        selected = apply_placement_source_frame_width(
            candidate.result,
            source_width,
        )
        selected = refine_template_phase_with_source_frame_width(
            selected,
            source_width,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
        )
        phase = finalize_template_phase_candidate(
            replace(candidate, result=selected),
            phase_input,
            source_frame_width_authority=source_width,
        )
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)

        diagnostic = template_alignment_diagnostic(phase, observations)

        assert diagnostic.global_lattice_authority is not None
        self.assertEqual(
            diagnostic.global_lattice_authority.joint_constraint_rank,
            3,
        )
        self.assertEqual(len(diagnostic.adjacency_observation_coverage), 2)
        self.assertTrue(
            all(
                item.state.value == "complete"
                for item in diagnostic.adjacency_observation_coverage
            )
        )
        assert diagnostic.direct_role_binding_authority is not None
        self.assertEqual(
            diagnostic.direct_role_binding_authority.state.value,
            "supported",
        )
        assert diagnostic.outer_frame_observation_authority is not None
        self.assertEqual(
            diagnostic.outer_frame_observation_authority.state.value,
            "supported",
        )
        assert diagnostic.frame_width_inference is not None
        self.assertEqual(
            diagnostic.frame_width_inference.state.value,
            "supported",
        )

    def test_one_direct_suffix_shift_is_named_without_new_search(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 170.0),
                ("end:2", 270.0),
            )
        )
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval.exact(10.0),
            canonical_delta_px=10.0,
            separator_band_observation_id=ObservationId("separator:1"),
            end_edge_observation_id=ObservationId("end:1"),
            next_start_edge_observation_id=ObservationId("start:2"),
            signed_gap_interval_px=FiniteInterval.exact(30.0),
            canonical_signed_gap_px=30.0,
        )
        phase = fit_template_phase(
            observations,
            template(2),
            adjacency_relations=(relation,),
        )
        assert phase.best is not None
        diagnostic = template_alignment_diagnostic(phase, observations)
        self.assertEqual(
            diagnostic.pattern,
            ResidualPattern.MEASURED_RELATIONS,
        )
        self.assertEqual(diagnostic.adjacency_relations, (relation,))

    def test_direct_normal_separator_is_still_a_measured_relation(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
            )
        )
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.NORMAL,
            delta_interval_px=FiniteInterval.exact(0.0),
            canonical_delta_px=0.0,
            separator_band_observation_id=ObservationId("separator:normal"),
            end_edge_observation_id=ObservationId("end:1"),
            next_start_edge_observation_id=ObservationId("start:2"),
            signed_gap_interval_px=FiniteInterval.exact(20.0),
            canonical_signed_gap_px=20.0,
        )
        phase = fit_template_phase(
            observations,
            template(2),
            adjacency_relations=(relation,),
        )

        diagnostic = template_alignment_diagnostic(phase, observations)

        self.assertEqual(
            diagnostic.pattern,
            ResidualPattern.MEASURED_RELATIONS,
        )
        self.assertEqual(diagnostic.adjacency_relations, (relation,))
        self.assertFalse(diagnostic.adjacency_relations[0].is_anomaly)

    def test_unresolved_fit_preserves_the_minimum_reason(self) -> None:
        observations = (edge("only", 40.0),)
        phase = fit_template_phase(observations, template(2))
        phase = replace(
            phase,
            best=None,
            runner_up=None,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason="one direct phase anchor is still missing",
            failure_kind=PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE,
            winner_basis=None,
        )
        diagnostic = template_alignment_diagnostic(phase, observations)
        self.assertEqual(diagnostic.pattern, ResidualPattern.UNRESOLVED)
        self.assertEqual(
            diagnostic.unresolved_reason,
            "one direct phase anchor is still missing",
        )
        self.assertIsNone(diagnostic.absolute_phase_px)

    def test_repeated_separator_shape_conflicts_remain_explicit_diagnostics(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
                ("start:3", 280.0),
                ("end:3", 380.0),
            )
        )
        phase = fit_template_phase(observations, template(3))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        shifted = (
            observations[0],
            self._shift_observation(observations[1], 10.0),
            self._shift_observation(observations[2], -10.0),
            self._shift_observation(observations[3], 10.0),
            self._shift_observation(observations[4], -10.0),
            observations[5],
        )
        bands = (
            separator(
                "separator:shape:1",
                shifted[1],
                shifted[2],
                FiniteInterval.exact(0.0),
            ),
            separator(
                "separator:shape:2",
                shifted[3],
                shifted[4],
                FiniteInterval.exact(0.0),
            ),
        )
        diagnostic = template_alignment_diagnostic(
            phase,
            shifted,
            bands,
        )
        self.assertEqual(
            diagnostic.pattern,
            ResidualPattern.NORMAL,
        )
        self.assertEqual(len(diagnostic.incompatible_separator_support_ids), 2)
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(phase.best)

    def test_one_separator_width_departure_does_not_invent_an_advance(self) -> None:
        observations = tuple(
            edge(name, coordinate)
            for name, coordinate in (
                ("start:1", 40.0),
                ("end:1", 140.0),
                ("start:2", 160.0),
                ("end:2", 260.0),
            )
        )
        phase = fit_template_phase(observations, template(2))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        shifted = (
            observations[0],
            self._shift_observation(observations[1], 10.0),
            self._shift_observation(observations[2], -10.0),
            observations[3],
        )
        band = separator(
            "separator:one-width-departure",
            shifted[1],
            shifted[2],
            FiniteInterval.exact(0.0),
        )
        diagnostic = template_alignment_diagnostic(
            phase,
            shifted,
            (band,),
        )
        self.assertEqual(diagnostic.pattern, ResidualPattern.NORMAL)
        self.assertEqual(
            diagnostic.incompatible_separator_support_ids,
            (band.observation_id,),
        )
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)


if __name__ == "__main__":
    unittest.main()
