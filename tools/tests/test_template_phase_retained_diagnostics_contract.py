from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from x5crop.detection.photo_geometry import (
    template_phase_competition as phase_competition,
    template_phase_fitting as phase_fitting,
    template_phase as phase_flow,
    template_phase_projection as phase_projection,
    template_phase_refinement as phase_refinement,
)
from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_edge as edge,
    placement_sequence,
    phase_sequence_measurement,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_frame_width import (
    calibrate_source_frame_width,
    SourceFrameWidthAuthorityPlacementScope,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.template_direct_role_authority import assess_direct_role_binding_authority
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase import (
    fit_template_phase_candidate_with_adjacency_relations,
    fit_template_phase_with_adjacency_relations,
    retain_pre_local_phase_proposal,
)
from x5crop.detection.photo_geometry.template_lattice_authority import direct_role_constraint_rank
from x5crop.detection.photo_geometry.template_phase_candidate_model import _BoundFit
from x5crop.detection.photo_geometry.template_phase_observations import _facts
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectedBinding,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseRetainedProposalBasis,
    TemplatePhaseInput,
    _TerminalPhaseDiagnostic,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from tools.tests.phase_test_support import _phase_candidate_group


class TemplatePhaseRetainedDiagnosticsContractTest(unittest.TestCase):
    def test_late_empty_runner_restores_only_existing_failed_diagnostic(self) -> None:
        spec = template(2)
        current_edges = _phase_candidate_group("current-diagnostic", 0.0)
        diagnostic_edges = _phase_candidate_group("terminal-diagnostic", 400.0)
        current = fit_template_phase(current_edges, spec,
            holder_span_px=FiniteInterval(0.0, 300.0))
        terminal = fit_template_phase(diagnostic_edges, spec,
            holder_span_px=FiniteInterval(400.0, 700.0))
        assert terminal.best is not None
        authority = assess_direct_role_binding_authority(
            terminal.best, diagnostic_edges, (),
            (phase_sequence_measurement("terminal-measurement", FiniteInterval(0.0, 800.0)),))
        failed = PhaseCandidateAuthorityProjection(
            authority, PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE,
            None, (), 3, "original terminal failure",
        )
        diagnostic = _TerminalPhaseDiagnostic(terminal.best, failed)
        unresolved = replace(current,
            registered_direct_observation_ids=tuple(
                fact.observation_id for fact in _facts((*current_edges, *diagnostic_edges))),
            status=PhaseFitStatus.UNRESOLVED,
            failure_kind=PhaseFailureKind.CALIBRATED_NOMINAL_GRID_CONFLICT,
            ambiguity_reason="later local counterevidence", winner_basis=None,
            runner_up=None, runner_phase_candidate_authority_projection=None,
            _terminal_diagnostic=diagnostic,
        )
        restored = phase_flow._retain_empty_terminal_diagnostic_runner(unresolved)
        self.assertEqual(restored.best, unresolved.best)
        self.assertEqual(restored.runner_up, terminal.best)
        self.assertIs(restored.runner_phase_candidate_authority_projection, failed)
        self.assertEqual(restored.failure_kind, unresolved.failure_kind)
        self.assertEqual(restored.ambiguity_reason, unresolved.ambiguity_reason)
        self.assertIsNone(restored.winner_basis)
        self.assertEqual(restored.receipt, unresolved.receipt)
        self.assertIsNone(restored._terminal_diagnostic)
        # A real competing runner, a resolved result, and a producer bound
        # never yield their slot to a failed diagnostic.
        for protected in (
            replace(unresolved, runner_up=terminal.best),
            replace(unresolved, status=current.status, failure_kind=None,
                ambiguity_reason=None, winner_basis=current.winner_basis),
            replace(unresolved, status=PhaseFitStatus.BOUND_EXCEEDED, best=None,
                failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED),
        ):
            result = phase_flow._retain_empty_terminal_diagnostic_runner(protected)
            self.assertEqual(result.best, protected.best)
            self.assertEqual(result.runner_up, protected.runner_up)
            self.assertEqual(result.status, protected.status)
            self.assertEqual(result.failure_kind, protected.failure_kind)
        with self.assertRaisesRegex(ValueError, "registered template"):
            replace(unresolved, registered_direct_observation_ids=current.registered_direct_observation_ids)
        with self.assertRaisesRegex(ValueError, "registered template"):
            replace(unresolved, template=replace(spec, template_id="different-template"))
        with self.assertRaisesRegex(ValueError, "failed projection"):
            _TerminalPhaseDiagnostic(terminal.best, replace(failed,
                outcome=PhaseCandidateProjectionOutcome.UNCHANGED,
                basis=PhaseCandidateProjectionBasis.DIRECT_BINDINGS, reason=None))

    def test_local_counterevidence_retains_a_complete_pre_local_proposal(
        self,
    ) -> None:
        spec = template(4)
        observations = tuple(
            replace(
                edge(f"retained-proposal:{slot}", 40.0 + 120.0 * slot),
                qualified_anchor_roles=(BoundaryRole.START,),
            )
            for slot in range(4)
        )
        nominal = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=(
                    calibrated_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 520.0),
                phase_authority_px=FiniteInterval.exact(40.0),
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "retained-proposal-complete",
                        FiniteInterval(0.0, 520.0),
                    ),
                ),
            )
        )
        self.assertEqual(nominal.status, PhaseFitStatus.RESOLVED)
        assert nominal.best is not None
        self.assertIsNotNone(
            nominal.best.calibrated_nominal_grid_fit_state
        )
        failed = replace(
            nominal,
            best=None,
            runner_up=None,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason="local adjacency refit rejected the normal Grid",
            failure_kind=PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
            winner_basis=None,
            best_phase_candidate_authority_projection=None,
            runner_phase_candidate_authority_projection=None,
            global_lattice_authority=None,
            calibrated_nominal_grid_evidence=None,
            adjacency_observation_coverage=(),
            adjacency_continuity_observations=(),
            direct_role_binding_authority=None,
            outer_frame_observation_authority=None,
            source_frame_width_topology_assessment=None,
            # This synthetic pre-local failure has no retained fit; final
            # candidate-bound proofs are rebuilt after proposal retention.
            retained_adjacency_assessments=(),
        )

        retained = retain_pre_local_phase_proposal(
            failed,
            prior=nominal,
        )

        self.assertEqual(retained.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            retained.failure_kind,
            PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
        )
        self.assertIs(retained.best, nominal.best)
        self.assertIsNone(retained.winner_basis)
        self.assertEqual(
            retained.retained_proposal_basis,
            PhaseRetainedProposalBasis
            .CALIBRATED_NOMINAL_GRID_BEFORE_LOCAL_COUNTEREVIDENCE,
        )

        direct_prior = fit_template_phase(
            observations,
            spec,
            phase_authority_px=FiniteInterval.exact(40.0),
        )
        assert direct_prior.best is not None
        self.assertIsNone(
            direct_prior.best.calibrated_nominal_grid_fit_state
        )
        retained_direct = retain_pre_local_phase_proposal(
            failed,
            prior=direct_prior,
        )
        self.assertIs(retained_direct.best, direct_prior.best)
        self.assertEqual(
            retained_direct.retained_proposal_basis,
            PhaseRetainedProposalBasis
            .DIRECT_LATTICE_BEFORE_LOCAL_COUNTEREVIDENCE,
        )

        bounded = replace(
            failed,
            status=PhaseFitStatus.BOUND_EXCEEDED,
            ambiguity_reason="phase hypothesis bound exceeded",
            failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED,
            _native_phase_retention=None,
        )
        not_retained = retain_pre_local_phase_proposal(
            bounded,
            prior=nominal,
        )
        self.assertIsNone(not_retained.best)
        self.assertIsNone(not_retained.retained_proposal_basis)

    def test_restored_proposal_measures_width_before_final_eligibility(self) -> None:
        spec = template(2)
        observations = tuple(
            edge(f"restored-width:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=spec,
            scale_px_per_mm=None,
            holder_span_px=FiniteInterval(0.0, 300.0),
            phase_authority_px=FiniteInterval.exact(40.0),
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(spec),
            sequence_measurement_sets=(phase_sequence_measurement(
                "restored-width-complete", FiniteInterval(0.0, 300.0),
            ),),
        )

        def reject_local(result, *_args, **_kwargs):
            return replace(
                result, best=None, runner_up=None,
                status=PhaseFitStatus.UNRESOLVED,
                failure_kind=PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
                ambiguity_reason="local counterevidence rejects eligibility",
                winner_basis=None,
                best_phase_candidate_authority_projection=None,
                runner_phase_candidate_authority_projection=None,
                calibrated_nominal_grid_evidence=None,
                adjacency_observation_coverage=(),
                adjacency_continuity_observations=(),
                direct_role_binding_authority=None,
                outer_frame_observation_authority=None,
                source_frame_width_topology_assessment=None,
                global_lattice_authority=None,
            )

        with patch.object(phase_refinement, "_refine_selected_roles_with_candidate_elimination",
                          side_effect=reject_local):
            candidate = fit_template_phase_candidate_with_adjacency_relations(phase_input)
        result = candidate.result
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )
        _, width = calibrate_source_frame_width(source, result, observations)

        self.assertIsNotNone(result.direct_role_binding_authority)
        self.assertEqual(width.state, EvidenceState.SUPPORTED)
        self.assertEqual(width.placement_scope,
                         SourceFrameWidthAuthorityPlacementScope.RETAINED_UNRESOLVED_PROPOSAL)
        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(result.failure_kind, PhaseFailureKind.FIXED_TEMPLATE_MISMATCH)
        self.assertIsNone(result.winner_basis)

    def test_residual_counterevidence_retains_bounded_phase_proposal(
        self,
    ) -> None:
        spec = template(1)
        observations = (edge("residual-proposal-anchor", 40.0),)
        baseline = fit_template_phase(observations, spec)
        assert baseline.best is not None

        with patch(
            'x5crop.detection.photo_geometry.template_phase_fitting._fit_seed',
            return_value=_BoundFit(baseline.best, False),
        ):
            retained = fit_template_phase(observations, spec)

        self.assertEqual(retained.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            retained.failure_kind,
            PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
        )
        self.assertIs(retained.best, baseline.best)
        self.assertIsNone(retained.winner_basis)
        self.assertEqual(
            retained.retained_proposal_basis,
            PhaseRetainedProposalBasis
            .DIRECT_LATTICE_WITH_RESIDUAL_COUNTEREVIDENCE,
        )
        self.assertIn(
            "residual compatibility contract",
            retained.ambiguity_reason or "",
        )

        unanchored = fit_template_phase((), spec)
        self.assertIsNone(unanchored.best)
        self.assertIsNone(unanchored.retained_proposal_basis)

    def test_overlapping_marginals_do_not_hide_a_distinct_residual_runner(
        self,
    ) -> None:
        spec = template(3)
        complete = placement_sequence(spec)
        sparse = placement_sequence(spec, missing=(1, 2, 3, 4, 5))
        sparse = replace(
            sparse,
            phase_lattice_fit=replace(
                sparse.phase_lattice_fit,
                absolute_phase_interval_px=FiniteInterval(-100.0, 300.0),
            ),
        )
        observations = tuple(
            edge(f"seed:{index}", position)
            for index, position in enumerate(complete.model_role_positions_px)
        )
        for distinct in (False, True):
            with self.subTest(distinct_coordinate_identity=distinct):
                binding = complete.role_bindings[0]
                assert binding is not None
                rival = replace(
                    complete,
                    role_bindings=(
                        replace(binding, observation_id=ObservationId("other:start"))
                        if distinct else binding,
                        *complete.role_bindings[1:],
                    ),
                )
                calls = 0

                def fitted_seed(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    return (
                        _BoundFit(sparse, True)
                        if calls == 1 else _BoundFit(rival, False)
                    )

                with patch.object(phase_fitting, "_fit_seed", side_effect=fitted_seed):
                    result = fit_template_phase(observations, spec)

                self.assertGreater(calls, 1)
                self.assertIs(result.best, sparse)
                if distinct:
                    self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
                    self.assertIsNone(result.winner_basis)
                    self.assertIs(result.runner_up, rival)
                    self.assertIn("higher-support", result.ambiguity_reason or "")
                else:
                    self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
                    self.assertIsNone(result.runner_up)

    def test_stronger_terminal_residual_evidence_survives_occupied_runner(
        self,
    ) -> None:
        spec = template(3)
        best = placement_sequence(spec, missing=(1, 2, 3, 5))
        runner = placement_sequence(spec, missing=(1, 2, 3, 4, 5))
        first = runner.role_bindings[0]
        assert first is not None
        runner = replace(
            runner,
            role_bindings=(replace(first, observation_id=ObservationId("eligible:other")),
                           *runner.role_bindings[1:]),
        )
        complete = placement_sequence(spec)
        first = complete.role_bindings[0]
        assert first is not None
        complete = replace(
            complete,
            role_bindings=(replace(first, observation_id=ObservationId("terminal:other")),
                           *complete.role_bindings[1:]),
        )
        for residual_compatible, stronger, distinct, grid_conflict, native_authorized in (
            (False, True, True, False, True),
            (True, True, True, False, True),
            (False, False, True, False, True),
            (False, True, False, False, True),
            (True, True, True, True, True),
            (True, True, True, True, False),
        ):
            with self.subTest(residual_compatible=residual_compatible,
                              stronger=stronger, distinct=distinct,
                              grid_conflict=grid_conflict, native_authorized=native_authorized):
                terminal = complete if stronger else replace(
                    best, role_bindings=(complete.role_bindings[0], *best.role_bindings[1:]),
                )
                if not distinct:
                    terminal = placement_sequence(spec)
                # A raw-compatible failed interpretation must never gain the
                # stronger residual-counterevidence exception.
                topology_terminal = replace(complete, residual_sum_px=1.0)
                pool = (_BoundFit(best, True), _BoundFit(runner, True),
                        _BoundFit(terminal, residual_compatible),
                        _BoundFit(topology_terminal, True))
                calls = 0

                def fitted_seed(*args, **kwargs):
                    nonlocal calls
                    candidate = pool[min(calls, len(pool) - 1)]
                    calls += 1
                    return candidate

                def project(candidate, authority, *args, **kwargs):
                    eligible = candidate.fit is best or candidate.fit is runner
                    return (candidate if eligible else None), PhaseCandidateAuthorityProjection(
                        input_direct_role_authority=authority,
                        outcome=(PhaseCandidateProjectionOutcome.UNCHANGED if eligible
                                 else PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT
                                 if grid_conflict and candidate.fit is terminal
                                 else PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE),
                        basis=(PhaseCandidateProjectionBasis.DIRECT_BINDINGS if eligible else None),
                        projected_out_bindings=tuple(
                            PhaseCandidateProjectedBinding(item.role_index, item.observation_id)
                            for item in authority.facts if item.state == EvidenceState.UNAVAILABLE
                        ),
                        retained_direct_constraint_rank=direct_role_constraint_rank(
                            candidate.fit, authority.supported_role_indices,
                        ),
                        reason=None if eligible else "original failed projection",
                    )

                observations = tuple(
                    edge(str(binding.observation_id), binding.canonical_position_px)
                    for fit in (best, runner, complete)
                    for binding in fit.role_bindings if binding is not None
                )
                observations = tuple({item.observation_id: item for item in observations}.values())
                if not native_authorized:
                    observations = tuple(
                        replace(item, trace_coordinates_px=(0, 10), support_fraction=2.0 / 3.0)
                        if str(item.observation_id) == "terminal:other" else item
                        for item in observations
                    )
                with patch.object(phase_fitting, "_fit_seed", side_effect=fitted_seed), patch.object(
                    phase_projection, "project_candidate_to_authorized_direct_roles", side_effect=project,
                ):
                    result = fit_template_phase(
                        observations, spec,
                        sequence_measurement_sets=(phase_sequence_measurement(
                            "occupied-runner", FiniteInterval(0.0, 500.0),
                        ),),
                    )
                expected = (
                    (not residual_compatible or grid_conflict and native_authorized)
                    and stronger and distinct
                )
                self.assertIs(result.best, best)
                self.assertIs(result.runner_up, terminal if expected else runner)
                projection = result.runner_phase_candidate_authority_projection
                assert projection is not None
                self.assertEqual(projection.eligible, not expected)
                if expected:
                    self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
                    self.assertIsNone(result.winner_basis)
                    self.assertEqual(
                        projection.outcome,
                        PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT
                        if grid_conflict else PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE,
                    )
                    self.assertEqual(projection.reason, "original failed projection")
                    self.assertIn("higher-support", result.ambiguity_reason or "")
                result.receipt.validate_bounds()

    def test_empty_diagnostic_runner_retains_an_incompatible_terminal_fit(
        self,
    ) -> None:
        spec = template(3)
        sparse = placement_sequence(spec, missing=(1, 2, 3, 4, 5))
        complete = placement_sequence(spec)
        first = complete.role_bindings[0]
        assert first is not None
        complete = replace(
            complete,
            role_bindings=(
                replace(first, observation_id=ObservationId("terminal:other")),
                *complete.role_bindings[1:],
            ),
            residual_sum_px=50.0,
        )
        observations = (
            edge("sequence:0", 100.0),
            *(edge(str(binding.observation_id), binding.canonical_position_px)
              for binding in complete.role_bindings if binding is not None),
        )
        calls = 0

        def fitted_seed(*args, **kwargs):
            nonlocal calls
            calls += 1
            return (
                _BoundFit(sparse, True)
                if calls == 1 else _BoundFit(complete, False)
            )

        def terminal_projection(candidate, authority, *args, **kwargs):
            return None, PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT,
                basis=None,
                projected_out_bindings=(),
                retained_direct_constraint_rank=direct_role_constraint_rank(
                    candidate.fit, authority.supported_role_indices,
                ),
                reason="registered Grid conflicts with this diagnostic fit",
            )

        with patch.object(phase_fitting, "_fit_seed", side_effect=fitted_seed), patch.object(
            phase_projection, "project_candidate_to_authorized_direct_roles",
            side_effect=terminal_projection,
        ):
            result = fit_template_phase(
                observations, spec,
                sequence_measurement_sets=(phase_sequence_measurement(
                    "terminal-diagnostics", FiniteInterval(0.0, 500.0),
                ),),
            )

        self.assertIs(result.best, sparse)
        self.assertIs(result.runner_up, complete)
        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertIsNone(result.winner_basis)
        self.assertEqual(result.failure_kind, PhaseFailureKind.CALIBRATED_NOMINAL_GRID_CONFLICT)
        assert result.runner_phase_candidate_authority_projection is not None
        self.assertFalse(result.runner_phase_candidate_authority_projection.eligible)
        self.assertEqual(result.receipt.candidate_direct_role_projection_success_count, 0)

    def test_equal_bindings_preserve_each_full_protection_interval(self) -> None:
        observations = tuple(
            edge(f"dedup-role:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
        )
        spec = template(2)
        baseline = fit_template_phase(observations, spec).best
        assert baseline is not None
        protected = replace(
            baseline,
            model_full_role_intervals_px=(
                *baseline.model_full_role_intervals_px[:-1],
                FiniteInterval(240.0, 280.0),
            ),
        )
        for measured in (False, True):
            with self.subTest(measured=measured):
                calls = 0

                def fitted_seed(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    return _BoundFit(baseline if calls % 2 else protected, True)

                with patch.object(phase_fitting, "_fit_seed", side_effect=fitted_seed):
                    result = fit_template_phase(
                        observations,
                        spec,
                        sequence_measurement_sets=(
                            (phase_sequence_measurement(
                                "dedup-protection", FiniteInterval(0.0, 300.0),
                            ),) if measured else ()
                        ),
                    )
                self.assertGreaterEqual(calls, 2)
                self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
                assert result.best is not None
                self.assertEqual(
                    result.best.binding_observation_ids, baseline.binding_observation_ids,
                )
                self.assertEqual(
                    result.best.model_full_role_intervals_px[-1],
                    FiniteInterval(240.0, 280.0),
                )
                result.receipt.validate_bounds()

    def test_equal_projected_fits_keep_distinct_weak_role_provenance(self) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                trace_coordinates_px=(10, 20) if weak else (0, 10, 20),
                support_fraction=2.0 / 3.0 if weak else 1.0,
                continuous_support_fraction=2.0 / 3.0 if weak else 1.0,
            )
            for identity, coordinate, role, weak in (
                ("dedup:start:1", 40.0, BoundaryRole.START, False),
                ("dedup:start:2", 160.0, BoundaryRole.START, False),
                ("dedup:start:3", 280.0, BoundaryRole.START, False),
                ("dedup:weak:1", 140.0, BoundaryRole.END, True),
                ("dedup:weak:2", 140.0, BoundaryRole.END, True),
            )
        )
        spec = template(3)
        projections = []
        project = phase_projection.project_candidate_to_authorized_direct_roles

        def project_record(*args, **kwargs):
            record = project(*args, **kwargs)
            projections.append(record)
            return record

        with patch.object(
            phase_projection, "project_candidate_to_authorized_direct_roles",
            side_effect=project_record,
        ), patch.object(
            phase_competition, "_unseparated_completion_competitor",
            wraps=phase_competition._unseparated_completion_competitor,
        ) as completion:
            result = fit_template_phase(
                observations, spec,
                phase_authority_px=FiniteInterval.exact(40.0),
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(spec),
                sequence_measurement_sets=(phase_sequence_measurement(
                    "dedup-provenance", FiniteInterval(0.0, 380.0),
                ),),
            )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        matching = [
            (candidate, projection)
            for candidate, projection in projections
            if candidate is not None and candidate.fit == result.best
        ]
        self.assertEqual(len(matching), 3)
        self.assertEqual(
            {tuple(item.observation_id for item in projection.projected_out_bindings)
             for _, projection in matching},
            {(), (ObservationId("dedup:weak:1"),), (ObservationId("dedup:weak:2"),)},
        )
        retained = completion.call_args.args[1]
        self.assertEqual(sum(candidate.fit == result.best for candidate in retained), 3)
        self.assertEqual(result.receipt.candidate_direct_role_authority_evaluation_count, 4)
        result.receipt.validate_bounds()


if __name__ == "__main__":
    unittest.main()
