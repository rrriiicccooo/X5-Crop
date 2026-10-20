from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests import test_template_phase_membership_contract as membership_fixture
from tools.tests.phase_test_support import _continuity_for_residual
from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_edge,
    phase_separator,
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_adjacency_coverage import (
    assess_adjacency_observation_coverage,
)
from x5crop.detection.photo_geometry.template_adjacency_topology import (
    observe_adjacency_continuity,
)
from x5crop.detection.photo_geometry.template_model import (
    OverlapRelation,
    SequenceBindingUse,
    SequenceRoleLineEvidence,
    SeparatorRelation,
    adjacency_relation_evidence_identity,
)
from x5crop.detection.photo_geometry.template_overlap import (
    observe_overlap_edge_pairs,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseCandidateProjectionOutcome,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_phase_output import (
    PhaseMemberOutputGap,
    PhaseMemberAdjacencyPropagation,
    PhaseMemberOutputWork,
    assess_phase_member_output,
)
from x5crop.detection.photo_geometry.template_phase_projection import (
    CandidateProjectionWork,
)
from x5crop.detection.photo_geometry.template_phase_refinement import (
    _project_late_local_candidate,
)
from x5crop.detection.photo_geometry.template_residual import (
    ResidualPattern,
    derive_adjacency_relations,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FramePhysicalSpec


class PhaseMemberAdjacencyPropagationContractTest(unittest.TestCase):
    @staticmethod
    def _fixture(kind: str, *, missing: tuple[int, ...] = (), conflict: bool = False):
        spec = phase_template(3)
        if kind == "narrow":
            coordinates = (
                (100.0, 200.0, 220.0, 320.0, 340.0, 440.0)
                if conflict
                else (100.0, 200.0, 215.0, 315.0, 335.0, 435.0)
            )
            prefix = "narrow"
        elif kind == "overlap":
            coordinates = (100.0, 200.0, 195.0, 295.0, 315.0, 415.0)
            prefix = "overlap"
        else:
            raise AssertionError(f"unknown adjacency fixture: {kind}")

        all_edges = tuple(
            replace(
                phase_edge(f"{prefix}:{index}", coordinate),
                qualified_anchor_roles=(
                    (BoundaryRole.START,)
                    if index % 2 == 0
                    else (BoundaryRole.END,)
                ),
                polarity=1 if index % 2 == 0 else -1,
                **(
                    {
                        "canonical_direction_degrees": 0.0,
                        "fit_direction_interval_degrees": FiniteInterval.exact(0.0),
                        "full_direction_interval_degrees": FiniteInterval.exact(0.0),
                    }
                    if kind == "overlap"
                    else {}
                ),
            )
            for index, coordinate in enumerate(coordinates)
        )
        observations = tuple(
            edge for index, edge in enumerate(all_edges) if index not in missing
        )
        band = None
        if kind == "narrow":
            band = phase_separator(
                f"{prefix}:separator",
                all_edges[1],
                all_edges[2],
                FiniteInterval(14.8, 15.2),
            )
        bands = () if band is None else (band,)

        base = placement_sequence(spec, missing=missing)
        bindings = []
        for index, binding in enumerate(base.role_bindings):
            if binding is None:
                bindings.append(None)
                continue
            edge = all_edges[index]
            observation_id = ObservationId(f"{prefix}:{index}")
            evidence_group_id = (
                band.observation_id
                if band is not None and index in (1, 2)
                else observation_id
            )
            line_evidence = None
            if kind == "overlap":
                assert edge.fit_direction_interval_degrees is not None
                line_evidence = SequenceRoleLineEvidence(
                    observation_id=observation_id,
                    reference_trace_px=edge.reference_trace_px,
                    fit_position_interval_px=edge.fit_position_interval_px,
                    fit_direction_interval_degrees=edge.fit_direction_interval_degrees,
                )
            bindings.append(
                replace(
                    binding,
                    observation_id=observation_id,
                    evidence_group_id=evidence_group_id,
                    canonical_position_px=coordinates[index],
                    fit_position_interval_px=edge.fit_position_interval_px,
                    full_position_interval_px=edge.full_position_interval_px,
                    line_evidence=line_evidence,
                )
            )

        model_intervals = tuple(
            all_edges[index].fit_position_interval_px
            if index not in missing
            else FiniteInterval.exact(coordinates[index])
            for index in range(len(coordinates))
        )
        model_full_intervals = tuple(
            all_edges[index].full_position_interval_px
            if index not in missing
            else FiniteInterval.exact(coordinates[index])
            for index in range(len(coordinates))
        )
        fit = replace(
            base,
            model_role_positions_px=coordinates,
            model_role_intervals_px=model_intervals,
            model_full_role_intervals_px=model_full_intervals,
            role_bindings=tuple(bindings),
        )
        analysis = derive_adjacency_relations(
            fit,
            _continuity_for_residual(fit, observations, bands),
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=bands,
            template=spec,
            calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(spec),
            scale_px_per_mm=None,
            holder_span_px=FiniteInterval(0.0, 500.0),
            phase_authority_px=FiniteInterval.exact(100.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    f"{prefix}:projection",
                    FiniteInterval(0.0, 500.0),
                ),
            ),
        )
        return fit, phase_input, analysis, all_edges, bands

    @staticmethod
    def _project(fit, phase_input, analysis):
        work = CandidateProjectionWork()
        output, projection = _project_late_local_candidate(
            fit,
            phase_input,
            allow_direct_rank=True,
            adjacency_relations=analysis.relations,
            projection_work=work,
        )
        return output, projection, work

    @staticmethod
    def _assess_lane(fit, phase_input, *, base_cross_registration=None):
        fixture = membership_fixture.TemplatePhaseMembershipContractTest()
        member = fixture._member(fit, 0)
        scope = fixture._scope(
            fit.template,
            (member,),
            fixture._receipt(hypotheses=1),
        )
        scale = PositiveInterval.exact(10.0)
        source = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=scale,
            height_scale_px_per_mm=scale,
        )
        lane = SimpleNamespace(
            phase_competition=SimpleNamespace(
                status=PhaseFitStatus.UNRESOLVED,
                competition_scopes=(scope,),
                registered_direct_observation_ids=(),
            ),
            phase_input=phase_input,
            source_scan_geometry=source,
            coarse_support=SimpleNamespace(enclosing_side_facts=()),
            lane=SimpleNamespace(
                scan_canvas=SimpleNamespace(
                    axis_scales=SimpleNamespace(
                        width_axis_px_per_mm=scale,
                        height_axis_px_per_mm=scale,
                    )
                )
            ),
            base_cross_registration=base_cross_registration,
        )
        return lane, scope, member

    def _assert_identity_preserved(self, before, after, analysis) -> None:
        self.assertIsNotNone(after)
        assert after is not None
        self.assertEqual(after.template, before.template)
        self.assertEqual(
            after.phase_lattice_fit.integer_slot_offset,
            before.phase_lattice_fit.integer_slot_offset,
        )
        self.assertEqual(after.role_bindings, before.role_bindings)
        self.assertEqual(
            tuple(map(adjacency_relation_evidence_identity, after.adjacency_relations)),
            tuple(map(adjacency_relation_evidence_identity, analysis.relations)),
        )

    def test_registered_narrow_separator_and_overlap_use_the_same_bounded_api(self):
        for kind, relation_type in (
            ("narrow", SeparatorRelation),
            ("overlap", OverlapRelation),
        ):
            with self.subTest(kind=kind):
                fit, phase_input, analysis, _edges, _bands = self._fixture(kind)
                self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
                self.assertIsInstance(analysis.relations[0], relation_type)
                output, projection, work = self._project(fit, phase_input, analysis)
                self.assertIsNotNone(output)
                self.assertIsNotNone(projection)
                assert projection is not None
                self.assertEqual(
                    projection.outcome,
                    PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT,
                )
                self.assertEqual(work.direct_fit_count, 1)
                self.assertEqual(work.nominal_grid_solve_count, 0)
                self.assertEqual(work.nominal_grid_solve_success_count, 0)
                self._assert_identity_preserved(fit, output, analysis)
                propagation = PhaseMemberAdjacencyPropagation(
                    fit, analysis, projection, output
                )
                self.assertIs(propagation.output_fit, output)

    def test_missing_suffix_uses_one_real_nominal_grid_solve_without_losing_bindings(self):
        fit, phase_input, analysis, _edges, _bands = self._fixture(
            "narrow", missing=(4, 5)
        )
        output, projection, work = self._project(fit, phase_input, analysis)
        self.assertIsNotNone(output)
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
        )
        self.assertEqual(work.direct_fit_count, 0)
        self.assertEqual(work.nominal_grid_solve_count, 1)
        self.assertEqual(work.nominal_grid_solve_success_count, 1)
        self._assert_identity_preserved(fit, output, analysis)
        self.assertEqual(output.role_bindings[4:], (None, None))

    def test_idempotent_or_no_new_relation_does_not_solve_again(self):
        fit, phase_input, analysis, edges, _bands = self._fixture("narrow")
        output, _projection, _work = self._project(fit, phase_input, analysis)
        assert output is not None

        repeat, repeat_projection, repeat_work = self._project(
            output,
            phase_input,
            replace(analysis, relations=output.adjacency_relations),
        )
        self.assertIs(repeat, output)
        self.assertIsNone(repeat_projection)
        self.assertEqual(repeat_work, CandidateProjectionWork())

        no_relation_analysis = derive_adjacency_relations(
            fit,
            _continuity_for_residual(fit, edges, ()),
        )
        self.assertEqual(no_relation_analysis.relations, ())
        unchanged, unchanged_projection, unchanged_work = self._project(
            fit,
            phase_input,
            no_relation_analysis,
        )
        self.assertIs(unchanged, fit)
        self.assertIsNone(unchanged_projection)
        self.assertEqual(unchanged_work, CandidateProjectionWork())

    def test_unregistered_or_incomplete_overlap_cannot_become_a_relation(self):
        fit, _phase_input, _analysis, edges, _bands = self._fixture("overlap")

        for complete, register_overlap in ((True, False), (False, True)):
            with self.subTest(
                complete=complete, register_overlap=register_overlap
            ):
                measurement = phase_sequence_measurement(
                    f"overlap-guard:{complete}:{register_overlap}",
                    FiniteInterval(0.0, 500.0),
                    complete=complete,
                )
                coverage = assess_adjacency_observation_coverage(
                    fit, (measurement,), directly_observed_ordinals=()
                )
                pairs = (
                    observe_overlap_edge_pairs(
                        edges,
                        (),
                        (measurement,),
                        direction=fit.template.direction,
                        maximum_overlap_px=12.0,
                    )
                    if register_overlap
                    else ()
                )
                continuity = observe_adjacency_continuity(
                    fit, edges, (), coverage, pairs
                )
                analysis = derive_adjacency_relations(fit, continuity)
                expected_pattern = ResidualPattern.UNRESOLVED
                if not complete:
                    self.assertEqual(
                        continuity[0].kind.value,
                        "coverage_incomplete",
                    )
                    expected_pattern = ResidualPattern.NORMAL
                self.assertEqual(analysis.pattern, expected_pattern)
                self.assertEqual(analysis.relations, ())
                if complete:
                    self.assertIsNotNone(analysis.unresolved_reason)
                else:
                    self.assertIsNone(analysis.unresolved_reason)

    def test_missing_overlap_direct_permission_stays_ineligible(self):
        fit, phase_input, analysis, edges, _bands = self._fixture("overlap")
        short_edges = tuple(
            replace(
                edge,
                trace_coordinates_px=(10, 20),
                support_fraction=2.0 / 3.0,
                continuous_support_fraction=2.0 / 3.0,
            )
            if index in (1, 2)
            else edge
            for index, edge in enumerate(edges)
        )
        short_input = replace(phase_input, observations=short_edges)
        output, projection, work = self._project(fit, short_input, analysis)
        self.assertIsNone(output)
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.TOPOLOGY_BINDING_UNAVAILABLE,
        )
        self.assertEqual(work, CandidateProjectionWork())

    def test_grid_counter_reports_success_and_infeasible_attempts_at_solver_entry(self):
        fit, phase_input, analysis, _edges, _bands = self._fixture(
            "narrow", missing=(4, 5)
        )
        output, _projection, work = self._project(fit, phase_input, analysis)
        self.assertIsNotNone(output)
        self.assertEqual(work.nominal_grid_solve_count, 1)
        self.assertEqual(work.nominal_grid_solve_success_count, 1)

        bad_fit, bad_input, bad_analysis, _edges, _bands = self._fixture(
            "narrow", missing=(4, 5), conflict=True
        )
        output, projection, work = self._project(
            bad_fit, bad_input, bad_analysis
        )
        self.assertIsNone(output)
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT,
        )
        self.assertEqual(work.direct_fit_count, 0)
        self.assertEqual(work.nominal_grid_solve_count, 1)
        self.assertEqual(work.nominal_grid_solve_success_count, 0)

        overlap_fit, overlap_input, overlap_analysis, edges, _bands = self._fixture(
            "overlap"
        )
        short_input = replace(
            overlap_input,
            observations=tuple(
                replace(
                    edge,
                    trace_coordinates_px=(10, 20),
                    support_fraction=2.0 / 3.0,
                    continuous_support_fraction=2.0 / 3.0,
                )
                if index in (1, 2)
                else edge
                for index, edge in enumerate(edges)
            ),
        )
        output, projection, work = self._project(
            overlap_fit, short_input, overlap_analysis
        )
        self.assertIsNone(output)
        self.assertIsNotNone(projection)
        self.assertEqual(work, CandidateProjectionWork())

    def test_propagation_record_rejects_ledger_or_identity_mutations(self):
        fit, phase_input, analysis, _edges, _bands = self._fixture("narrow")
        output, projection, _work = self._project(fit, phase_input, analysis)
        assert output is not None and projection is not None
        PhaseMemberAdjacencyPropagation(fit, analysis, projection, output)

        with self.assertRaisesRegex(ValueError, "borrowed another native authority ledger"):
            overlap_fit, overlap_input, overlap_analysis, _edges, _bands = self._fixture(
                "overlap"
            )
            _overlap_output, overlap_projection, _overlap_work = self._project(
                overlap_fit, overlap_input, overlap_analysis
            )
            assert overlap_projection is not None
            PhaseMemberAdjacencyPropagation(
                fit,
                analysis,
                replace(
                    projection,
                    input_direct_role_authority=(
                        overlap_projection.input_direct_role_authority
                    ),
                ),
                output,
            )

        forged_bindings = list(output.role_bindings)
        forged_bindings[3] = None
        with self.assertRaisesRegex(ValueError, "changed native bindings"):
            PhaseMemberAdjacencyPropagation(
                fit,
                analysis,
                projection,
                replace(output, role_bindings=tuple(forged_bindings)),
            )

        forged_interval = replace(
            output.role_bindings[0],
            fit_position_interval_px=FiniteInterval(99.9, 100.1),
        )
        forged_bindings = list(output.role_bindings)
        forged_bindings[0] = forged_interval
        with self.assertRaisesRegex(ValueError, "changed native bindings"):
            PhaseMemberAdjacencyPropagation(
                fit,
                analysis,
                projection,
                replace(output, role_bindings=tuple(forged_bindings)),
            )

        forged_offset = replace(
            output,
            phase_lattice_fit=replace(
                output.phase_lattice_fit,
                integer_slot_offset=output.phase_lattice_fit.integer_slot_offset + 1,
                absolute_phase_interval_px=FiniteInterval(
                    output.phase_lattice_fit.absolute_phase_interval_px.minimum
                    + output.phase_lattice_fit.canonical_period_px,
                    output.phase_lattice_fit.absolute_phase_interval_px.maximum
                    + output.phase_lattice_fit.canonical_period_px,
                ),
                canonical_absolute_phase_px=(
                    output.phase_lattice_fit.canonical_absolute_phase_px
                    + output.phase_lattice_fit.canonical_period_px
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "changed native bindings"):
            PhaseMemberAdjacencyPropagation(
                fit, analysis, projection, forged_offset
            )

        forged_template = replace(
            output,
            template=replace(output.template, template_id="forged-template"),
        )
        with self.assertRaisesRegex(ValueError, "changed native bindings"):
            PhaseMemberAdjacencyPropagation(
                fit, analysis, projection, forged_template
            )

        forged_relation = replace(output, adjacency_relations=())
        with self.assertRaisesRegex(ValueError, "changed native bindings"):
            PhaseMemberAdjacencyPropagation(
                fit, analysis, projection, forged_relation
            )

        local_bindings = list(fit.role_bindings)
        local_bindings[3] = replace(
            local_bindings[3], use=SequenceBindingUse.LOCAL_REFINEMENT
        )
        local_fit = replace(
            fit,
            role_bindings=tuple(local_bindings),
            phase_support_coverage=float(
                replace(fit, role_bindings=tuple(local_bindings)).phase_support_count
            ),
        )
        local_output_bindings = list(output.role_bindings)
        local_output_bindings[3] = replace(
            local_output_bindings[3], use=SequenceBindingUse.LOCAL_REFINEMENT
        )
        local_output = replace(
            output,
            role_bindings=tuple(local_output_bindings),
            phase_support_coverage=float(
                replace(output, role_bindings=tuple(local_output_bindings)).phase_support_count
            ),
        )
        PhaseMemberAdjacencyPropagation(
            local_fit, analysis, projection, local_output
        )
        forged_local_anchor = list(local_output.role_bindings)
        forged_local_anchor[3] = replace(
            forged_local_anchor[3], use=SequenceBindingUse.PHASE_ANCHOR
        )
        with self.assertRaisesRegex(ValueError, "changed native bindings"):
            PhaseMemberAdjacencyPropagation(
                local_fit,
                analysis,
                projection,
                replace(local_output, role_bindings=tuple(forged_local_anchor)),
            )

    def test_assess_resource_precheck_stops_before_adjacency_refit(self):
        fit, phase_input, analysis, _edges, _bands = self._fixture("narrow")
        self.assertEqual(fit.adjacency_relations, ())
        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
        self.assertTrue(analysis.relations)

        lane, scope, member = self._assess_lane(fit, phase_input)
        proof = assess_phase_member_output(
            lane,
            scope,
            member,
            available_work_units=0,
        )
        self.assertEqual(proof.scope_id, scope.scope_id)
        self.assertEqual(proof.record_ordinal, member.record_ordinal)
        self.assertEqual(proof.gaps, (PhaseMemberOutputGap.WORK_BOUND_EXCEEDED,))
        self.assertIsNone(proof.adjacency_propagation)
        self.assertEqual(proof.work.adjacency_refit_count, 0)
        self.assertEqual(proof.work.adjacency_direct_fit_count, 0)
        self.assertEqual(proof.work.adjacency_nominal_grid_solve_count, 0)
        self.assertEqual(proof.work.width_evaluation_count, 0)
        self.assertIsNone(proof.cross_context)
        self.assertIsNone(proof.placement)

    def test_assess_with_budget_refits_once_and_forwards_relation_to_cross_owner(self):
        fit, phase_input, _analysis, _edges, _bands = self._fixture("narrow")
        lane, scope, member = self._assess_lane(
            fit,
            phase_input,
            base_cross_registration=object(),
        )
        observed_sequence_fits = []

        def bounded_cross_probe(*_args, **kwargs):
            observed_sequence_fits.append(kwargs["sequence_fits"])
            raise ValueError("bounded Cross owner probe")

        with patch(
            "x5crop.detection.photo_geometry.template_phase_output.prepare_template_cross_context",
            side_effect=bounded_cross_probe,
        ):
            proof = assess_phase_member_output(
                lane,
                scope,
                member,
                available_work_units=10**9,
            )
        self.assertEqual(proof.gaps, (PhaseMemberOutputGap.CROSS_CONTEXT_UNAVAILABLE,))
        self.assertIsNotNone(proof.adjacency_propagation)
        assert proof.adjacency_propagation is not None
        self.assertEqual(proof.work.adjacency_refit_count, 1)
        self.assertEqual(proof.work.adjacency_direct_fit_count, 1)
        self.assertEqual(proof.work.adjacency_nominal_grid_solve_count, 0)
        self.assertEqual(proof.work.width_evaluation_count, 1)
        self.assertEqual(proof.work.cross_context_count, 1)
        self.assertEqual(len(observed_sequence_fits), 1)
        self.assertIsNotNone(proof.adjacency_propagation.output_fit)
        assert proof.adjacency_propagation.output_fit is not None
        self.assertEqual(
            observed_sequence_fits[0][0].adjacency_relations,
            proof.adjacency_propagation.output_fit.adjacency_relations,
        )
        self.assertTrue(proof.adjacency_propagation.analysis.relations)

    def test_output_work_rejects_second_refit_or_overcounted_solver(self):
        PhaseMemberOutputWork(
            adjacency_refit_count=1,
            adjacency_direct_fit_count=1,
        )
        PhaseMemberOutputWork(
            adjacency_refit_count=1,
            adjacency_nominal_grid_solve_count=1,
            adjacency_nominal_grid_solve_success_count=1,
        )
        for values in (
            {"adjacency_refit_count": 2},
            {
                "adjacency_refit_count": 1,
                "adjacency_direct_fit_count": 1,
                "adjacency_nominal_grid_solve_count": 1,
            },
            {
                "adjacency_refit_count": 1,
                "adjacency_nominal_grid_solve_count": 1,
                "adjacency_nominal_grid_solve_success_count": 2,
            },
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                PhaseMemberOutputWork(**values)


if __name__ == "__main__":
    unittest.main()
