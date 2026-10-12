from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_edge as edge,
    placement_sequence,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import BoundaryEvidenceState, BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.template_model import SequenceBindingUse
from x5crop.detection.photo_geometry.template_direct_role_authority import assess_direct_role_binding_authority
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase import fit_template_phase_with_adjacency_relations
from x5crop.detection.photo_geometry.template_lattice_authority import direct_role_constraint_rank
from x5crop.detection.photo_geometry.template_phase_candidate_model import (
    _BoundFit,
    _phase_residual_compatible,
)
from x5crop.detection.photo_geometry.template_phase_observations import _facts
from x5crop.detection.photo_geometry.template_phase_projection import project_candidate_to_authorized_direct_roles
from x5crop.detection.photo_geometry.template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseWinnerBasis,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_residual import derive_candidate_separator_relations
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from tools.tests.phase_test_support import _phase_candidate_group


class TemplatePhaseCandidateAuthorityContractTest(unittest.TestCase):
    def test_pure_cross_height_edge_has_no_direct_role_authority(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                measurement_basis=(
                    BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
                    if identity == "joint:start:1"
                    else BoundaryEdgeMeasurementBasis.DIRECT_TRACE
                ),
            )
            for identity, coordinate, role in (
                ("joint:start:1", 40.0, BoundaryRole.START),
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
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(6)),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 800.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "cross-height-outer-anchor",
                        FiniteInterval(0.0, 800.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE,
        )
        assert result.direct_role_binding_authority is not None
        self.assertEqual(
            result.direct_role_binding_authority.unsupported_role_indices,
            (0,),
        )

    def test_cross_height_separator_pair_authorizes_both_roles_once(
        self,
    ) -> None:
        start1 = replace(
            edge("start:1", 40.0),
            qualified_anchor_roles=(BoundaryRole.START,),
            polarity=1,
        )
        end1 = replace(
            edge("aggregate:end:1", 140.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
            measurement_basis=(
                BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )
        start2 = replace(
            edge("aggregate:start:2", 160.0),
            qualified_anchor_roles=(BoundaryRole.START,),
            polarity=1,
            measurement_basis=(
                BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            ),
        )
        end2 = replace(
            edge("end:2", 260.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
        )
        spec = template(2)

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=(start1, end1, start2, end2),
                separator_bands=(
                    separator(
                        "separator:aggregate-pair",
                        end1,
                        start2,
                        FiniteInterval(19.0, 21.0),
                    ),
                ),
                template=spec,
                calibrated_nominal_grid_prior=(
                    unavailable_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=PositiveInterval.exact(10.0),
                holder_span_px=FiniteInterval(0.0, 300.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "cross-height-separator-pair",
                        FiniteInterval(0.0, 300.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.direct_role_binding_authority is not None
        aggregate_facts = tuple(
            item
            for item in result.direct_role_binding_authority.facts
            if item.role_index in {1, 2}
        )
        self.assertEqual(len(aggregate_facts), 2)
        self.assertEqual(
            tuple(
                tuple(basis.value for basis in item.bases)
                for item in aggregate_facts
            ),
            (("separator_pair",), ("separator_pair",)),
        )

    def test_short_unpaired_edge_cannot_own_a_direct_role_coordinate(self) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=(
                    (10, 20) if identity.startswith("short:") else (0, 10, 20)
                ),
                support_fraction=(
                    2.0 / 3.0 if identity.startswith("short:") else 1.0
                ),
                continuous_support_fraction=(
                    2.0 / 3.0 if identity.startswith("short:") else 1.0
                ),
            )
            for identity, coordinate, role in (
                ("start:1", 40.0, BoundaryRole.START),
                ("end:1", 140.0, BoundaryRole.END),
                ("start:2", 160.0, BoundaryRole.START),
                ("end:2", 260.0, BoundaryRole.END),
                ("short:start:3", 280.0, BoundaryRole.START),
                ("start:4", 400.0, BoundaryRole.START),
                ("end:4", 500.0, BoundaryRole.END),
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(
                    template(4)
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 540.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "short-unpaired-direct-role",
                        FiniteInterval(0.0, 540.0),
                    ),
                ),
                global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                    frame_width_observation_ids=tuple(
                        ObservationId(identity)
                        for identity in (
                            "start:1",
                            "end:1",
                            "start:2",
                            "end:2",
                        )
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE,
        )
        assert result.direct_role_binding_authority is not None
        self.assertEqual(
            result.direct_role_binding_authority.unsupported_role_indices,
            (4,),
        )

    def test_candidate_authority_rejects_an_unauthorized_discrete_runner(
        self,
    ) -> None:
        observations = (
            *_phase_candidate_group("supported", 0.0),
            *_phase_candidate_group("short", 5.0, short=True),
        )
        result = fit_template_phase(
            observations,
            template(2),
            holder_span_px=FiniteInterval(0.0, 320.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "candidate-direct-role-authority",
                    FiniteInterval(0.0, 320.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(
            result.winner_basis,
            PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY,
        )
        self.assertIsNotNone(result.runner_up)
        assert result.best_phase_candidate_authority_projection is not None
        assert result.runner_phase_candidate_authority_projection is not None
        self.assertEqual(
            result.best_phase_candidate_authority_projection
            .input_direct_role_authority.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            result.runner_phase_candidate_authority_projection
            .input_direct_role_authority.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            result.receipt.candidate_direct_role_authority_evaluation_count,
            2,
        )
        self.assertEqual(
            result.receipt.candidate_direct_role_authority_terminal_count,
            1,
        )
        self.assertEqual(
            result.receipt.candidate_direct_role_authority_role_check_count,
            8,
        )

    def test_candidate_projection_removes_only_one_unavailable_phase_anchor(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=((10, 20) if weak else (0, 10, 20)),
                support_fraction=(2.0 / 3.0 if weak else 1.0),
                continuous_support_fraction=(2.0 / 3.0 if weak else 1.0),
            )
            for identity, coordinate, role, weak in (
                ("start:1", 40.0, BoundaryRole.START, False),
                ("end:1", 140.0, BoundaryRole.END, False),
                ("start:2", 160.0, BoundaryRole.START, False),
                ("end:2", 260.0, BoundaryRole.END, False),
                ("weak:start:3", 280.0, BoundaryRole.START, True),
                ("end:3", 380.0, BoundaryRole.END, False),
            )
        )
        result = fit_template_phase(
            observations,
            template(3),
            holder_span_px=FiniteInterval(0.0, 420.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "candidate-projection-rank-three",
                    FiniteInterval(0.0, 420.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None and result.best is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.PROJECTED,
        )
        self.assertEqual(projection.retained_direct_constraint_rank, 3)
        self.assertEqual(
            tuple(item.role_index for item in projection.projected_out_bindings),
            (4,),
        )
        self.assertIsNone(result.best.role_bindings[4])
        self.assertEqual(
            tuple(
                binding.canonical_position_px
                for index, binding in enumerate(result.best.role_bindings)
                if index != 4 and binding is not None
            ),
            (40.0, 140.0, 160.0, 260.0, 380.0),
        )
        self.assertGreater(
            result.receipt.candidate_direct_role_projection_success_count,
            0,
        )

    def test_measured_separator_projection_uses_the_current_constraint_rank(
        self,
    ) -> None:
        spec = template(2)
        observations = tuple(
            edge(f"measured-rank:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 110.0, 128.0, 228.0))
        )
        measurements = (
            phase_sequence_measurement(
                "measured-rank", FiniteInterval(0.0, 260.0)
            ),
        )
        initial = fit_template_phase(
            observations, spec, sequence_measurement_sets=measurements
        )
        assert initial.best is not None
        band = separator(
            "measured-rank:band", observations[1], observations[2],
            FiniteInterval(17.8, 18.2),
        )
        authority = assess_direct_role_binding_authority(
            initial.best, observations, (band,), measurements
        )
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(direct_role_constraint_rank(initial.best), 3)
        relations = derive_candidate_separator_relations(
            initial.best, authority, (band,), FiniteInterval.exact(120.0)
        )
        self.assertEqual(len(relations), 1)
        for prior, outcome in (
            (
                None,
                PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_UNAVAILABLE,
            ),
            (
                calibrated_nominal_grid_prior(spec),
                PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
            ),
        ):
            with self.subTest(calibrated=prior is not None):
                projected, receipt = project_candidate_to_authorized_direct_roles(
                    _BoundFit(initial.best, True), authority, _facts(observations),
                    (), spec.roles, spec, relations, FiniteInterval.exact(120.0),
                    None, None, prior,
                )
                self.assertEqual(receipt.retained_direct_constraint_rank, 2)
                self.assertEqual(receipt.outcome, outcome)
                if prior is None:
                    self.assertIsNone(projected)
                else:
                    assert projected is not None
                    self.assertEqual(
                        projected.fit.role_bindings,
                        initial.best.role_bindings,
                    )

    def test_candidate_separator_relation_requires_strictly_positive_gap(self) -> None:
        observations = tuple(
            edge(f"contact-inclusive:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 110.0, 130.0, 230.0))
        )
        measurements = (
            phase_sequence_measurement(
                "contact-inclusive", FiniteInterval(0.0, 260.0)
            ),
        )
        initial = fit_template_phase(
            observations, template(2), sequence_measurement_sets=measurements
        )
        assert initial.best is not None
        for minimum, expected_count in ((0.0, 0), (0.1, 1)):
            with self.subTest(minimum=minimum):
                band = separator(
                    "contact-inclusive:band", observations[1], observations[2],
                    FiniteInterval(minimum, 20.2),
                )
                authority = assess_direct_role_binding_authority(
                    initial.best, observations, (band,), measurements
                )
                relations = derive_candidate_separator_relations(
                    initial.best, authority, (band,), FiniteInterval.exact(120.0)
                )
                self.assertEqual(len(relations), expected_count)

    def test_grid_refit_rechecks_current_residuals_in_both_directions(self) -> None:
        spec = template(2)
        observations = tuple(
            replace(
                edge(f"grid-residual:{index}", coordinate),
                full_position_interval_px=FiniteInterval(
                    coordinate - 20.0, coordinate + 20.0
                ),
            )
            for index, coordinate in enumerate((10.0, 110.0, 128.0, 228.0))
        )
        measurements = (
            phase_sequence_measurement(
                "grid-residual", FiniteInterval(0.0, 260.0)
            ),
        )
        initial = fit_template_phase(
            observations, spec, sequence_measurement_sets=measurements
        )
        assert initial.best is not None
        band = separator(
            "grid-residual:band", observations[1], observations[2],
            FiniteInterval(17.8, 18.2),
        )
        authority = assess_direct_role_binding_authority(
            initial.best, observations, (band,), measurements
        )
        relations = derive_candidate_separator_relations(
            initial.best, authority, (band,), FiniteInterval.exact(120.0)
        )
        for old_verdict, phase_authority, expected in (
            (False, None, True),
            (True, FiniteInterval.exact(25.0), False),
        ):
            with self.subTest(old_verdict=old_verdict):
                projected, receipt = project_candidate_to_authorized_direct_roles(
                    _BoundFit(initial.best, old_verdict), authority,
                    _facts(observations), (), spec.roles, spec, relations,
                    FiniteInterval.exact(120.0), phase_authority, None,
                    calibrated_nominal_grid_prior(spec),
                )
                self.assertEqual(
                    receipt.outcome,
                    PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
                )
                assert projected is not None
                self.assertEqual(projected.residual_compatible, expected)
                self.assertEqual(
                    projected.fit.role_bindings, initial.best.role_bindings
                )

    def test_phase_residual_compatibility_excludes_local_refinements(self) -> None:
        base = placement_sequence(template(2))
        for phase_error, expected in ((0.0, True), (2.0, True), (3.0, False)):
            for local_error in (0.0, 1000.0):
                with self.subTest(phase_error=phase_error, local_error=local_error):
                    bindings = []
                    for index, (binding, canonical) in enumerate(zip(
                        base.role_bindings, base.model_role_positions_px, strict=True
                    )):
                        position = canonical + (phase_error if index == 0 else local_error)
                        interval = FiniteInterval.exact(position)
                        bindings.append(replace(
                            binding,
                            use=(
                                SequenceBindingUse.PHASE_ANCHOR if index == 0
                                else SequenceBindingUse.LOCAL_REFINEMENT
                            ),
                            canonical_position_px=position,
                            fit_position_interval_px=interval,
                            full_position_interval_px=interval,
                        ))
                    fit = replace(
                        base, role_bindings=tuple(bindings), phase_support_coverage=1.0
                    )
                    self.assertEqual(_phase_residual_compatible(fit), expected)
                    self.assertEqual(fit.role_bindings, tuple(bindings))

    def test_rank_two_projection_requires_a_calibrated_nominal_grid(self) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=((10, 20) if weak else (0, 10, 20)),
                support_fraction=(2.0 / 3.0 if weak else 1.0),
                continuous_support_fraction=(2.0 / 3.0 if weak else 1.0),
            )
            for identity, coordinate, role, weak in (
                ("start:1", 40.0, BoundaryRole.START, False),
                ("weak:end:1", 140.0, BoundaryRole.END, True),
                ("weak:start:2", 160.0, BoundaryRole.START, True),
                ("end:2", 260.0, BoundaryRole.END, False),
            )
        )
        result = fit_template_phase(
            observations,
            template(2),
            holder_span_px=FiniteInterval(0.0, 300.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "candidate-projection-rank-two",
                    FiniteInterval(0.0, 300.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_UNAVAILABLE,
        )
        self.assertEqual(projection.retained_direct_constraint_rank, 2)

    def test_unobserved_frame_requires_a_calibrated_nominal_grid(self) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=((10, 20) if weak else (0, 10, 20)),
                support_fraction=(2.0 / 3.0 if weak else 1.0),
                continuous_support_fraction=(2.0 / 3.0 if weak else 1.0),
            )
            for identity, coordinate, role, weak in (
                ("start:1", 40.0, BoundaryRole.START, False),
                ("end:1", 140.0, BoundaryRole.END, False),
                ("start:2", 160.0, BoundaryRole.START, False),
                ("end:2", 260.0, BoundaryRole.END, False),
                ("weak:start:3", 280.0, BoundaryRole.START, True),
                ("weak:end:3", 380.0, BoundaryRole.END, True),
                ("start:4", 400.0, BoundaryRole.START, False),
                ("end:4", 500.0, BoundaryRole.END, False),
            )
        )
        result = fit_template_phase(
            observations,
            template(4),
            holder_span_px=FiniteInterval(0.0, 540.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "candidate-projection-unobserved-frame",
                    FiniteInterval(0.0, 540.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_UNAVAILABLE,
        )
        self.assertEqual(projection.retained_direct_constraint_rank, 3)
        self.assertEqual(
            tuple(item.role_index for item in projection.projected_out_bindings),
            (4, 5),
        )

    def test_calibrated_grid_replaces_an_unauthorized_complete_frame(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=((10, 20) if weak else (0, 10, 20)),
                support_fraction=(2.0 / 3.0 if weak else 1.0),
                continuous_support_fraction=(2.0 / 3.0 if weak else 1.0),
            )
            for identity, coordinate, role, weak in (
                ("start:1", 40.0, BoundaryRole.START, False),
                ("end:1", 140.0, BoundaryRole.END, False),
                ("start:2", 160.0, BoundaryRole.START, False),
                ("end:2", 260.0, BoundaryRole.END, False),
                ("weak:start:3", 280.0, BoundaryRole.START, True),
                ("weak:end:3", 380.0, BoundaryRole.END, True),
                ("start:4", 400.0, BoundaryRole.START, False),
                ("end:4", 500.0, BoundaryRole.END, False),
            )
        )

        result = fit_template_phase(
            observations,
            template(4),
            holder_span_px=FiniteInterval(0.0, 540.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "candidate-projection-calibrated-frame",
                    FiniteInterval(0.0, 540.0),
                ),
            ),
            calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                template(4)
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        projection = result.best_phase_candidate_authority_projection
        assert projection is not None and result.best is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
        )
        self.assertEqual(projection.retained_direct_constraint_rank, 3)
        self.assertEqual(
            tuple(item.role_index for item in projection.projected_out_bindings),
            (4, 5),
        )
        self.assertIsNone(result.best.role_bindings[4])
        self.assertIsNone(result.best.role_bindings[5])

    def test_candidate_authority_rejects_a_material_contradiction(self) -> None:
        supported = _phase_candidate_group("supported", 0.0)
        contradicted = _phase_candidate_group("contradicted", 5.0)
        alternative = replace(
            edge("contradicted:alternative", 155.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
            support_fraction=0.34,
            continuous_support_fraction=0.34,
        )
        conflict = separator(
            "candidate-material-conflict",
            contradicted[1],
            alternative,
            FiniteInterval(9.0, 11.0),
        )
        conflict = replace(
            conflict,
            material_support_region_count=1,
            material_regions=tuple(
                region
                if region.region_index == 0
                else replace(
                    region,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                )
                for region in conflict.material_regions
            ),
            evidence_state=BoundaryEvidenceState.CONTRADICTION,
        )

        result = fit_template_phase(
            (*supported, *contradicted, alternative),
            template(2),
            separator_bands=(conflict,),
            holder_span_px=FiniteInterval(0.0, 320.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "candidate-material-conflict",
                    FiniteInterval(0.0, 320.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(
            result.winner_basis,
            PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY,
        )
        assert result.runner_phase_candidate_authority_projection is not None
        self.assertEqual(
            result.runner_phase_candidate_authority_projection
            .input_direct_role_authority.state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(
            result.runner_phase_candidate_authority_projection
            .input_direct_role_authority
            .unsupported_role_indices,
            (1,),
        )
        self.assertEqual(
            result.runner_phase_candidate_authority_projection.outcome,
            PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
        )
        self.assertFalse(
            result.runner_phase_candidate_authority_projection
            .projected_out_bindings
        )

    def test_short_material_alternative_does_not_contradict_source_wide_role(
        self,
    ) -> None:
        supported = _phase_candidate_group("supported", 0.0)
        alternative_group = _phase_candidate_group("alternative", 5.0)
        impossible_alternative = replace(
            edge("alternative:impossible-end", 155.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
            trace_coordinates_px=(10, 20),
            support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0,
        )
        conflict = separator(
            "material-outside-fitted-width",
            alternative_group[1],
            impossible_alternative,
            FiniteInterval(9.0, 11.0),
        )
        conflict = replace(
            conflict,
            material_support_region_count=1,
            material_regions=tuple(
                region
                if region.region_index == 0
                else replace(
                    region,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                )
                for region in conflict.material_regions
            ),
            evidence_state=BoundaryEvidenceState.CONTRADICTION,
        )

        result = fit_template_phase(
            (*supported, *alternative_group, impossible_alternative),
            template(2),
            separator_bands=(conflict,),
            holder_span_px=FiniteInterval(0.0, 320.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "material-outside-fitted-width",
                    FiniteInterval(0.0, 320.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        assert result.runner_phase_candidate_authority_projection is not None
        self.assertEqual(
            result.runner_phase_candidate_authority_projection
            .input_direct_role_authority.state,
            EvidenceState.SUPPORTED,
        )
        rejected = replace(
            result.best_phase_candidate_authority_projection,
            outcome=(
                PhaseCandidateProjectionOutcome.DISCRETE_IDENTITY_CHANGED
            ),
            basis=None,
            reason="authorized refit changed the bounded discrete mapping",
        )
        self.assertFalse(rejected.eligible)

    def test_independent_source_width_rejects_impossible_material_alternative(
        self,
    ) -> None:
        observations = _phase_candidate_group("source-width", 0.0)
        result = fit_template_phase(observations, template(2))
        assert result.best is not None
        alternative = replace(
            edge("source-width:alternate-start", 50.0),
            qualified_anchor_roles=(BoundaryRole.START,),
            polarity=1,
        )
        supported = SeparatorMaterialRegionObservation(
            region_index=0,
            sample_count=1,
            material_contrast_interval=FiniteInterval(3.0, 4.0),
            core_texture_interval=FiniteInterval(0.0, 1.0),
            state=SeparatorMaterialRegionState.SUPPORTED,
        )
        conflict = replace(
            separator(
                "source-width:material-conflict",
                observations[0],
                alternative,
                FiniteInterval(9.0, 11.0),
            ),
            material_support_region_count=1,
            material_regions=(
                supported,
                replace(
                    supported,
                    region_index=1,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                ),
                replace(
                    supported,
                    region_index=2,
                    state=SeparatorMaterialRegionState.TONE_UNRESOLVED,
                ),
            ),
            evidence_state=BoundaryEvidenceState.CONTRADICTION,
        )
        measurement_sets = (
            phase_sequence_measurement(
                "source-width-material-conflict",
                FiniteInterval(0.0, 300.0),
            ),
        )

        before_source_width = assess_direct_role_binding_authority(
            result.best,
            (*observations, alternative),
            (conflict,),
            measurement_sets,
        )
        after_source_width = assess_direct_role_binding_authority(
            result.best,
            (*observations, alternative),
            (conflict,),
            measurement_sets,
            authorized_source_frame_width_px=FiniteInterval(99.0, 101.0),
        )

        self.assertEqual(
            before_source_width.state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(after_source_width.state, EvidenceState.SUPPORTED)

    def test_two_authorized_discrete_candidates_remain_ambiguous(self) -> None:
        result = fit_template_phase(
            (
                *_phase_candidate_group("first", 0.0),
                *_phase_candidate_group("second", 5.0),
            ),
            template(2),
            holder_span_px=FiniteInterval(0.0, 320.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "two-authorized-candidates",
                    FiniteInterval(0.0, 320.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
        )
        assert result.best_phase_candidate_authority_projection is not None
        assert result.runner_phase_candidate_authority_projection is not None
        self.assertEqual(
            result.best_phase_candidate_authority_projection
            .input_direct_role_authority.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            result.runner_phase_candidate_authority_projection
            .input_direct_role_authority.state,
            EvidenceState.SUPPORTED,
        )

    def test_no_authorized_candidate_returns_a_typed_failure(self) -> None:
        result = fit_template_phase(
            (
                *_phase_candidate_group("first-short", 0.0, short=True),
                *_phase_candidate_group("second-short", 5.0, short=True),
            ),
            template(2),
            holder_span_px=FiniteInterval(0.0, 320.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "no-authorized-candidate",
                    FiniteInterval(0.0, 320.0),
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE,
        )
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        assert result.best_phase_candidate_authority_projection is not None
        self.assertEqual(
            result.best_phase_candidate_authority_projection
            .input_direct_role_authority.state,
            EvidenceState.UNAVAILABLE,
        )


if __name__ == "__main__":
    unittest.main()
