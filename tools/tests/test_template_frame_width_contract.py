from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
    placement_template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.template_contact import observe_contact_edges
from x5crop.detection.photo_geometry.template_frame_width import (
    apply_correlated_frame_width_inference,
    apply_placement_source_frame_width,
    assess_placement_source_frame_width_topology,
    calibrate_source_frame_width,
    SourceFrameWidthAuthority,
    SourceFrameWidthAuthorityFailureKind,
    SourceFrameWidthAuthorityPlacementScope,
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
from x5crop.detection.photo_geometry.template_adjacency_topology import (
    observe_adjacency_continuity,
)
from x5crop.detection.photo_geometry.template_model import (
    FrameWidthInferenceFailureKind,
    SeparatorRelation,
    SequenceBindingUse,
    SourceFrameWidthAuthorityBasis,
    measured_separator_relation_kind,
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
    SourceFrameWidthTopologyFailureKind,
    TemplatePhaseInput,
)
from x5crop.formats import FramePhysicalSpec


class TemplateFrameWidthContractTest(unittest.TestCase):
    @staticmethod
    def _independent_width_authority(
        fit,
        observation_ids: tuple[ObservationId, ...],
        *,
        supporting_frame_ordinals: tuple[int, ...] = (1, 2),
    ) -> SourceFrameWidthAuthority:
        return SourceFrameWidthAuthority(
            authority_id="test-independent-source-width",
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
                and binding.observation_id in set(observation_ids)
                else None
                for binding in fit.role_bindings
            ),
            basis=(
                SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES
            ),
            supporting_frame_ordinals=supporting_frame_ordinals,
            supporting_constraint_ids=(),
            width_px=FiniteInterval(
                fit.pitch_fit.frame_width_px.minimum,
                fit.pitch_fit.frame_width_px.maximum,
            ),
            canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
            observation_ids=observation_ids,
            failure_kind=None,
            reason=None,
        )

    @classmethod
    def _source_width_topology_fixture(
        cls,
        previous_end_interval: FiniteInterval,
    ):
        observations = tuple(
            phase_edge(f"source-width-topology:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 160.0, 260.0, 280.0, 380.0, 400.0, 500.0)
            )
        )
        phase = fit_template_phase(observations, phase_template(4))
        assert phase.best is not None
        bindings = list(phase.best.role_bindings)
        assert bindings[3] is not None and bindings[4] is not None
        bindings[3] = replace(
            bindings[3],
            canonical_position_px=previous_end_interval.center,
            fit_position_interval_px=previous_end_interval,
            full_position_interval_px=previous_end_interval,
        )
        bindings[4] = None
        selected = replace(
            phase.best,
            role_bindings=tuple(bindings),
        )
        phase = replace(phase, best=selected)
        authority = cls._independent_width_authority(
            selected,
            tuple(
                observations[index].observation_id
                for index in (0, 1, 6, 7)
            ),
            supporting_frame_ordinals=(1, 4),
        )
        return phase, authority

    @staticmethod
    def _apply_width_and_topology(phase, authority):
        selected = apply_placement_source_frame_width(phase, authority)
        assert selected.best is not None
        inferred = apply_correlated_frame_width_inference(
            selected.best,
            source_frame_width_authority=authority,
        )
        return assess_placement_source_frame_width_topology(
            replace(selected, best=inferred),
            authority,
        )

    def test_source_width_inference_preserves_normal_adjacency_for_full_interval(
        self,
    ) -> None:
        phase, authority = self._source_width_topology_fixture(
            FiniteInterval(259.8, 260.2)
        )

        selected = self._apply_width_and_topology(phase, authority)

        self.assertEqual(selected.status, PhaseFitStatus.RESOLVED)
        assessment = selected.source_frame_width_topology_assessment
        assert assessment is not None
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertIsNone(assessment.failure_kind)
        self.assertEqual(len(assessment.facts), 1)
        self.assertEqual(assessment.facts[0].relation_ordinal, 2)
        self.assertEqual(assessment.facts[0].inferred_role_indices, (4,))
        self.assertGreaterEqual(
            assessment.facts[0].signed_gap_interval_px.minimum,
            0.0,
        )

    def test_source_width_inference_cannot_choose_a_favorable_normal_state(
        self,
    ) -> None:
        phase, authority = self._source_width_topology_fixture(
            FiniteInterval(270.0, 290.0)
        )

        selected = self._apply_width_and_topology(phase, authority)

        self.assertEqual(selected.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            selected.failure_kind,
            PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED,
        )
        assessment = selected.source_frame_width_topology_assessment
        assert assessment is not None
        self.assertEqual(assessment.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            assessment.failure_kind,
            SourceFrameWidthTopologyFailureKind.NORMAL_ADJACENCY_UNRESOLVED,
        )
        self.assertLess(assessment.facts[0].signed_gap_interval_px.minimum, 0.0)
        self.assertGreater(
            assessment.facts[0].signed_gap_interval_px.maximum,
            0.0,
        )

    def test_source_width_inference_reports_certain_unproved_overlap(
        self,
    ) -> None:
        phase, authority = self._source_width_topology_fixture(
            FiniteInterval(285.0, 295.0)
        )

        selected = self._apply_width_and_topology(phase, authority)

        self.assertEqual(selected.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            selected.failure_kind,
            PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED,
        )
        assessment = selected.source_frame_width_topology_assessment
        assert assessment is not None
        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            assessment.failure_kind,
            SourceFrameWidthTopologyFailureKind.NORMAL_ADJACENCY_CONTRADICTED,
        )
        self.assertLess(assessment.facts[0].signed_gap_interval_px.maximum, 0.0)

    def test_unavailable_width_inference_does_not_claim_topology_ownership(
        self,
    ) -> None:
        phase, _authority = self._source_width_topology_fixture(
            FiniteInterval(259.8, 260.2)
        )
        assert phase.best is not None
        bindings = list(phase.best.role_bindings)
        bindings[5] = None
        fit = replace(phase.best, role_bindings=tuple(bindings))
        phase = replace(phase, best=fit)
        authority = self._independent_width_authority(
            fit,
            tuple(
                binding.observation_id
                for index in (0, 1, 6, 7)
                if (binding := fit.role_bindings[index]) is not None
            ),
            supporting_frame_ordinals=(1, 4),
        )
        selected = apply_placement_source_frame_width(phase, authority)
        assert selected.best is not None
        inferred = apply_correlated_frame_width_inference(
            selected.best,
            source_frame_width_authority=authority,
        )

        assessed = assess_placement_source_frame_width_topology(
            replace(selected, best=inferred),
            authority,
        )

        assert inferred.frame_width_inference is not None
        self.assertEqual(
            inferred.frame_width_inference.failure_kind,
            FrameWidthInferenceFailureKind.COMPLETE_FRAME_UNOBSERVED,
        )
        self.assertEqual(assessed.status, PhaseFitStatus.RESOLVED)
        topology = assessed.source_frame_width_topology_assessment
        assert topology is not None
        self.assertEqual(topology.state, EvidenceState.SUPPORTED)
        self.assertFalse(topology.facts)

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
        self.assertEqual(
            authority.basis,
            SourceFrameWidthAuthorityBasis.RECONCILED_DIRECT_CONSTRAINTS,
        )
        self.assertEqual(len(authority.supporting_constraint_ids), 4)
        self.assertEqual(authority.supporting_frame_ordinals, (1, 3))
        self.assertEqual(
            authority.observation_ids,
            calibrated.width_state.observation_ids,
        )
        self.assertEqual(
            authority.observation_ids,
            tuple(sorted(authority.observation_ids, key=str)),
        )
        selected = apply_placement_source_frame_width(phase, authority)
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

    def test_complete_frames_and_direct_lattice_reconcile_one_source_width(
        self,
    ) -> None:
        observations = (
            phase_edge("a-frame-1-start", 40.0),
            phase_edge("b-frame-1-end", 140.0),
            phase_edge("c-frame-3-start", 280.0),
            replace(
                phase_edge("z-frame-3-end", 380.0),
                full_position_interval_px=FiniteInterval(370.0, 390.0),
            ),
        )
        phase = self._with_selected_width_prerequisites(
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
        self.assertEqual(
            authority.basis,
            SourceFrameWidthAuthorityBasis.RECONCILED_DIRECT_CONSTRAINTS,
        )
        self.assertEqual(authority.supporting_frame_ordinals, (1, 3))
        self.assertEqual(len(authority.supporting_constraint_ids), 4)
        self.assertEqual(len(authority.observation_ids), 4)
        self.assertEqual(
            calibrated.width_state.extent_projection_px(),
            FiniteInterval.exact(100.0),
        )

    def test_direct_lattice_width_consumes_every_retained_constraint(
        self,
    ) -> None:
        template = replace(
            phase_template(3),
            frame_width_px=FiniteInterval(90.0, 110.0),
            nominal_gap_px=FiniteInterval(10.0, 30.0),
        )
        observations = (
            replace(
                phase_edge("a-wide-frame-1-end", 140.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                full_position_interval_px=FiniteInterval(130.0, 150.0),
                polarity=-1,
            ),
            replace(
                phase_edge("b-frame-2-start", 160.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                phase_edge("c-frame-3-start", 280.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                phase_edge("d-frame-3-end", 380.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            ),
        )
        phase = self._with_selected_width_prerequisites(
            fit_template_phase(
                observations,
                template,
                phase_authority_px=FiniteInterval(39.0, 41.0),
            ),
            observations,
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval(9.0, 11.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        _calibrated, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            authority.basis,
            SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE,
        )
        self.assertEqual(len(authority.supporting_constraint_ids), 4)
        self.assertEqual(len(authority.observation_ids), 4)
        assert authority.width_px is not None
        self.assertGreater(authority.width_px.minimum, 96.0)
        self.assertLess(authority.width_px.maximum, 104.0)

    def test_incompatible_retained_direct_constraint_is_width_conflict(
        self,
    ) -> None:
        template = replace(
            phase_template(3),
            frame_width_px=FiniteInterval(90.0, 110.0),
            nominal_gap_px=FiniteInterval(10.0, 30.0),
        )
        observations = (
            replace(
                phase_edge("a-wide-frame-1-end", 140.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                full_position_interval_px=FiniteInterval(130.0, 150.0),
                polarity=-1,
            ),
            replace(
                phase_edge("b-frame-2-start", 160.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                phase_edge("c-frame-3-start", 280.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                phase_edge("d-frame-3-end", 380.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            ),
        )
        phase = self._with_selected_width_prerequisites(
            fit_template_phase(
                observations,
                template,
                phase_authority_px=FiniteInterval(39.0, 41.0),
            ),
            observations,
        )
        lattice = phase.global_lattice_authority
        assert lattice is not None
        contradictory = tuple(
            replace(
                constraint,
                value_interval_px=FiniteInterval(409.8, 410.2),
            )
            if constraint.role_index == 5
            else constraint
            for constraint in lattice.constraints
        )
        phase = replace(
            phase,
            global_lattice_authority=replace(
                lattice,
                constraints=contradictory,
            ),
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval(9.0, 11.0),
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
        self.assertEqual(
            authority.reason,
            "direct lattice canonical W leaves the physical source state",
        )

    def test_overdetermined_direct_residual_reconciles_complete_frame_width(
        self,
    ) -> None:
        observations = (
            phase_edge("a-frame-1-start", 40.0),
            phase_edge("b-frame-1-end", 140.0),
            phase_edge("c-frame-3-start", 280.0),
            phase_edge("z-frame-3-end", 380.0),
        )
        phase = self._with_selected_width_prerequisites(
            fit_template_phase(observations, phase_template(3)),
            observations,
        )
        lattice = phase.global_lattice_authority
        assert phase.best is not None and lattice is not None
        constraints = tuple(
            replace(
                constraint,
                value_interval_px=FiniteInterval(145.0, 145.0),
            )
            if constraint.role_index == 1
            else constraint
            for constraint in lattice.constraints
        )
        phase = replace(
            phase,
            best=replace(
                phase.best,
                pitch_fit=replace(
                    phase.best.pitch_fit,
                    frame_width_px=FiniteInterval(90.0, 110.0),
                ),
            ),
            global_lattice_authority=replace(
                lattice,
                constraints=constraints,
            ),
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
        self.assertEqual(
            authority.basis,
            SourceFrameWidthAuthorityBasis.RECONCILED_DIRECT_CONSTRAINTS,
        )
        self.assertEqual(len(authority.supporting_constraint_ids), 4)
        width = calibrated.width_state.extent_projection_px()
        self.assertTrue(width.contains(100.0))
        self.assertLess(width.maximum - width.minimum, 1.0)

    def test_rank_three_direct_roles_close_correlated_source_width(self) -> None:
        observations = (
            replace(
                phase_edge("rank-three-frame-1-end", 140.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            ),
            replace(
                phase_edge("rank-three-frame-2-start", 160.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                phase_edge("rank-three-frame-3-start", 280.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
        )
        phase = fit_template_phase(
            observations,
            phase_template(3),
            phase_authority_px=FiniteInterval(39.0, 41.0),
        )
        phase = self._with_selected_width_prerequisites(
            phase,
            observations,
        )
        assert phase.global_lattice_authority is not None
        self.assertEqual(
            phase.global_lattice_authority.direct_role_constraint_rank,
            3,
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
        self.assertEqual(
            authority.basis,
            SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE,
        )
        self.assertEqual(len(authority.supporting_constraint_ids), 3)
        self.assertFalse(authority.supporting_frame_ordinals)
        self.assertEqual(authority.observation_ids, tuple(
            sorted(
                (item.observation_id for item in observations),
                key=str,
            )
        ))
        self.assertEqual(
            calibrated.width_state.extent_projection_px(),
            FiniteInterval.exact(100.0),
        )
        selected = apply_placement_source_frame_width(phase, authority)
        assert selected.best is not None
        source_binding = selected.best.role_bindings[1]
        assert source_binding is not None
        local_identity = ObservationId("rank-three-unrelated-local")
        local_position = selected.best.model_role_positions_px[0]
        local_bindings = list(selected.best.role_bindings)
        local_bindings[0] = replace(
            source_binding,
            use=SequenceBindingUse.LOCAL_REFINEMENT,
            observation_id=local_identity,
            evidence_group_id=local_identity,
            canonical_position_px=local_position,
            fit_position_interval_px=FiniteInterval.exact(local_position),
            full_position_interval_px=FiniteInterval.exact(local_position),
            line_evidence=None,
        )
        with_unrelated_local = replace(
            selected.best,
            role_bindings=tuple(local_bindings),
        )
        self.assertTrue(
            authority.matches_placement(with_unrelated_local)
        )
        inferred_with_local = apply_correlated_frame_width_inference(
            with_unrelated_local,
            source_frame_width_authority=authority,
        )
        assert inferred_with_local.frame_width_inference is not None
        self.assertEqual(
            inferred_with_local.frame_width_inference.state,
            EvidenceState.SUPPORTED,
        )
        blocked_by_projected_line = apply_correlated_frame_width_inference(
            selected.best,
            source_frame_width_authority=authority,
            projected_counterevidence_role_indices=(0,),
        )
        assert blocked_by_projected_line.frame_width_inference is not None
        self.assertEqual(
            blocked_by_projected_line.frame_width_inference.failure_kind,
            FrameWidthInferenceFailureKind.DIRECT_LATTICE_COUNTEREVIDENCE,
        )
        changed_phase_anchors = list(selected.best.role_bindings)
        changed_phase_anchors[1] = replace(
            source_binding,
            use=SequenceBindingUse.LOCAL_REFINEMENT,
        )
        self.assertFalse(
            authority.matches_placement(
                replace(
                    selected.best,
                    role_bindings=tuple(changed_phase_anchors),
                )
            )
        )
        inferred = apply_correlated_frame_width_inference(
            selected.best,
            source_frame_width_authority=authority,
        )
        assert inferred.frame_width_inference is not None
        self.assertEqual(
            inferred.frame_width_inference.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            inferred.frame_width_inference.inferred_role_indices,
            (0, 3, 5),
        )
        self.assertEqual(
            inferred.frame_width_inference.authority_basis,
            SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE,
        )

    def test_direct_lattice_width_preserves_measured_gap_prefix(self) -> None:
        observations = (
            replace(
                phase_edge("wide-frame-1-end", 140.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            ),
            replace(
                phase_edge("wide-frame-2-start", 165.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                phase_edge("wide-frame-2-end", 265.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            ),
            replace(
                phase_edge("wide-frame-3-start", 285.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
        )
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=measured_separator_relation_kind(5.0),
            delta_interval_px=FiniteInterval.exact(5.0),
            canonical_delta_px=5.0,
            separator_band_observation_id=ObservationId("wide-band:1"),
            end_edge_observation_id=observations[0].observation_id,
            next_start_edge_observation_id=observations[1].observation_id,
            signed_gap_interval_px=FiniteInterval.exact(25.0),
            canonical_signed_gap_px=25.0,
        )
        phase = fit_template_phase(
            observations,
            phase_template(3),
            phase_authority_px=FiniteInterval(39.0, 41.0),
            adjacency_relations=(relation,),
        )
        phase = self._with_selected_width_prerequisites(
            phase,
            observations,
        )
        lattice = phase.global_lattice_authority
        assert lattice is not None
        end_2_constraint = next(
            item
            for item in lattice.constraints
            if item.observation_ids == (observations[2].observation_id,)
        )
        self.assertEqual(
            end_2_constraint.value_interval_px,
            FiniteInterval(
                observations[2].full_position_interval_px.minimum - 25.0,
                observations[2].full_position_interval_px.maximum - 25.0,
            ),
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        _calibrated, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            authority.basis,
            SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE,
        )
        self.assertEqual(authority.width_px, FiniteInterval.exact(100.0))

    def test_source_width_rebinds_measured_delta_without_moving_edges(
        self,
    ) -> None:
        observations = (
            phase_edge("frame-1-start", 40.0),
            phase_edge("frame-1-end", 140.0),
            phase_edge("frame-2-start", 160.0),
            phase_edge("frame-2-end", 260.0),
            phase_edge("frame-3-start", 280.0),
            phase_edge("frame-3-end", 380.0),
        )
        phase = fit_template_phase(observations, phase_template(3))
        assert phase.best is not None
        fit = replace(
            phase.best,
            pitch_fit=replace(
                phase.best.pitch_fit,
                frame_width_px=PositiveInterval(99.0, 101.0),
            ),
        )
        end_binding = fit.role_bindings[1]
        start_binding = fit.role_bindings[2]
        assert end_binding is not None and start_binding is not None
        signed_gap = fit.template.direction * (
            fit.model_role_positions_px[2]
            - fit.model_role_positions_px[1]
        )
        delta = (
            fit.pitch_fit.canonical_frame_width_px
            - fit.pitch_fit.canonical_pitch_px
            + signed_gap
        )
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=measured_separator_relation_kind(delta),
            delta_interval_px=FiniteInterval(delta - 2.0, delta + 2.0),
            canonical_delta_px=delta,
            separator_band_observation_id=ObservationId("separator-band:1"),
            end_edge_observation_id=end_binding.observation_id,
            next_start_edge_observation_id=start_binding.observation_id,
            signed_gap_interval_px=FiniteInterval.exact(signed_gap),
            canonical_signed_gap_px=signed_gap,
        )
        fit = replace(fit, adjacency_relations=(relation,))
        phase = replace(phase, best=fit)
        selected_width = fit.pitch_fit.canonical_frame_width_px + 1.0
        authority = SourceFrameWidthAuthority(
            authority_id="source-width:test",
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
                and binding.observation_id
                in {
                    observations[0].observation_id,
                    observations[1].observation_id,
                    observations[4].observation_id,
                    observations[5].observation_id,
                }
                else None
                for binding in fit.role_bindings
            ),
            basis=(
                SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES
            ),
            supporting_frame_ordinals=(1, 3),
            supporting_constraint_ids=(),
            width_px=FiniteInterval(
                fit.pitch_fit.frame_width_px.minimum,
                fit.pitch_fit.frame_width_px.maximum,
            ),
            canonical_width_px=selected_width,
            observation_ids=tuple(
                sorted(
                    (
                        observations[0].observation_id,
                        observations[1].observation_id,
                        observations[4].observation_id,
                        observations[5].observation_id,
                    ),
                    key=str,
                )
            ),
            failure_kind=None,
            reason=None,
        )

        selected = apply_placement_source_frame_width(phase, authority)

        assert selected.best is not None
        self.assertEqual(
            selected.best.model_role_positions_px,
            fit.model_role_positions_px,
        )
        (selected_relation,) = selected.best.adjacency_relations
        self.assertAlmostEqual(
            selected_relation.canonical_delta_px,
            selected_width
            - fit.pitch_fit.canonical_pitch_px
            + signed_gap,
        )

    def test_contact_adjacent_frames_do_not_calibrate_source_width(
        self,
    ) -> None:
        observations = tuple(
            phase_edge(f"contact-width:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 160.0, 260.0, 360.0, 380.0, 480.0)
            )
        )
        bands = (
            phase_separator(
                "contact-width:separator:1",
                observations[1],
                observations[2],
                FiniteInterval(19.8, 20.2),
            ),
            phase_separator(
                "contact-width:separator:3",
                observations[4],
                observations[5],
                FiniteInterval(19.8, 20.2),
            ),
        )
        contacts = observe_contact_edges(
            observations,
            bands,
            (
                phase_sequence_measurement(
                    "contact-width",
                    FiniteInterval(0.0, 500.0),
                ),
            ),
        )
        phase = fit_template_phase(
            observations,
            phase_template(4),
            separator_bands=bands,
            contact_edge_observations=contacts,
        )
        self.assertEqual(phase.status, PhaseFitStatus.RESOLVED)
        phase = self._with_selected_width_prerequisites(
            phase,
            observations,
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        _calibrated, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(authority.supporting_frame_ordinals, (1, 4))

    def test_observed_inner_frames_close_source_width_before_outer_refinement(
        self,
    ) -> None:
        observations = tuple(
            phase_edge(f"outer-missing:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 160.0, 260.0, 280.0, 380.0)
            )
        )
        phase = fit_template_phase(observations, phase_template(3))
        assert phase.best is not None
        bindings = list(phase.best.role_bindings)
        bindings[0] = None
        bindings[1] = None
        phase = replace(
            phase,
            best=replace(
                phase.best,
                role_bindings=tuple(bindings),
                phase_support_coverage=3.0,
            ),
        )
        phase = self._with_selected_width_prerequisites(
            phase,
            observations,
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )

        _calibrated, authority = calibrate_source_frame_width(
            source,
            phase,
            observations,
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(authority.supporting_frame_ordinals, (2, 3))

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
        rejected = apply_placement_source_frame_width(phase, authority)
        self.assertEqual(rejected.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            rejected.failure_kind,
            PhaseFailureKind.SOURCE_FRAME_WIDTH_CONFLICT,
        )

    def test_source_width_narrows_retained_ambiguous_proposal_without_resolving(
        self,
    ) -> None:
        observations = (
            phase_edge("frame-1-start", 40.0),
            phase_edge("frame-1-end", 139.0),
            phase_edge("frame-2-start", 160.0),
            phase_edge("frame-2-end", 260.0),
            phase_edge("frame-3-start", 280.0),
            phase_edge("frame-3-end", 381.0),
        )
        phase = fit_template_phase(observations, phase_template(3))
        assert phase.best is not None
        bindings = list(phase.best.role_bindings)
        bindings[1] = None
        phase = replace(
            phase,
            best=replace(
                phase.best,
                role_bindings=tuple(bindings),
                phase_support_coverage=3.0,
            ),
        )
        phase = self._with_selected_width_prerequisites(phase, observations)
        assert phase.best is not None
        prior_missing_interval = phase.best.model_full_role_intervals_px[1]
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

        calibrated, authority = calibrate_source_frame_width(
            source,
            ambiguous,
            observations,
        )

        self.assertNotEqual(calibrated.width_state, source.width_state)
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            authority.placement_scope,
            SourceFrameWidthAuthorityPlacementScope
            .RETAINED_AMBIGUOUS_PROPOSAL,
        )
        narrowed = apply_placement_source_frame_width(ambiguous, authority)
        self.assertEqual(narrowed.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(
            narrowed.failure_kind,
            PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
        )
        self.assertEqual(narrowed.runner_up, ambiguous.runner_up)
        assert narrowed.best is not None
        self.assertTrue(authority.matches_placement(narrowed.best))
        inferred = apply_correlated_frame_width_inference(
            narrowed.best,
            source_frame_width_authority=authority,
        )
        assessment = inferred.frame_width_inference
        assert assessment is not None
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertEqual(assessment.inferred_role_indices, (1,))
        assert assessment.width_px is not None
        opposite = inferred.role_bindings[0]
        assert opposite is not None
        inferred_interval = FiniteInterval(
            opposite.full_position_interval_px.minimum
            + assessment.width_px.minimum,
            opposite.full_position_interval_px.maximum
            + assessment.width_px.maximum,
        )
        self.assertLess(inferred_interval.width, prior_missing_interval.width)

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
        selected = apply_placement_source_frame_width(phase, authority)
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
        coverage = (
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
        )
        assert phase.best is not None
        phase = replace(
            phase,
            adjacency_observation_coverage=coverage,
            adjacency_continuity_observations=observe_adjacency_continuity(
                phase.best,
                observations,
                (),
                coverage,
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
            source_frame_width_authority=(
                self._independent_width_authority(fit, authority_ids)
            ),
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
            source_frame_width_authority=(
                self._independent_width_authority(fit, width_ids)
            ),
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
            source_frame_width_authority=self._independent_width_authority(
                fit,
                tuple(
                    ObservationId(f"sequence:{index}")
                    for index in range(4)
                ),
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
            source_frame_width_authority=self._independent_width_authority(
                fit,
                (
                    ObservationId("sequence:0"),
                    ObservationId("sequence:1"),
                    ObservationId("sequence:2"),
                    ObservationId("sequence:4"),
                ),
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
            source_frame_width_authority=self._independent_width_authority(
                fit,
                tuple(
                    ObservationId(f"sequence:{index}")
                    for index in range(4)
                ),
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
            source_frame_width_authority=self._independent_width_authority(
                fit,
                tuple(
                    ObservationId(f"sequence:{index}")
                    for index in range(4)
                ),
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
            source_frame_width_authority=None,
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
