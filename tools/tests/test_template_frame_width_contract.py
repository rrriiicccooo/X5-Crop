from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_template,
    placement_sequence,
    placement_template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    apply_correlated_frame_width_inference,
    apply_selected_source_frame_width,
    calibrate_source_frame_width,
    SourceFrameWidthAuthorityFailureKind,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_adjacency_coverage import (
    AdjacencyCoverageState,
    AdjacencyObservationCoverage,
    AdjacencyTraceCoverage,
)
from x5crop.detection.photo_geometry.template_model import (
    FrameWidthInferenceFailureKind,
    SequenceBindingUse,
)
from x5crop.detection.photo_geometry.template_lattice_authority import (
    assess_global_lattice_authority,
    direct_role_constraint_rank,
)
from x5crop.detection.photo_geometry.template_outer_frame_authority import (
    assess_outer_frame_observation_authority,
)
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.formats import FramePhysicalSpec


class TemplateFrameWidthContractTest(unittest.TestCase):
    @staticmethod
    def _with_selected_width_prerequisites(phase, observations):
        assert phase.best is not None
        facts = tuple(
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
                independent_support_region_count=3,
                bases=(DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,),
                blocking_material_conflict_ids=(),
                state=EvidenceState.SUPPORTED,
            )
            for role_index, binding in enumerate(phase.best.role_bindings)
            if binding is not None
        )
        direct = DirectRoleBindingAuthority(
            state=EvidenceState.SUPPORTED,
            facts=facts,
            unsupported_role_indices=(),
            reason=None,
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=phase.template,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(phase.template),
            scale_px_per_mm=None,
            holder_span_px=None,
            phase_authority_px=None,
        )
        lattice = assess_global_lattice_authority(
            phase.best,
            phase_input,
            direct_role_authority=direct,
        )
        return replace(
            phase,
            direct_role_binding_authority=direct,
            global_lattice_authority=lattice,
        )

    @classmethod
    def _with_rank_two_selected_width_prerequisites(
        cls,
        phase,
        observations,
    ):
        assert phase.best is not None
        retained_phase_anchor = False
        bindings = []
        for binding in phase.best.role_bindings:
            if binding is None:
                bindings.append(None)
            elif not retained_phase_anchor:
                retained_phase_anchor = True
                bindings.append(binding)
            else:
                bindings.append(
                    replace(binding, use=SequenceBindingUse.LOCAL_REFINEMENT)
                )
        selected = replace(
            phase,
            best=replace(
                phase.best,
                role_bindings=tuple(bindings),
                phase_support_coverage=1.0,
            ),
        )
        selected = cls._with_selected_width_prerequisites(
            selected,
            observations,
        )
        assert selected.best is not None
        direct = selected.direct_role_binding_authority
        assert direct is not None
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=selected.template,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(selected.template),
            scale_px_per_mm=None,
            holder_span_px=None,
            phase_authority_px=None,
            global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                pitch_observation_ids=(observations[-1].observation_id,),
            ),
        )
        lattice = assess_global_lattice_authority(
            selected.best,
            phase_input,
            direct_role_authority=direct,
        )
        if lattice.joint_constraint_rank != 2:
            raise AssertionError("rank-two source-W test fixture is invalid")
        return replace(
            selected,
            global_lattice_authority=lattice,
            outer_frame_observation_authority=(
                assess_outer_frame_observation_authority(selected.best)
            ),
        )

    @staticmethod
    def _local_role_fixture(*, local: bool = True):
        template = placement_template(4)
        original = placement_sequence(template)
        bindings = list(original.role_bindings)
        assert bindings[4] is not None
        if local:
            bindings[4] = replace(
                bindings[4],
                use=SequenceBindingUse.LOCAL_REFINEMENT,
            )
        fit = replace(original, role_bindings=tuple(bindings))
        observations = tuple(
            replace(
                phase_edge(f"sequence:{index}", coordinate),
                qualified_anchor_roles=(
                    BoundaryRole.START
                    if index % 2 == 0
                    else BoundaryRole.END,
                ),
                trace_coordinates_px=(
                    (10, 20) if index == 4 else (0, 10, 20)
                ),
                support_fraction=(2.0 / 3.0 if index == 4 else 1.0),
                continuous_support_fraction=(
                    2.0 / 3.0 if index == 4 else 1.0
                ),
            )
            for index, coordinate in enumerate(
                original.model_role_positions_px
            )
        )
        facts = tuple(
            DirectRoleAuthorityFact(
                role_index=index,
                lane_ordinal=index // 2 + 1,
                role=(
                    BoundaryRole.START
                    if index % 2 == 0
                    else BoundaryRole.END
                ),
                observation_id=ObservationId(f"sequence:{index}"),
                evidence_group_id=ObservationId(f"sequence:{index}"),
                independent_support_region_count=(2 if index == 4 else 3),
                bases=(
                    ()
                    if index == 4
                    else (DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,)
                ),
                blocking_material_conflict_ids=(),
                state=(
                    EvidenceState.UNAVAILABLE
                    if index == 4
                    else EvidenceState.SUPPORTED
                ),
            )
            for index in range(8)
        )
        authority = DirectRoleBindingAuthority(
            state=EvidenceState.UNAVAILABLE,
            facts=facts,
            unsupported_role_indices=(4,),
            reason="role 4 has no coordinate authority",
        )
        return fit, observations, authority

    def test_lattice_rank_counts_one_row_per_physical_evidence_group(
        self,
    ) -> None:
        observations = (
            phase_edge("rank-group:start:1", 40.0),
            phase_edge("rank-group:end:1", 140.0),
            phase_edge("rank-group:start:2", 160.0),
            phase_edge("rank-group:end:2", 260.0),
        )
        phase = fit_template_phase(observations, phase_template(2))
        assert phase.best is not None
        bindings = list(phase.best.role_bindings)
        assert all(binding is not None for binding in bindings)
        shared_group = ObservationId("rank-group:shared-separator")
        bindings[1] = replace(bindings[1], evidence_group_id=shared_group)
        bindings[2] = replace(bindings[2], evidence_group_id=shared_group)
        bindings[3] = None
        correlated = replace(
            phase.best,
            role_bindings=tuple(bindings),
            phase_support_coverage=2.0,
        )

        self.assertEqual(direct_role_constraint_rank(correlated), 2)
        bindings[3] = phase.best.role_bindings[3]
        independent = replace(correlated, role_bindings=tuple(bindings))
        self.assertEqual(direct_role_constraint_rank(independent), 3)

    def test_non_adjacent_direct_frames_close_one_source_width_hull(self) -> None:
        observations = (
            phase_edge("frame-1-start", 40.0),
            phase_edge("frame-1-end", 139.0),
            phase_edge("frame-3-start", 280.0),
            phase_edge("frame-3-end", 381.0),
        )
        phase = fit_template_phase(observations, phase_template(3))
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        phase = self._with_selected_width_prerequisites(phase, observations)
        calibrated, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        width = calibrated.width_state.extent_projection_px()
        self.assertEqual(width, FiniteInterval.exact(100.0))
        self.assertEqual(len(calibrated.width_state.observation_ids), 4)
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(authority.supporting_frame_ordinals, (1, 3))
        self.assertEqual(
            authority.observation_ids,
            calibrated.width_state.observation_ids,
        )
        self.assertEqual(
            authority.observation_ids,
            tuple(sorted(authority.observation_ids, key=str)),
        )
        selected = apply_selected_source_frame_width(phase, authority)
        assert selected.best is not None and phase.best is not None
        self.assertEqual(selected.runner_up, phase.runner_up)
        self.assertEqual(
            selected.best.binding_observation_ids,
            phase.best.binding_observation_ids,
        )
        self.assertEqual(
            selected.best.model_role_positions_px,
            phase.best.model_role_positions_px,
        )
        self.assertGreaterEqual(
            selected.best.pitch_fit.frame_width_px.minimum,
            width.minimum,
        )
        self.assertLessEqual(
            selected.best.pitch_fit.frame_width_px.maximum,
            width.maximum,
        )
        self.assertLessEqual(
            selected.best.pitch_fit.frame_width_px.minimum,
            selected.best.pitch_fit.canonical_frame_width_px,
        )
        self.assertGreaterEqual(
            selected.best.pitch_fit.frame_width_px.maximum,
            selected.best.pitch_fit.canonical_frame_width_px,
        )

    def test_selected_width_conflict_is_typed_counterevidence(self) -> None:
        observations = (
            phase_edge("conflicting-frame-1-start", 40.0),
            phase_edge("conflicting-frame-1-end", 139.0),
            phase_edge("conflicting-frame-3-start", 280.0),
            phase_edge("conflicting-frame-3-end", 381.0),
        )
        phase = fit_template_phase(observations, phase_template(3))
        phase = self._with_selected_width_prerequisites(phase, observations)
        assert phase.best is not None
        phase = replace(
            phase,
            best=replace(
                phase.best,
                pitch_fit=replace(
                    phase.best.pitch_fit,
                    frame_width_px=FiniteInterval(80.0, 90.0),
                    canonical_frame_width_px=85.0,
                ),
            ),
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        retained, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(retained, source)
        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            authority.failure_kind,
            SourceFrameWidthAuthorityFailureKind.PHYSICAL_WIDTH_CONFLICT,
        )
        rejected = apply_selected_source_frame_width(phase, authority)
        self.assertEqual(rejected.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            rejected.failure_kind,
            PhaseFailureKind.SOURCE_FRAME_WIDTH_CONFLICT,
        )

    def test_source_width_never_resolves_an_ambiguous_placement(self) -> None:
        observations = (
            phase_edge("frame-1-start", 40.0),
            phase_edge("frame-1-end", 139.0),
            phase_edge("frame-3-start", 280.0),
            phase_edge("frame-3-end", 381.0),
        )
        phase = fit_template_phase(observations, phase_template(3))
        phase = self._with_selected_width_prerequisites(phase, observations)
        ambiguous = replace(
            phase,
            status=PhaseFitStatus.AMBIGUOUS,
            ambiguity_reason="test discrete runner remains",
            failure_kind=PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
            winner_basis=None,
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        retained, authority = calibrate_source_frame_width(
            source,
            ambiguous,
            observations,
        )

        self.assertEqual(retained, source)
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            authority.failure_kind,
            SourceFrameWidthAuthorityFailureKind.UNIQUE_PLACEMENT_UNAVAILABLE,
        )

    def test_rank_two_selected_lattice_can_close_source_width(self) -> None:
        observations = (
            phase_edge("rank-two-frame-1-start", 40.0),
            phase_edge("rank-two-frame-1-end", 139.0),
            phase_edge("rank-two-frame-3-start", 280.0),
            phase_edge("rank-two-frame-3-end", 381.0),
        )
        phase = self._with_rank_two_selected_width_prerequisites(
            fit_template_phase(observations, phase_template(3)),
            observations,
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        calibrated, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(authority.supporting_frame_ordinals, (1, 3))
        self.assertEqual(
            calibrated.width_state.observation_ids,
            authority.observation_ids,
        )
        selected = apply_selected_source_frame_width(phase, authority)
        assert selected.best is not None
        closed_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=phase.template,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(phase.template),
            scale_px_per_mm=None,
            holder_span_px=None,
            phase_authority_px=None,
            global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                frame_width_observation_ids=authority.observation_ids,
                pitch_observation_ids=(observations[-1].observation_id,),
            ),
        )
        closed = assess_global_lattice_authority(
            selected.best,
            closed_input,
            direct_role_authority=phase.direct_role_binding_authority,
        )
        self.assertEqual(closed.state, EvidenceState.SUPPORTED)
        self.assertEqual(closed.joint_constraint_rank, 3)

    def test_rank_one_lattice_cannot_claim_source_width(self) -> None:
        observations = (
            phase_edge("rank-one-frame-1-start", 40.0),
            phase_edge("rank-one-frame-1-end", 139.0),
            phase_edge("rank-one-frame-3-start", 280.0),
            phase_edge("rank-one-frame-3-end", 381.0),
        )
        phase = self._with_rank_two_selected_width_prerequisites(
            fit_template_phase(observations, phase_template(3)),
            observations,
        )
        assert phase.best is not None
        rank_one_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=phase.template,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(phase.template),
            scale_px_per_mm=None,
            holder_span_px=None,
            phase_authority_px=None,
        )
        phase = replace(
            phase,
            global_lattice_authority=assess_global_lattice_authority(
                phase.best,
                rank_one_input,
                direct_role_authority=phase.direct_role_binding_authority,
            ),
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        retained, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(retained, source)
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            authority.failure_kind,
            SourceFrameWidthAuthorityFailureKind.GLOBAL_LATTICE_RANK_INSUFFICIENT,
        )

    def test_incomplete_inferred_adjacency_blocks_source_width(self) -> None:
        observations = (
            phase_edge("coverage-frame-1-start", 40.0),
            phase_edge("coverage-frame-1-end", 139.0),
            phase_edge("coverage-frame-3-start", 280.0),
            phase_edge("coverage-frame-3-end", 381.0),
        )
        phase = self._with_rank_two_selected_width_prerequisites(
            fit_template_phase(observations, phase_template(3)),
            observations,
        )
        incomplete_trace = AdjacencyTraceCoverage(
            trace_position_px=10,
            covering_query_ids=(),
            covered_intervals_px=(),
            required_coordinate_count=11,
            covered_coordinate_count=0,
            complete=False,
        )
        complete_trace = AdjacencyTraceCoverage(
            trace_position_px=10,
            covering_query_ids=("complete-query",),
            covered_intervals_px=(FiniteInterval(0.0, 10.0),),
            required_coordinate_count=11,
            covered_coordinate_count=11,
            complete=True,
        )
        phase = replace(
            phase,
            adjacency_observation_coverage=(
                AdjacencyObservationCoverage(
                    relation_ordinal=1,
                    required_interval_px=FiniteInterval(140.0, 160.0),
                    covering_query_ids=(),
                    trace_coverage=(incomplete_trace,),
                    required_trace_count=1,
                    covered_trace_count=0,
                    required_coordinate_count=11,
                    covered_coordinate_count=0,
                    normal_inference_required=True,
                    state=AdjacencyCoverageState.INCOMPLETE,
                ),
                AdjacencyObservationCoverage(
                    relation_ordinal=2,
                    required_interval_px=FiniteInterval(260.0, 280.0),
                    covering_query_ids=("complete-query",),
                    trace_coverage=(complete_trace,),
                    required_trace_count=1,
                    covered_trace_count=1,
                    required_coordinate_count=11,
                    covered_coordinate_count=11,
                    normal_inference_required=False,
                    state=AdjacencyCoverageState.COMPLETE,
                ),
            ),
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        retained, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(retained, source)
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            authority.failure_kind,
            SourceFrameWidthAuthorityFailureKind.ADJACENCY_COVERAGE_INCOMPLETE,
        )

    def test_direct_role_contradiction_precedes_source_width(self) -> None:
        observations = (
            phase_edge("conflict-frame-1-start", 40.0),
            phase_edge("conflict-frame-1-end", 139.0),
            phase_edge("conflict-frame-3-start", 280.0),
            phase_edge("conflict-frame-3-end", 381.0),
        )
        phase = self._with_rank_two_selected_width_prerequisites(
            fit_template_phase(observations, phase_template(3)),
            observations,
        )
        direct = phase.direct_role_binding_authority
        assert direct is not None
        conflict = replace(
            direct.facts[0],
            bases=(),
            blocking_material_conflict_ids=(ObservationId("material-conflict"),),
            state=EvidenceState.CONTRADICTED,
        )
        contradicted = DirectRoleBindingAuthority(
            state=EvidenceState.CONTRADICTED,
            facts=(conflict, *direct.facts[1:]),
            unsupported_role_indices=(conflict.role_index,),
            reason="direct role has material conflict",
        )
        phase = replace(
            phase,
            direct_role_binding_authority=contradicted,
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        retained, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(retained, source)
        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            authority.failure_kind,
            SourceFrameWidthAuthorityFailureKind.DIRECT_ROLE_AUTHORITY_CONTRADICTED,
        )

    def test_one_source_width_authority_infers_multiple_opposite_roles(self) -> None:
        template = placement_template(4)
        fit = placement_sequence(template, missing=(5, 7))
        authority_ids = tuple(
            ObservationId(f"sequence:{index}") for index in range(4)
        )

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=authority_ids,
        )

        inference = assessed.frame_width_inference
        self.assertIsNotNone(inference)
        assert inference is not None
        self.assertEqual(inference.state, EvidenceState.SUPPORTED)
        self.assertEqual(inference.inferred_role_indices, (5, 7))
        self.assertEqual(inference.supporting_frame_ordinals, (1, 2))
        self.assertEqual(inference.observation_ids, authority_ids)
        self.assertFalse(inference.validation_only_role_indices)
        self.assertFalse(inference.validation_observation_ids)
        self.assertEqual(
            inference.width_px,
            fit.pitch_fit.frame_width_px,
        )
        self.assertEqual(assessed.pitch_fit, fit.pitch_fit)

    def test_local_weak_coordinate_yields_to_correlated_width(self) -> None:
        fit, observations, authority = self._local_role_fixture()
        width_ids = tuple(
            ObservationId(f"sequence:{index}") for index in range(4)
        )

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=width_ids,
            direct_role_authority=authority,
            sequence_edges=observations,
        )

        self.assertIsNone(assessed.role_bindings[4])
        inference = assessed.frame_width_inference
        assert inference is not None
        self.assertEqual(inference.state, EvidenceState.SUPPORTED)
        self.assertEqual(inference.inferred_role_indices, (4,))
        self.assertEqual(inference.supporting_frame_ordinals, (1, 2))
        self.assertEqual(inference.validation_only_role_indices, (4,))
        self.assertEqual(
            inference.validation_observation_ids,
            (ObservationId("sequence:4"),),
        )
        self.assertEqual(inference.observation_ids, width_ids)

    def test_phase_anchor_never_yields_to_source_width(self) -> None:
        fit, observations, authority = self._local_role_fixture(local=False)

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=tuple(
                ObservationId(f"sequence:{index}") for index in range(4)
            ),
            direct_role_authority=authority,
            sequence_edges=observations,
        )

        self.assertIsNotNone(assessed.role_bindings[4])
        self.assertIsNone(assessed.frame_width_inference)

    def test_width_evidence_that_uses_the_weak_line_cannot_demote_it(
        self,
    ) -> None:
        fit, observations, authority = self._local_role_fixture()

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=(
                ObservationId("sequence:0"),
                ObservationId("sequence:1"),
                ObservationId("sequence:2"),
                ObservationId("sequence:4"),
            ),
            direct_role_authority=authority,
            sequence_edges=observations,
        )

        self.assertIsNotNone(assessed.role_bindings[4])
        self.assertIsNone(assessed.frame_width_inference)

    def test_multiple_compatible_local_lines_remain_unresolved(self) -> None:
        fit, observations, authority = self._local_role_fixture()
        alternate = replace(
            observations[4],
            observation_id=ObservationId("alternate:start:3"),
        )

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=tuple(
                ObservationId(f"sequence:{index}") for index in range(4)
            ),
            direct_role_authority=authority,
            sequence_edges=(*observations, alternate),
        )

        self.assertIsNotNone(assessed.role_bindings[4])
        self.assertIsNone(assessed.frame_width_inference)

    def test_grid_cannot_create_a_frame_with_both_roles_unobserved(self) -> None:
        template = placement_template(3)
        fit = placement_sequence(template, missing=(4, 5))

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=tuple(
                ObservationId(f"sequence:{index}") for index in range(4)
            ),
        )

        inference = assessed.frame_width_inference
        self.assertIsNotNone(inference)
        assert inference is not None
        self.assertEqual(inference.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            inference.failure_kind,
            FrameWidthInferenceFailureKind.COMPLETE_FRAME_UNOBSERVED,
        )

    def test_one_complete_frame_cannot_claim_source_common_width(self) -> None:
        template = placement_template(2)
        fit = placement_sequence(template, missing=(3,))

        assessed = apply_correlated_frame_width_inference(
            fit,
            frame_width_observation_ids=(
                ObservationId("sequence:0"),
                ObservationId("sequence:1"),
            ),
        )

        inference = assessed.frame_width_inference
        self.assertIsNotNone(inference)
        assert inference is not None
        self.assertEqual(inference.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            inference.failure_kind,
            FrameWidthInferenceFailureKind.COMMON_WIDTH_AUTHORITY_UNAVAILABLE,
        )


if __name__ == "__main__":
    unittest.main()
