from __future__ import annotations

from dataclasses import replace
import math
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_edge as edge,
    placement_sequence,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    transformed_phase_edge as transformed_edge,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryEvidenceState,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    SeparatorMaterialPolarity,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.template_model import (
    FrameWidthInferenceFailureKind,
    LatticeParameterFitBasis,
    OverlapRelation,
    SeparatorRelationKind,
    SeparatorRelation,
    PhaseLatticeAuthority,
    SequenceBindingUse,
    SequenceRoleBinding,
    SourceFrameWidthAuthorityBasis,
    TemplateSearchReceipt,
    TemplateSpec,
    template_role_refinement_radius_px,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    apply_placement_source_frame_width,
    SourceFrameWidthAuthority,
    SourceFrameWidthAuthorityPlacementScope,
)
from x5crop.detection.photo_geometry.template_overlap import (
    observe_overlap_edge_pairs,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    assess_direct_role_binding_authority,
    intrinsic_direct_role_authority_bases,
)
from x5crop.detection.photo_geometry.template_adjacency_coverage import (
    assess_adjacency_observation_coverage,
)
from x5crop.detection.photo_geometry.template_adjacency_topology import (
    observe_adjacency_continuity,
)
from x5crop.detection.photo_geometry.template_nominal_grid_model import (
    NominalGridFailureKind,
)
from x5crop.detection.photo_geometry.template_phase import (
    _merge_continuous_placement,
    _refine_selected_roles_with_candidate_elimination,
    _same_continuous_placement,
    account_prior_phase_fit,
    finalize_template_phase_candidate,
    fit_template_phase,
    fit_template_phase_candidate_with_adjacency_relations,
    fit_template_phase_with_adjacency_relations,
    refine_template_phase_with_source_frame_width,
    retain_pre_local_phase_proposal,
)
from x5crop.detection.photo_geometry.template_lattice_authority import (
    direct_role_constraint_rank,
)
from x5crop.detection.photo_geometry.template_phase_candidates import (
    _BoundFit,
    _bounded_lattice_least_squares,
    _facts,
    _match_roles,
    _refine_local_role_bindings,
)
from x5crop.detection.photo_geometry.template_phase_candidates import (
    _separator_role_authority,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    GlobalLatticeAuthorityBasis,
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseRetainedProposalBasis,
    PhaseWinnerBasis,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_residual import (
    ResidualPattern,
    derive_adjacency_relations,
)
from x5crop.detection.photo_geometry.template_stability import (
    AnchorDependencyEffect,
    leave_one_anchor_out_phase_stability,
)
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)


def _continuity_for_residual(fit, observations, bands):
    measurement = phase_sequence_measurement(
        "residual",
        FiniteInterval(0.0, 1000.0),
    )
    coverage = assess_adjacency_observation_coverage(
        fit,
        (measurement,),
        directly_observed_ordinals=(),
    )
    overlap_pairs = observe_overlap_edge_pairs(
        tuple(observations),
        tuple(bands),
        (measurement,),
        direction=fit.template.direction,
        maximum_overlap_px=template_role_refinement_radius_px(
            fit.template.pitch_px.maximum
        ),
    )
    return observe_adjacency_continuity(
        fit,
        tuple(observations),
        tuple(bands),
        coverage,
        overlap_pairs,
    )


def _fit_with_independent_source_width(
    phase_input: TemplatePhaseInput,
    observation_ids: tuple[ObservationId, ...],
    supporting_frame_ordinals: tuple[int, ...],
):
    """Run the production placement-bound flow with a typed test W authority."""

    candidate = fit_template_phase_candidate_with_adjacency_relations(
        phase_input
    )
    fit = candidate.result.best
    assert candidate.result.status == PhaseFitStatus.RESOLVED and fit is not None
    authority = SourceFrameWidthAuthority(
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
        basis=SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES,
        supporting_frame_ordinals=supporting_frame_ordinals,
        supporting_constraint_ids=(),
        width_px=FiniteInterval(
            fit.pitch_fit.frame_width_px.minimum,
            fit.pitch_fit.frame_width_px.maximum,
        ),
        canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
        observation_ids=tuple(sorted(observation_ids, key=str)),
        failure_kind=None,
        reason=None,
    )
    selected = apply_placement_source_frame_width(candidate.result, authority)
    selected = refine_template_phase_with_source_frame_width(
        selected,
        authority,
        phase_input.observations,
        phase_input.separator_bands,
        phase_input.sequence_measurement_sets,
    )
    return finalize_template_phase_candidate(
        replace(candidate, result=selected),
        phase_input,
        source_frame_width_authority=authority,
    )


class TemplatePhaseContractTest(unittest.TestCase):
    @staticmethod
    def _phase_candidate_group(
        prefix: str,
        offset_px: float,
        *,
        short: bool = False,
    ) -> tuple[BoundaryEdgeObservation, ...]:
        values = []
        for index, (coordinate, role) in enumerate(
            (
                (40.0, BoundaryRole.START),
                (140.0, BoundaryRole.END),
                (160.0, BoundaryRole.START),
                (260.0, BoundaryRole.END),
            )
        ):
            observation = replace(
                edge(f"{prefix}:{index}", coordinate + offset_px),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            if short:
                observation = replace(
                    observation,
                    trace_coordinates_px=(10, 20),
                    support_fraction=2.0 / 3.0,
                    continuous_support_fraction=2.0 / 3.0,
                )
            values.append(observation)
        return tuple(values)

    @staticmethod
    def _local_line(
        name: str,
        coordinate: float,
        role: BoundaryRole,
    ) -> BoundaryEdgeObservation:
        direction = FiniteInterval.exact(0.0)
        return replace(
            edge(name, coordinate),
            qualified_anchor_roles=(role,),
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=direction,
            full_direction_interval_degrees=direction,
            # Exclude this line from global phase fitting while retaining its
            # typed local line evidence.
            fit_residual_px=20.0,
        )

    def test_unique_local_closure_refines_roles_without_phase_authority(
        self,
    ) -> None:
        anchor = replace(
            self._local_line("anchor:start:1", 100.0, BoundaryRole.START),
            fit_residual_px=0.0,
        )
        end1 = self._local_line("local:end:1", 201.0, BoundaryRole.END)
        start2 = self._local_line("local:start:2", 221.0, BoundaryRole.START)
        end2 = self._local_line("local:end:2", 321.0, BoundaryRole.END)
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(98.0, 102.0),
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=(anchor, end1, start2, end2),
                separator_bands=(
                    separator(
                        "separator:1",
                        end1,
                        start2,
                        FiniteInterval(19.0, 21.0),
                    ),
                ),
                template=spec,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(spec),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(result.best.phase_support_locations, (0,))
        self.assertEqual(
            tuple(binding.use for binding in result.best.role_bindings),
            (
                SequenceBindingUse.PHASE_ANCHOR,
                SequenceBindingUse.LOCAL_REFINEMENT,
                SequenceBindingUse.LOCAL_REFINEMENT,
                SequenceBindingUse.LOCAL_REFINEMENT,
            ),
        )
        self.assertEqual(result.receipt.local_refinement_lookup_count, 16)
        self.assertEqual(result.receipt.local_refinement_binding_count, 3)
        self.assertEqual(result.receipt.inferred_role_count, 0)

    def test_multiple_local_fixed_width_pairs_lack_global_authority(self) -> None:
        anchor = replace(
            self._local_line("anchor:start:1", 100.0, BoundaryRole.START),
            fit_residual_px=0.0,
        )
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(99.0, 101.0),
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=(
                    anchor,
                    self._local_line(
                        "local:start:2:a", 221.0, BoundaryRole.START
                    ),
                    self._local_line(
                        "local:start:2:b", 223.0, BoundaryRole.START
                    ),
                    self._local_line(
                        "local:end:2:a", 321.0, BoundaryRole.END
                    ),
                    self._local_line(
                        "local:end:2:b", 323.0, BoundaryRole.END
                    ),
                ),
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=(
                    unavailable_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE,
        )
        assert result.best is not None
        self.assertEqual(
            result.best.binding_observation_ids,
            (ObservationId("anchor:start:1"), None, None, None),
        )
        self.assertEqual(result.receipt.local_refinement_lookup_count, 20)
        self.assertEqual(result.receipt.local_refinement_binding_count, 0)

    def test_post_grid_local_pair_can_contradict_the_current_fit_width(
        self,
    ) -> None:
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(90.0, 110.0),
        )
        fit = placement_sequence(spec, missing=(0, 1))
        fit = replace(
            fit,
            pitch_fit=replace(
                fit.pitch_fit,
                frame_width_px=PositiveInterval(99.5, 100.5),
            ),
        )
        true_start = self._local_line(
            "local:true:start:1",
            90.0,
            BoundaryRole.START,
        )
        weak_start = self._local_line(
            "local:weak:start:1",
            90.25,
            BoundaryRole.START,
        )
        true_end = self._local_line(
            "local:true:end:1",
            200.0,
            BoundaryRole.END,
        )
        observations = (
            true_start,
            weak_start,
            true_end,
        )
        refined = _refine_local_role_bindings(
            fit,
            observations,
            (),
            intrinsic_coordinate_authority_ids=frozenset(
                {
                    true_start.observation_id,
                    true_end.observation_id,
                }
            ),
        )

        self.assertEqual(
            refined.fit.binding_observation_ids[:2],
            (
                ObservationId("local:true:start:1"),
                ObservationId("local:true:end:1"),
            ),
        )

    def test_intrinsic_coordinate_authority_excludes_a_short_edge(self) -> None:
        source_wide = edge("source-wide", 100.0)
        short = replace(
            edge("short", 101.0),
            trace_coordinates_px=(0, 10),
            support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0,
        )

        bases = intrinsic_direct_role_authority_bases(
            (source_wide, short),
            (
                phase_sequence_measurement(
                    "intrinsic-coordinate-authority",
                    FiniteInterval(0.0, 300.0),
                ),
            ),
        )

        self.assertEqual(
            bases,
            {
                source_wide.observation_id: (
                    DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                )
            },
        )

    def test_post_grid_local_pair_stays_unbound_when_fit_width_is_ambiguous(
        self,
    ) -> None:
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(90.0, 110.0),
        )
        fit = placement_sequence(spec, missing=(0, 1))
        fit = replace(
            fit,
            pitch_fit=replace(
                fit.pitch_fit,
                frame_width_px=PositiveInterval(99.5, 100.5),
            ),
        )
        first_start = self._local_line(
            "local:first:start:1",
            100.0,
            BoundaryRole.START,
        )
        second_start = self._local_line(
            "local:second:start:1",
            100.25,
            BoundaryRole.START,
        )
        true_end = self._local_line(
            "local:end:1",
            200.0,
            BoundaryRole.END,
        )
        observations = (
            first_start,
            second_start,
            true_end,
        )
        refined = _refine_local_role_bindings(
            fit,
            observations,
            (),
            intrinsic_coordinate_authority_ids=frozenset(
                {
                    first_start.observation_id,
                    second_start.observation_id,
                    true_end.observation_id,
                }
            ),
        )

        self.assertEqual(refined.fit.binding_observation_ids[:2], (None, None))

    def test_independent_source_width_closes_one_intrinsic_pair(self) -> None:
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(90.0, 110.0),
        )
        fit = placement_sequence(spec, missing=(0, 1))
        first_start = self._local_line(
            "source-width:first:start:1",
            90.0,
            BoundaryRole.START,
        )
        true_start = self._local_line(
            "source-width:true:start:1",
            100.0,
            BoundaryRole.START,
        )
        end = self._local_line(
            "source-width:end:1",
            200.0,
            BoundaryRole.END,
        )
        observations = (first_start, true_start, end)
        intrinsic_ids = frozenset(
            item.observation_id for item in observations
        )

        physical_only = _refine_local_role_bindings(
            fit,
            observations,
            (),
            intrinsic_coordinate_authority_ids=intrinsic_ids,
        )
        source_closed = _refine_local_role_bindings(
            fit,
            observations,
            (),
            intrinsic_coordinate_authority_ids=intrinsic_ids,
            frame_width_authority_px=FiniteInterval(99.5, 100.5),
        )

        self.assertEqual(
            physical_only.fit.binding_observation_ids[:2],
            (None, None),
        )
        self.assertEqual(
            source_closed.fit.binding_observation_ids[:2],
            (true_start.observation_id, end.observation_id),
        )

    def test_independent_source_width_closes_one_intrinsic_edge(self) -> None:
        fit = placement_sequence(template(2), missing=(0, 1))
        start = self._local_line(
            "source-width:start-only:1",
            100.0,
            BoundaryRole.START,
        )

        physical_only = _refine_local_role_bindings(
            fit,
            (start,),
            (),
            intrinsic_coordinate_authority_ids=frozenset(
                {start.observation_id}
            ),
        )
        source_closed = _refine_local_role_bindings(
            fit,
            (start,),
            (),
            intrinsic_coordinate_authority_ids=frozenset(
                {start.observation_id}
            ),
            frame_width_authority_px=FiniteInterval(99.5, 100.5),
        )

        self.assertEqual(
            physical_only.fit.binding_observation_ids[:2],
            (None, None),
        )
        self.assertEqual(
            source_closed.fit.binding_observation_ids[:2],
            (start.observation_id, None),
        )

    def test_source_width_single_edge_rejects_an_opposite_candidate(self) -> None:
        fit = placement_sequence(template(2), missing=(0, 1, 2))
        start = self._local_line(
            "source-width:intrinsic:start:1",
            100.0,
            BoundaryRole.START,
        )
        conflicting_end = self._local_line(
            "source-width:weak:end:1",
            210.0,
            BoundaryRole.END,
        )
        conflicting_end = replace(
            conflicting_end,
            qualified_anchor_roles=(
                BoundaryRole.END,
                BoundaryRole.START,
            ),
        )

        refined = _refine_local_role_bindings(
            fit,
            (start, conflicting_end),
            (),
            intrinsic_coordinate_authority_ids=frozenset(
                {start.observation_id}
            ),
            frame_width_authority_px=FiniteInterval(99.5, 100.5),
        )

        self.assertEqual(refined.fit.binding_observation_ids[:2], (None, None))

    def test_source_width_single_edge_rejects_multiple_intrinsic_edges(
        self,
    ) -> None:
        fit = placement_sequence(template(2), missing=(0, 1))
        first = self._local_line(
            "source-width:first:start:1",
            99.0,
            BoundaryRole.START,
        )
        second = self._local_line(
            "source-width:second:start:1",
            101.0,
            BoundaryRole.START,
        )

        refined = _refine_local_role_bindings(
            fit,
            (first, second),
            (),
            intrinsic_coordinate_authority_ids=frozenset(
                {first.observation_id, second.observation_id}
            ),
            frame_width_authority_px=FiniteInterval(99.5, 100.5),
        )

        self.assertEqual(refined.fit.binding_observation_ids[:2], (None, None))

    def test_locally_bound_separator_drives_one_wide_advance(self) -> None:
        anchor = replace(
            self._local_line("anchor:start:1", 100.0, BoundaryRole.START),
            fit_residual_px=0.0,
        )
        end1 = self._local_line("local:end:1", 201.0, BoundaryRole.END)
        start2 = self._local_line("local:start:2", 231.0, BoundaryRole.START)
        end2 = self._local_line("local:end:2", 331.0, BoundaryRole.END)
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(98.0, 102.0),
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=(anchor, end1, start2, end2),
                separator_bands=(
                    separator(
                        "separator:wide",
                        end1,
                        start2,
                        FiniteInterval(29.0, 31.0),
                    ),
                ),
                template=spec,
                calibrated_nominal_grid_prior=(
                    unavailable_nominal_grid_prior(spec)
                ),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(result.best.phase_support_locations, (0,))
        self.assertEqual(len(result.best.adjacency_relations), 1)
        relation = result.best.adjacency_relations[0]
        self.assertEqual(relation.kind, SeparatorRelationKind.WIDE)
        self.assertEqual(relation.canonical_delta_px, 10.0)
        self.assertEqual(
            result.best.model_role_positions_px,
            (100.0, 200.0, 230.0, 330.0),
        )
        self.assertEqual(result.receipt.local_refinement_lookup_count, 32)
        self.assertEqual(result.receipt.local_refinement_binding_count, 6)

    def test_local_bend_binds_role_without_recalibrating_global_template(
        self,
    ) -> None:
        def straight(
            observation: BoundaryEdgeObservation,
            role: BoundaryRole,
        ) -> BoundaryEdgeObservation:
            direction = FiniteInterval.exact(0.0)
            return replace(
                observation,
                qualified_anchor_roles=(role,),
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=direction,
                full_direction_interval_degrees=direction,
            )

        observations = (
            straight(edge("straight:start:1", 100.0), BoundaryRole.START),
            straight(edge("straight:end:1", 200.0), BoundaryRole.END),
            straight(edge("straight:start:2", 220.0), BoundaryRole.START),
            straight(edge("straight:end:2", 320.0), BoundaryRole.END),
            straight(edge("straight:start:3", 340.0), BoundaryRole.START),
            replace(
                edge("bend:end:3", 442.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
        )

        result = fit_template_phase(observations, template(3))

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        for actual, expected in zip(
            result.best.model_role_positions_px,
            (100.0, 200.0, 220.0, 320.0, 340.0, 440.0),
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(
            result.best.binding_observation_ids[-1],
            ObservationId("bend:end:3"),
        )

    def test_equal_physical_role_alternatives_are_not_broken_by_identity(self) -> None:
        observations = (
            replace(
                edge("start:a", 99.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("start:z", 101.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("end", 200.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
        )
        template = TemplateSpec(
            template_id="ambiguous-role-binding",
            frame_width_px=FiniteInterval(98.0, 102.0),
            pitch_px=120.0,
            count=1,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=120.0,
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=2,
            ),
            nominal_gap_px=20.0,
        )

        matches = _match_roles(
            _facts(observations),
            template.roles,
            (),
            phase=100.0,
            width=100.0,
            pitch=120.0,
            direction=1,
            prefixes=(0.0,),
            frame_width=template.frame_width_px,
            fit_residual_limit_px=None,
        )

        self.assertEqual(matches, ())

    def test_separator_roles_cannot_form_an_unobserved_mixed_pair(self) -> None:
        observations = (
            replace(
                edge("outer:start", 30.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("band:a:end", 110.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            replace(
                edge("band:b:end", 130.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            replace(
                edge("band:a:start", 150.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("band:b:start", 170.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("outer:end", 250.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
        )
        facts = _facts(observations)
        by_id = {item.observation_id: item for item in facts}
        separator_pairs = (
            (
                by_id[ObservationId("band:a:end")],
                by_id[ObservationId("band:a:start")],
            ),
            (
                by_id[ObservationId("band:b:end")],
                by_id[ObservationId("band:b:start")],
            ),
        )
        compiled = template(2)

        matches = _match_roles(
            facts,
            compiled.roles,
            separator_pairs,
            phase=30.0,
            width=100.0,
            pitch=120.0,
            direction=1,
            prefixes=(0.0, 0.0),
            frame_width=compiled.frame_width_px,
            fit_residual_limit_px=None,
        )

        self.assertEqual(
            tuple((role.role_index, fact.observation_id) for role, fact in matches),
            (
                (0, ObservationId("outer:start")),
                (3, ObservationId("outer:end")),
            ),
        )

    def test_sequence_fit_rejects_invalid_provenance_and_residual(self) -> None:
        result = fit_template_phase(
            tuple(
                edge(f"edge:{index}", coordinate)
                for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
            ),
            template(2),
        )
        assert result.best is not None
        with self.assertRaisesRegex(ValueError, "residual"):
            replace(result.best, residual_sum_px=math.inf)
        duplicate = result.best.binding_observation_ids[0]
        assert duplicate is not None
        bindings = list(result.best.role_bindings)
        assert bindings[1] is not None
        bindings[1] = replace(bindings[1], observation_id=duplicate)
        with self.assertRaisesRegex(
            ValueError,
            "one observation may bind only one proven adjacent contact",
        ):
            replace(result.best, role_bindings=tuple(bindings))

    def test_regular_sequence_uses_direct_phase(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((80.0, 180.0, 200.0, 300.0, 320.0, 420.0))
        )
        result = fit_template_phase(
            observations,
            template(3),
            holder_span_px=FiniteInterval(0.0, 500.0),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsInstance(result.winner_basis, PhaseWinnerBasis)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertAlmostEqual(
            result.best.phase_lattice_fit.canonical_absolute_phase_px,
            80.0,
        )
        self.assertEqual(result.best.phase_support_count, 4)
        self.assertEqual(result.best.phase_support_locations, (0, 1, 2, 3))
        self.assertEqual(result.best.unbound_role_indices, ())

    def test_phase_is_derived_from_direct_observations(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((35.0, 135.0, 155.0, 255.0, 275.0, 375.0))
        )
        result = fit_template_phase(observations, template(3))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertAlmostEqual(
            result.best.phase_lattice_fit.canonical_absolute_phase_px,
            35.0,
        )

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
            *self._phase_candidate_group("supported", 0.0),
            *self._phase_candidate_group("short", 5.0, short=True),
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
        supported = self._phase_candidate_group("supported", 0.0)
        contradicted = self._phase_candidate_group("contradicted", 5.0)
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
        supported = self._phase_candidate_group("supported", 0.0)
        alternative_group = self._phase_candidate_group("alternative", 5.0)
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
        observations = self._phase_candidate_group("source-width", 0.0)
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
                *self._phase_candidate_group("first", 0.0),
                *self._phase_candidate_group("second", 5.0),
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
                *self._phase_candidate_group("first-short", 0.0, short=True),
                *self._phase_candidate_group("second-short", 5.0, short=True),
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

    def test_local_short_edge_yields_to_correlated_source_width(self) -> None:
        observations = tuple(
            replace(
                self._local_line(identity, coordinate, role),
                fit_residual_px=(
                    20.0 if identity == "local:start:3" else 0.0
                ),
                polarity=(1 if role == BoundaryRole.START else -1),
            )
            for identity, coordinate, role in (
                ("start:1", 100.0, BoundaryRole.START),
                ("end:1", 200.0, BoundaryRole.END),
                ("start:2", 220.0, BoundaryRole.START),
                ("end:2", 320.0, BoundaryRole.END),
                ("local:start:3", 340.0, BoundaryRole.START),
                ("end:3", 440.0, BoundaryRole.END),
                ("start:4", 460.0, BoundaryRole.START),
                ("end:4", 560.0, BoundaryRole.END),
            )
        )
        local = observations[4]
        observations = (
            *observations[:4],
            replace(
                local,
                trace_coordinates_px=(10, 20),
                support_fraction=0.34,
                continuous_support_fraction=0.34,
            ),
            *observations[5:],
        )
        width_ids = tuple(
            ObservationId(identity)
            for identity in ("start:1", "end:1", "start:2", "end:2")
        )

        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=template(4),
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(
                template(4)
            ),
            scale_px_per_mm=PositiveInterval.exact(100.0),
            holder_span_px=FiniteInterval(0.0, 600.0),
            phase_authority_px=FiniteInterval.exact(100.0),
            sequence_measurement_sets=(
                phase_sequence_measurement(
                    "local-short-to-source-width",
                    FiniteInterval(0.0, 600.0),
                ),
            ),
            global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                pitch_observation_ids=(ObservationId("end:3"),),
            ),
        )
        result = _fit_with_independent_source_width(
            phase_input,
            width_ids,
            (1, 2),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertIsNone(result.best.role_bindings[4])
        inference = result.best.frame_width_inference
        assert inference is not None
        self.assertEqual(result.receipt.inferred_role_count, 1)
        self.assertEqual(inference.validation_only_role_indices, (4,))
        self.assertEqual(
            inference.validation_observation_ids,
            (ObservationId("local:start:3"),),
        )
        authority = result.direct_role_binding_authority
        assert authority is not None
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertNotIn(4, tuple(item.role_index for item in authority.facts))

    def test_fixed_width_pair_cannot_self_authorize_two_short_edges(self) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=(
                    (10, 20)
                    if identity.startswith("short:")
                    else (0, 10, 20)
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
                ("short:end:3", 380.0, BoundaryRole.END),
                ("start:4", 400.0, BoundaryRole.START),
                ("end:4", 500.0, BoundaryRole.END),
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(4)),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 540.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "short-fixed-width-direct-role",
                        FiniteInterval(0.0, 540.0),
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
            (4, 5),
        )
        short_pair = tuple(
            item
            for item in result.direct_role_binding_authority.facts
            if item.role_index in {4, 5}
        )
        self.assertEqual(len(short_pair), 2)
        self.assertTrue(
            all(not item.bases for item in short_pair)
        )

    def test_two_region_separator_transfers_one_direct_role_authority(
        self,
    ) -> None:
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
                ("end:3", 380.0, BoundaryRole.END),
                ("start:4", 400.0, BoundaryRole.START),
                ("end:4", 500.0, BoundaryRole.END),
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(
                    separator(
                        "two-region:end-2:start-3",
                        observations[3],
                        observations[4],
                        FiniteInterval(19.8, 20.2),
                        region_count=2,
                    ),
                ),
                template=template(4),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(4)),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 540.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "two-region-transfer",
                        FiniteInterval(0.0, 540.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        authority = result.direct_role_binding_authority
        assert authority is not None
        self.assertEqual(
            authority.aperture_domain_required_role_indices,
            (4,),
        )
        transferred = next(
            item for item in authority.facts if item.role_index == 4
        )
        self.assertEqual(
            tuple(item.value for item in transferred.bases),
            ("partial_height_separator_pair",),
        )

    def test_two_region_separator_cannot_self_authorize_two_short_edges(
        self,
    ) -> None:
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
                ("short:end:2", 260.0, BoundaryRole.END),
                ("short:start:3", 280.0, BoundaryRole.START),
                ("end:3", 380.0, BoundaryRole.END),
                ("start:4", 400.0, BoundaryRole.START),
                ("end:4", 500.0, BoundaryRole.END),
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(
                    separator(
                        "two-region:two-short",
                        observations[3],
                        observations[4],
                        FiniteInterval(19.8, 20.2),
                        region_count=2,
                    ),
                ),
                template=template(4),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(4)),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 540.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "two-region-no-self-authority",
                        FiniteInterval(0.0, 540.0),
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
        assert projection is not None
        self.assertEqual(
            projection.outcome,
            PhaseCandidateProjectionOutcome.PROJECTED,
        )
        self.assertEqual(
            tuple(item.role_index for item in projection.projected_out_bindings),
            (3, 4),
        )
        authority = result.direct_role_binding_authority
        assert authority is not None
        self.assertEqual(authority.unsupported_role_indices, ())
        self.assertFalse(authority.aperture_domain_required_role_indices)

    def test_cross_height_union_authorizes_one_short_direct_edge(self) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=(
                    (10, 20) if identity.startswith("joint:") else (0, 10, 20)
                ),
                support_fraction=(
                    2.0 / 3.0 if identity.startswith("joint:") else 1.0
                ),
                continuous_support_fraction=(
                    2.0 / 3.0 if identity.startswith("joint:") else 1.0
                ),
                measurement_basis=(
                    BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE
                    if identity.startswith("joint:")
                    else BoundaryEdgeMeasurementBasis.DIRECT_TRACE
                ),
                aggregate_support_id=(
                    ObservationId("cross-height:joint:start:3")
                    if identity.startswith("joint:")
                    else None
                ),
            )
            for identity, coordinate, role in (
                ("start:1", 40.0, BoundaryRole.START),
                ("end:1", 140.0, BoundaryRole.END),
                ("start:2", 160.0, BoundaryRole.START),
                ("end:2", 260.0, BoundaryRole.END),
                ("joint:start:3", 280.0, BoundaryRole.START),
                ("start:4", 400.0, BoundaryRole.START),
                ("end:4", 500.0, BoundaryRole.END),
            )
        )

        phase_input = TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(4)),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 540.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "cross-height-union-direct-role",
                        FiniteInterval(0.0, 540.0),
                    ),
                ),
            )
        result = _fit_with_independent_source_width(
            phase_input,
            tuple(
                ObservationId(identity)
                for identity in (
                    "start:1",
                    "end:1",
                    "start:2",
                    "end:2",
                )
            ),
            (1, 2),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.direct_role_binding_authority is not None
        joint = tuple(
            item
            for item in result.direct_role_binding_authority.facts
            if item.role_index == 4
        )
        self.assertEqual(len(joint), 1)
        self.assertEqual(
            tuple(item.value for item in joint[0].bases),
            ("aggregate_union",),
        )

    def test_inferred_normal_adjacency_requires_full_registered_corridor(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for identity, coordinate, role in (
                ("start:1", 40.0, BoundaryRole.START),
                ("end:1", 140.0, BoundaryRole.END),
                ("start:3", 280.0, BoundaryRole.START),
            )
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
                        "partial-corridor",
                        FiniteInterval(0.0, 200.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE,
        )
        assert result.global_lattice_authority is not None
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 3)
        incomplete = tuple(
            item
            for item in result.adjacency_observation_coverage
            if item.state.value == "incomplete"
        )
        self.assertTrue(incomplete)
        self.assertTrue(
            any(
                trace.covered_coordinate_count
                < trace.required_coordinate_count
                for item in incomplete
                for trace in item.trace_coverage
            )
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
                full_position_interval_px=(
                    FiniteInterval(coordinate - 0.2, coordinate + 0.2)
                    if source_wide
                    else FiniteInterval(coordinate - 1.2, coordinate + 1.2)
                ),
            )

        anchor = local(
            "late-projection:anchor:start:1",
            100.0,
            BoundaryRole.START,
            source_wide=True,
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
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
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

    def test_rank_three_fit_uses_nearest_joint_physical_solution(self) -> None:
        matrix = np.asarray(
            [
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
                (1.0, 0.0, 2.0),
                (1.0, 1.0, 2.0),
            ],
            dtype=np.float64,
        )
        values = np.asarray(
            (10.0, 108.0, 131.0, 229.0, 252.0, 350.0),
            dtype=np.float64,
        )

        phase, width, pitch, basis = _bounded_lattice_least_squares(
            matrix,
            values,
            width_authority=PositiveInterval(95.0, 105.0),
            pitch_authority=FiniteInterval(115.0, 125.0),
            gap_authority=FiniteInterval(18.0, 22.0),
            phase_authority=None,
        )

        self.assertAlmostEqual(pitch - width, 22.0)
        self.assertEqual(
            basis,
            LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES,
        )
        self.assertNotEqual((width, pitch), (100.0, 120.0))
        bounded_residual = np.sum(
            (matrix @ np.asarray((phase, width, pitch)) - values) ** 2
        )
        nominal_phase = float(
            np.mean(values - matrix @ np.asarray((0.0, 100.0, 120.0)))
        )
        nominal_residual = np.sum(
            (
                matrix @ np.asarray((nominal_phase, 100.0, 120.0))
                - values
            )
            ** 2
        )
        self.assertLess(bounded_residual, nominal_residual)

    def test_rank_three_fit_never_widens_compiled_authorities(self) -> None:
        matrix = np.asarray(
            [
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 2.0),
            ],
            dtype=np.float64,
        )
        values = np.asarray((0.0, 70.0, 150.0, 390.0), dtype=np.float64)

        phase, width, pitch, basis = _bounded_lattice_least_squares(
            matrix,
            values,
            width_authority=PositiveInterval(95.0, 105.0),
            pitch_authority=FiniteInterval(115.0, 125.0),
            gap_authority=FiniteInterval(18.0, 22.0),
            phase_authority=FiniteInterval(-2.0, 2.0),
        )

        self.assertTrue(FiniteInterval(-2.0, 2.0).contains(phase))
        self.assertTrue(FiniteInterval(95.0, 105.0).contains(width))
        self.assertTrue(FiniteInterval(115.0, 125.0).contains(pitch))
        self.assertTrue(FiniteInterval(18.0, 22.0).contains(pitch - width))
        self.assertEqual(
            basis,
            LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES,
        )

    def test_parameter_basis_follows_only_the_same_discrete_lineage(self) -> None:
        coordinates = (10.0, 110.0, 130.0, 230.0)
        observations = tuple(
            edge(f"lineage:{index}", coordinate)
            for index, coordinate in enumerate(coordinates)
        )
        current = fit_template_phase(observations, template(2))
        assert current.best is not None
        prior = replace(
            current,
            best=replace(
                current.best,
                lattice_parameter_fit_basis=(
                    LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES
                ),
            ),
        )

        inherited = account_prior_phase_fit(current, prior)

        assert inherited.best is not None
        self.assertEqual(
            inherited.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES,
        )
        unrelated = fit_template_phase(
            tuple(
                edge(f"other:{index}", coordinate)
                for index, coordinate in enumerate(coordinates)
            ),
            template(2),
        )
        retained = account_prior_phase_fit(unrelated, prior)
        assert retained.best is not None
        self.assertEqual(
            retained.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.DIRECT_LEAST_SQUARES,
        )

    def test_prior_direct_pass_cannot_relabel_a_calibrated_grid_solve(
        self,
    ) -> None:
        spec = template(4)
        observations = tuple(
            replace(
                edge(f"nominal-lineage:{slot}", 40.0 + 120.0 * slot),
                qualified_anchor_roles=(BoundaryRole.START,),
            )
            for slot in range(4)
        )
        nominal = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=spec,
                calibrated_nominal_grid_prior=calibrated_nominal_grid_prior(
                    spec
                ),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 520.0),
                phase_authority_px=FiniteInterval.exact(40.0),
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "nominal-lineage-complete",
                        FiniteInterval(0.0, 520.0),
                    ),
                ),
            )
        )
        direct_prior = fit_template_phase(
            observations,
            spec,
            phase_authority_px=FiniteInterval.exact(40.0),
        )

        retained = account_prior_phase_fit(nominal, direct_prior)

        assert retained.best is not None
        self.assertEqual(
            retained.best.lattice_parameter_fit_basis,
            LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
        )
        self.assertIsNotNone(
            retained.best.calibrated_nominal_grid_fit_state
        )
        self.assertIsNotNone(retained.calibrated_nominal_grid_evidence)

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
        )
        not_retained = retain_pre_local_phase_proposal(
            bounded,
            prior=nominal,
        )
        self.assertIsNone(not_retained.best)
        self.assertIsNone(not_retained.retained_proposal_basis)

    def test_residual_counterevidence_retains_bounded_phase_proposal(
        self,
    ) -> None:
        spec = template(1)
        observations = (edge("residual-proposal-anchor", 40.0),)
        baseline = fit_template_phase(observations, spec)
        assert baseline.best is not None

        with patch(
            "x5crop.detection.photo_geometry.template_phase._fit_seed",
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

    def test_fixed_width_pair_rejects_nearer_interior_end_edge(self) -> None:
        observations = (
            replace(
                edge("outer-start", 10.0),
                qualified_anchor_roles=(BoundaryRole.START,),
                polarity=1,
            ),
            replace(
                edge("interior-end", 105.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            ),
            replace(
                edge("outer-end", 110.0),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=1,
            ),
        )
        result = fit_template_phase(
            observations,
            template(1),
            holder_span_px=FiniteInterval(0.0, 110.0),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.binding_observation_ids,
            (ObservationId("outer-start"), ObservationId("outer-end")),
        )

    def test_local_refine_rejects_a_high_residual_nearer_edge(self) -> None:
        compiled = TemplateSpec(
            template_id="bounded-local-refine",
            frame_width_px=FiniteInterval(96.0, 104.0),
            pitch_px=FiniteInterval(116.0, 124.0),
            count=1,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=FiniteInterval(116.0, 124.0),
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
            nominal_gap_px=FiniteInterval(16.0, 24.0),
        )
        start = replace(
            edge("local:start", 10.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        false_end = replace(
            edge("local:false-end", 110.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
            fit_residual_px=20.0,
        )
        true_end = replace(
            edge("local:true-end", 113.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
            fit_residual_px=1.0,
        )
        result = fit_template_phase(
            (start, false_end, true_end),
            compiled,
            scale_px_per_mm=100.0,
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.binding_observation_ids,
            (start.observation_id, true_end.observation_id),
        )

    def test_one_role_residual_does_not_expand_every_direct_role(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 160.0, 260.0, 280.0, 385.0)
            )
        )
        result = fit_template_phase(observations, template(3))
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        assert result.best is not None
        first = result.best.model_role_intervals_px[0]
        last = result.best.model_role_intervals_px[-1]
        self.assertLess(first.width, 6.0)
        self.assertLess(last.width, 6.0)

    def test_missing_separator_is_inferred_only_after_direct_phase(self) -> None:
        # Slot 2 is directly anchored; slot 1 has no observed separator and
        # is filled by the fixed pitch rule.
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 280.0, 380.0))
        )
        result = fit_template_phase(observations, template(3))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertEqual(result.best.unbound_role_indices, (2, 3))

        unresolved = fit_template_phase((), template(3))
        self.assertEqual(unresolved.status, PhaseFitStatus.UNRESOLVED)
        self.assertIn("direct", unresolved.ambiguity_reason or "")

    def test_internal_separator_and_holder_containment_establish_phase(self) -> None:
        left = replace(
            edge("internal-band:end", 260.0, support_fraction=0.2),
            qualified_anchor_roles=(),
            polarity=-1,
        )
        right = replace(
            edge("internal-band:start", 280.0, support_fraction=0.2),
            qualified_anchor_roles=(),
            polarity=1,
        )
        band = separator(
            "internal-band",
            left,
            right,
            FiniteInterval(19.0, 21.0),
        )
        result = fit_template_phase(
            (left, right),
            template(3),
            separator_bands=(band,),
            holder_span_px=FiniteInterval(0.0, 400.0),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertAlmostEqual(
            result.best.phase_lattice_fit.canonical_absolute_phase_px,
            40.0,
        )
        self.assertEqual(
            result.best.binding_observation_ids,
            (
                None,
                None,
                None,
                left.observation_id,
                right.observation_id,
                None,
            ),
        )
        self.assertEqual(len(result.best.bound_observation_ids), 2)
        self.assertEqual(result.best.phase_support_count, 1)
        self.assertEqual(
            result.best.evidence_group_ids,
            (band.observation_id,),
        )
        self.assertAlmostEqual(result.best.phase_support_coverage, 0.2)

    def test_source_wide_light_separator_establishes_the_same_phase_roles(
        self,
    ) -> None:
        left = replace(
            edge("light-band:end", 260.0, support_fraction=0.2),
            qualified_anchor_roles=(),
            polarity=1,
        )
        right = replace(
            edge("light-band:start", 280.0, support_fraction=0.2),
            qualified_anchor_roles=(),
            polarity=-1,
        )
        band = separator(
            "light-band",
            left,
            right,
            FiniteInterval(19.0, 21.0),
            material_polarity=SeparatorMaterialPolarity.LIGHT,
        )

        result = fit_template_phase(
            (left, right),
            template(3),
            separator_bands=(band,),
            holder_span_px=FiniteInterval(0.0, 400.0),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertAlmostEqual(
            result.best.phase_lattice_fit.canonical_absolute_phase_px,
            40.0,
        )
        self.assertEqual(
            result.best.binding_observation_ids,
            (None, None, None, left.observation_id, right.observation_id, None),
        )

    def test_source_wide_light_photo_region_cannot_create_separator_phase(
        self,
    ) -> None:
        left = replace(
            edge("bright-photo-region:left", 260.0, support_fraction=0.2),
            qualified_anchor_roles=(),
            polarity=1,
        )
        right = replace(
            edge("bright-photo-region:right", 320.0, support_fraction=0.2),
            qualified_anchor_roles=(),
            polarity=-1,
        )
        band = separator(
            "bright-photo-region",
            left,
            right,
            FiniteInterval(59.0, 61.0),
            material_polarity=SeparatorMaterialPolarity.LIGHT,
        )

        result = fit_template_phase(
            (left, right),
            template(3),
            separator_bands=(band,),
            holder_span_px=FiniteInterval(0.0, 400.0),
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE,
        )

    def test_source_wide_material_conflict_blocks_selected_direct_roles(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for identity, coordinate, role in (
                ("start:1", 40.0, BoundaryRole.START),
                ("end:1", 140.0, BoundaryRole.END),
                ("start:2", 160.0, BoundaryRole.START),
                ("end:2", 260.0, BoundaryRole.END),
                ("start:3", 280.0, BoundaryRole.START),
                ("end:3", 380.0, BoundaryRole.END),
                ("alternate:end:3", 390.0, BoundaryRole.END),
                ("start:4", 400.0, BoundaryRole.START),
                ("end:4", 500.0, BoundaryRole.END),
            )
        )
        by_id = {item.observation_id: item for item in observations}
        supported = SeparatorMaterialRegionObservation(
            region_index=0,
            sample_count=2,
            material_contrast_interval=FiniteInterval(3.0, 4.0),
            core_texture_interval=FiniteInterval(0.0, 1.0),
            state=SeparatorMaterialRegionState.SUPPORTED,
        )
        conflict = replace(
            separator(
                "material-conflict",
                by_id[ObservationId("end:3")],
                by_id[ObservationId("alternate:end:3")],
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

        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(conflict,),
                template=template(4),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(4)),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 540.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "material-conflict",
                        FiniteInterval(0.0, 540.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT,
        )
        authority = result.direct_role_binding_authority
        assert authority is not None
        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        self.assertEqual(authority.unsupported_role_indices, (5,))
        conflicted = tuple(
            item
            for item in authority.facts
            if item.state == EvidenceState.CONTRADICTED
        )
        self.assertEqual(
            tuple(item.role_index for item in conflicted),
            (5,),
        )
        self.assertTrue(
            all(
                item.blocking_material_conflict_ids
                == (conflict.observation_id,)
                for item in conflicted
            )
        )

    def test_internal_edges_preserve_discrete_ordinal_mappings(self) -> None:
        observations = tuple(
            replace(
                edge(f"internal-end:{index}", coordinate),
                qualified_anchor_roles=(BoundaryRole.END,),
                polarity=-1,
            )
            for index, coordinate in enumerate((260.0, 380.0, 500.0))
        )

        result = fit_template_phase(
            observations,
            template(4),
            holder_span_px=FiniteInterval(0.0, 620.0),
        )

        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None and result.runner_up is not None
        self.assertEqual(
            {
                round(result.best.phase_lattice_fit.canonical_absolute_phase_px),
                round(result.runner_up.phase_lattice_fit.canonical_absolute_phase_px),
            },
            {40, 160},
        )
        self.assertEqual(
            {
                result.best.phase_lattice_fit.integer_slot_offset,
                result.runner_up.phase_lattice_fit.integer_slot_offset,
            },
            {0, 1},
        )

    def test_inferred_role_propagates_pitch_authority_by_slot(self) -> None:
        compiled = TemplateSpec(
            template_id="interval-propagation",
            frame_width_px=FiniteInterval(98.0, 102.0),
            pitch_px=FiniteInterval(118.0, 122.0),
            count=4,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=FiniteInterval(118.0, 122.0),
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
            nominal_gap_px=FiniteInterval(18.0, 22.0),
        )
        result = fit_template_phase(
            (edge("first-start", 40.0), edge("first-end", 140.0)),
            compiled,
            holder_span_px=FiniteInterval(0.0, 500.0),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        first_missing_start = result.best.model_role_intervals_px[2]
        last_missing_start = result.best.model_role_intervals_px[6]
        self.assertAlmostEqual(
            last_missing_start.width - first_missing_start.width,
            8.0,
        )
        # A direct observation keeps its own local interval and is not widened
        # by pitch authority belonging to later inferred roles.
        self.assertLess(result.best.model_role_intervals_px[0].width, 2.0)

    def test_far_separated_roles_narrow_pitch_without_gap_count_block(
        self,
    ) -> None:
        compiled = TemplateSpec(
            template_id="far-span-pitch",
            frame_width_px=FiniteInterval(90.0, 110.0),
            pitch_px=FiniteInterval(108.0, 132.0),
            count=6,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=FiniteInterval(108.0, 132.0),
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
            nominal_gap_px=FiniteInterval(18.0, 22.0),
        )
        anchors = tuple(
            edge(f"far-span:{role_index}", coordinate)
            for role_index, coordinate in (
                (2, 160.0),
                (3, 260.0),
                (10, 640.0),
                (11, 740.0),
            )
        )
        result = fit_template_phase(
            anchors,
            compiled,
            holder_span_px=FiniteInterval(0.0, 800.0),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.binding_observation_ids,
            (
                None,
                None,
                ObservationId("far-span:2"),
                ObservationId("far-span:3"),
                None,
                None,
                None,
                None,
                None,
                None,
                ObservationId("far-span:10"),
                ObservationId("far-span:11"),
            ),
        )
        self.assertEqual(result.best.phase_lattice_fit.integer_slot_offset, 0)
        self.assertAlmostEqual(
            result.best.phase_lattice_fit.canonical_absolute_phase_px,
            40.0,
        )
        pitch_interval = result.best.pitch_fit.pitch_interval_px
        self.assertLess(
            pitch_interval.maximum - pitch_interval.minimum,
            0.3,
        )
        self.assertLess(result.best.model_role_intervals_px[8].width, 3.0)

    def test_adjacency_interval_is_applied_once_to_the_suffix(self) -> None:
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval(18.0, 22.0),
            canonical_delta_px=20.0,
            separator_band_observation_id=ObservationId("gap:interval"),
            end_edge_observation_id=ObservationId("end:1"),
            next_start_edge_observation_id=ObservationId("start:2"),
            signed_gap_interval_px=FiniteInterval(38.0, 42.0),
            canonical_signed_gap_px=40.0,
        )
        result = fit_template_phase(
            (
                edge("start:1", 10.0),
                edge("end:1", 110.0),
                edge("start:2", 150.0),
            ),
            template(3),
            adjacency_relations=(relation,),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        slot_two_start = result.best.model_role_intervals_px[4]
        self.assertLessEqual(slot_two_start.minimum, 268.0)
        self.assertGreaterEqual(slot_two_start.maximum, 272.0)
        self.assertLess(slot_two_start.maximum, 285.0)

    def test_leave_one_anchor_out_is_bounded_and_reports_dependency(self) -> None:
        observations = tuple(
            edge(f"stable:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
        )
        compiled = template(2)
        result = fit_template_phase(observations, compiled)
        assert result.best is not None
        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "bounded-stability",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            ),
        )
        self.assertEqual(
            analysis.receipt.refit_count,
            len(analysis.dependencies),
        )

    def test_stability_removes_both_sides_of_one_separator_atom(self) -> None:
        start = edge("start", 40.0)
        left = replace(edge("separator-left", 140.0), polarity=-1)
        right = replace(edge("separator-right", 160.0), polarity=1)
        end = replace(edge("end", 260.0), polarity=-1)
        band = separator("separator-band", left, right, FiniteInterval(19.0, 21.0))
        observations = (start, left, right, end)
        compiled = template(2)
        result = fit_template_phase(
            observations,
            compiled,
            separator_bands=(band,),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)

        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(band,),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "separator-stability",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
                global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                    pitch_observation_ids=(band.observation_id,),
                ),
            ),
        )

        separator_dependency = next(
            item
            for item in analysis.dependencies
            if set(item.observation_ids)
            == {left.observation_id, right.observation_id}
        )
        self.assertEqual(
            separator_dependency.support_atom_id,
            band.observation_id,
        )
        self.assertLessEqual(analysis.receipt.refit_count, 4)
        self.assertTrue(
            all(
                item.effect in tuple(AnchorDependencyEffect)
                for item in analysis.dependencies
            )
        )

    def test_stability_never_reuses_selected_source_width(self) -> None:
        observations = tuple(
            edge(f"selected-width:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
        )
        compiled = template(2)
        result = fit_template_phase(observations, compiled)
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(),
            template=compiled,
            calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
            scale_px_per_mm=None,
            holder_span_px=None,
            phase_authority_px=None,
            global_lattice_evidence=GlobalLatticeAuthorityEvidence(
                frame_width_observation_ids=tuple(
                    item.observation_id for item in observations
                ),
            ),
        )
        refit_inputs = []

        def capture_refit(candidate_input):
            refit_inputs.append(candidate_input)
            return replace(
                result,
                best=None,
                runner_up=None,
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason="test refit remains unresolved",
                failure_kind=PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE,
                winner_basis=None,
            )

        with patch(
            "x5crop.detection.photo_geometry.template_stability."
            "fit_template_phase_with_adjacency_relations",
            side_effect=capture_refit,
        ):
            leave_one_anchor_out_phase_stability(result, phase_input)

        self.assertTrue(refit_inputs)
        self.assertTrue(
            all(
                not item.global_lattice_evidence.frame_width_observation_ids
                for item in refit_inputs
            )
        )

    def test_leave_one_anchor_out_reports_discrete_slot_jump(self) -> None:
        observations = (edge("jump:start", 40.0), edge("jump:end", 140.0))
        compiled = template(1)
        result = fit_template_phase(observations, compiled)

        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
            ),
        )

        self.assertEqual(
            tuple(item.effect for item in analysis.dependencies),
            (
                AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR,
                AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR,
            ),
        )

    def test_leave_one_anchor_out_reports_lost_unknown_closure(self) -> None:
        coordinates = (
            36.149664229248124,
            135.74929537674714,
            167.9303173681674,
            259.52421612035914,
        )
        observations = tuple(
            edge(f"continuous:{index}", coordinate)
            for index, coordinate in enumerate(coordinates)
        )
        compiled = template(2)
        result = fit_template_phase(observations, compiled)

        analysis = leave_one_anchor_out_phase_stability(
            result,
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=compiled,
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(compiled),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "continuous-stability",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            ),
        )

        self.assertTrue(
            all(
                item.effect
                == AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR
                for item in analysis.dependencies
            )
        )

    def test_only_anchor_is_not_a_resolved_phase(self) -> None:
        observations = (edge("only-anchor", 40.0),)
        compiled = template(1)
        result = fit_template_phase(observations, compiled)
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
        )

    def test_close_runner_up_is_ambiguous(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 200.0, 300.0))
        )
        result = fit_template_phase(observations, template(2))
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertIsNone(result.winner_basis)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_role_free_coarse_support_cannot_select_phase(self) -> None:
        import inspect

        self.assertNotIn(
            "coarse_outer_interval_px",
            inspect.signature(fit_template_phase).parameters,
        )
        self.assertNotIn(
            "coarse_outer_interval_px",
            TemplatePhaseInput.__dataclass_fields__,
        )

    def test_distinct_close_runner_remains_ambiguous(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 40.5, 140.5, 160.0, 260.0)
            )
        )
        result = fit_template_phase(observations, template(2))
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        self.assertIsNone(result.winner_basis)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None and result.runner_up is not None
        self.assertLessEqual(
            max(
                abs(left - right)
                for left, right in zip(
                    result.best.model_role_positions_px,
                    result.runner_up.model_role_positions_px,
                    strict=True,
                )
            ),
            0.51,
        )

    def test_one_evidence_group_does_not_merge_distinct_coordinates(self) -> None:
        observations = tuple(
            edge(f"connected:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 110.0, 130.0, 230.0))
        )
        fit = fit_template_phase(observations, template(2)).best
        assert fit is not None
        positions = list(fit.model_role_positions_px)
        positions[2] += 2.0
        positions[3] += 2.0
        role_intervals = list(fit.model_role_intervals_px)
        full_intervals = list(fit.model_full_role_intervals_px)
        for index in (2, 3):
            role_intervals[index] = FiniteInterval.exact(positions[index])
            full_intervals[index] = FiniteInterval.exact(positions[index])
        alternative_ids = (
            ObservationId("connected:alternate:start"),
            ObservationId("connected:alternate:end"),
        )
        bindings = list(fit.role_bindings)
        original_bindings = (bindings[2], bindings[3])
        assert all(binding is not None for binding in original_bindings)
        bindings[2:4] = tuple(
            replace(binding, observation_id=identity)
            for binding, identity in zip(
                original_bindings,
                alternative_ids,
                strict=True,
            )
            if binding is not None
        )
        alternative = replace(
            fit,
            model_role_positions_px=tuple(positions),
            model_role_intervals_px=tuple(role_intervals),
            model_full_role_intervals_px=tuple(full_intervals),
            role_bindings=tuple(bindings),
        )
        self.assertTrue(
            all(
                left is not None
                and right is not None
                and left.observation_id != right.observation_id
                and left.evidence_group_id == right.evidence_group_id
                for left, right in zip(
                    fit.role_bindings[2:4],
                    alternative.role_bindings[2:4],
                    strict=True,
                )
            )
        )
        self.assertFalse(_same_continuous_placement(fit, alternative))

    def test_complementary_endpoint_facts_merge_into_one_continuous_fit(
        self,
    ) -> None:
        observations = tuple(
            edge(f"complementary:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 110.0, 130.0, 230.0))
        )
        fit = fit_template_phase(observations, template(2)).best
        assert fit is not None
        direct_count = (
            fit.contradicted_observation_count + len(fit.bound_observation_ids)
        )
        left_bindings = list(fit.role_bindings)
        right_bindings = list(fit.role_bindings)
        left_bindings[0] = None
        right_bindings[-1] = None
        left = replace(
            fit,
            role_bindings=tuple(left_bindings),
            contradicted_observation_count=(
                direct_count
                - sum(binding is not None for binding in left_bindings)
            ),
            phase_support_coverage=min(
                fit.phase_support_coverage,
                len(
                    {
                        (index + 1) // 2
                        for index, binding in enumerate(left_bindings)
                        if binding is not None
                    }
                ),
            ),
        )
        right = replace(
            fit,
            role_bindings=tuple(right_bindings),
            contradicted_observation_count=(
                direct_count
                - sum(binding is not None for binding in right_bindings)
            ),
            phase_support_coverage=min(
                fit.phase_support_coverage,
                len(
                    {
                        (index + 1) // 2
                        for index, binding in enumerate(right_bindings)
                        if binding is not None
                    }
                ),
            ),
        )

        self.assertNotEqual(
            left.evidence_group_ids,
            right.evidence_group_ids,
        )
        self.assertTrue(_same_continuous_placement(left, right))
        merged = _merge_continuous_placement(
            _BoundFit(left, True),
            _BoundFit(right, True),
        ).fit
        self.assertEqual(merged.role_bindings, fit.role_bindings)
        self.assertEqual(
            merged.pitch_fit.observation_ids,
            fit.bound_observation_ids,
        )
        self.assertEqual(
            merged.contradicted_observation_count,
            fit.contradicted_observation_count,
        )

    def test_direct_separator_identity_transmits_prefix_once(
        self,
    ) -> None:
        relation = SeparatorRelation(
            relation_ordinal=1,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval.exact(20.0),
            canonical_delta_px=20.0,
            separator_band_observation_id=ObservationId("gap:1"),
            end_edge_observation_id=ObservationId("edge:1"),
            next_start_edge_observation_id=ObservationId("edge:2"),
            signed_gap_interval_px=FiniteInterval.exact(40.0),
            canonical_signed_gap_px=40.0,
        )
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 90.0, 130.0, 230.0, 250.0, 350.0))
        )
        result = fit_template_phase(
            observations,
            template(3),
            adjacency_relations=(relation,),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(result.winner_basis, PhaseWinnerBasis.ONLY_PHYSICAL_FIT)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        phase = result.best.phase_lattice_fit.canonical_absolute_phase_px
        pitch = result.best.pitch_fit.canonical_pitch_px
        self.assertAlmostEqual(
            result.best.model_role_intervals_px[4].center,
            phase + 2.0 * pitch + 20.0,
        )
        self.assertAlmostEqual(
            result.best.model_role_intervals_px[5].center,
            phase + 2.0 * pitch + 120.0,
        )

    def test_direct_separator_authorizes_one_bounded_local_refit(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 253.0, 353.0)
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(
                separator(
                    "separator:wide",
                    observations[3],
                    observations[4],
                    FiniteInterval(22.8, 23.2),
                ),
                ),
                template=template(3),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(3)),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "wide-adjacency-relation",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            )
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        assert result.global_lattice_authority is not None
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 3)
        self.assertTrue(
            all(
                item.state.value == "complete"
                for item in result.adjacency_observation_coverage
                if item.normal_inference_required
            )
        )
        anomalies = tuple(
            relation
            for relation in result.best.adjacency_relations
            if relation.is_anomaly
        )
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].relation_ordinal, 2)
        self.assertAlmostEqual(result.best.model_role_positions_px[4], 253.0)
        self.assertAlmostEqual(result.best.model_role_positions_px[5], 353.0)
        self.assertEqual(
            result.receipt.adjacency_relation_evaluation_count,
            2,
        )
        self.assertEqual(result.receipt.fit_pass_count, 2)

    def test_direct_separator_refit_cannot_add_phase_authority(self) -> None:
        observations = tuple(
            edge(f"fixed-refit:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 253.0, 365.0)
            )
        )
        spec = template(3)
        measurement_sets = (
            phase_sequence_measurement(
                "fixed-separator-refit",
                FiniteInterval(0.0, 400.0),
            ),
        )
        normal = fit_template_phase(
            observations,
            spec,
            sequence_measurement_sets=measurement_sets,
        )
        self.assertEqual(normal.status, PhaseFitStatus.RESOLVED)
        assert normal.best is not None
        fixed = tuple(
            (role_index, binding.observation_id)
            for role_index, binding in enumerate(normal.best.role_bindings)
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        )
        relation = SeparatorRelation(
            relation_ordinal=2,
            kind=SeparatorRelationKind.WIDE,
            delta_interval_px=FiniteInterval.exact(3.0),
            canonical_delta_px=3.0,
            separator_band_observation_id=ObservationId("fixed-refit:band"),
            end_edge_observation_id=observations[3].observation_id,
            next_start_edge_observation_id=observations[4].observation_id,
            signed_gap_interval_px=FiniteInterval.exact(23.0),
            canonical_signed_gap_px=23.0,
        )
        adjusted = fit_template_phase(
            observations,
            spec,
            adjacency_relations=(
                SeparatorRelation(
                    relation_ordinal=1,
                    kind=SeparatorRelationKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                ),
                relation,
            ),
            sequence_measurement_sets=measurement_sets,
            phase_anchor_authority_ceiling=fixed,
        )

        self.assertEqual(adjusted.status, PhaseFitStatus.RESOLVED)
        assert adjusted.best is not None
        self.assertTrue(
            set(
                (role_index, binding.observation_id)
                for role_index, binding
                in enumerate(adjusted.best.role_bindings)
                if binding is not None
                and binding.use == SequenceBindingUse.PHASE_ANCHOR
            ).issubset(set(fixed)),
        )
        self.assertIsNone(adjusted.best.role_bindings[5])

    def test_direct_narrow_separator_uses_the_same_single_suffix_relation(self) -> None:
        observations = tuple(
            edge(f"edge:narrow:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 127.0, 227.0, 247.0, 347.0)
            )
        )
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(
                    separator(
                        "separator:narrow",
                        observations[1],
                        observations[2],
                        FiniteInterval(16.8, 17.2),
                    ),
                ),
                template=template(3),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(3)),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "narrow-adjacency-relation",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        anomalies = tuple(
            relation
            for relation in result.best.adjacency_relations
            if relation.is_anomaly
        )
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].kind, SeparatorRelationKind.NARROW)
        self.assertEqual(anomalies[0].relation_ordinal, 1)
        self.assertAlmostEqual(result.best.model_role_positions_px[2], 127.0)
        self.assertAlmostEqual(result.best.model_role_positions_px[4], 247.0)

    def test_local_separator_cannot_override_conflicting_edge_roles(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0)
            )
        )
        fit = fit_template_phase(observations, template(2)).best
        assert fit is not None
        bindings = list(fit.role_bindings)
        bindings[1], bindings[2] = bindings[2], bindings[1]
        reversed_fit = replace(fit, role_bindings=tuple(bindings))
        band = separator(
            "separator:direct-role-relation",
            observations[1],
            observations[2],
            FiniteInterval(19.8, 20.2),
            region_count=2,
        )

        authority = assess_direct_role_binding_authority(
            reversed_fit,
            observations,
            (band,),
            (
                phase_sequence_measurement(
                    "reversed-local-separator-pair",
                    FiniteInterval(0.0, 260.0),
                ),
            ),
        )

        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        conflicts = tuple(
            item
            for item in authority.facts
            if item.state == EvidenceState.CONTRADICTED
        )
        self.assertEqual(
            tuple(item.role_index for item in conflicts),
            (1, 2),
        )
        self.assertTrue(
            all(
                item.blocking_material_conflict_ids
                == (band.observation_id,)
                for item in conflicts
            )
        )

    def test_unrelated_two_region_separator_does_not_block_selected_roles(
        self,
    ) -> None:
        selected = self._phase_candidate_group("selected", 0.0)
        spec = template(2)
        fit = fit_template_phase(selected, spec).best
        assert fit is not None
        unrelated_left = replace(
            edge("unrelated:separator:left", 500.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
            trace_coordinates_px=(10, 20),
            support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0,
        )
        unrelated_right = replace(
            edge("unrelated:separator:right", 520.0),
            qualified_anchor_roles=(BoundaryRole.START,),
            polarity=1,
            trace_coordinates_px=(10, 20),
            support_fraction=2.0 / 3.0,
            continuous_support_fraction=2.0 / 3.0,
        )
        unrelated_band = separator(
            "unrelated:separator",
            unrelated_left,
            unrelated_right,
            FiniteInterval(19.8, 20.2),
            region_count=2,
        )

        authority = assess_direct_role_binding_authority(
            fit,
            (*selected, unrelated_left, unrelated_right),
            (unrelated_band,),
            (
                phase_sequence_measurement(
                    "unrelated-two-region-separator",
                    FiniteInterval(0.0, 560.0),
                ),
            ),
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertTrue(
            all(not item.blocking_material_conflict_ids for item in authority.facts)
        )

    def test_late_reversed_pair_eliminates_winner_and_promotes_legal_runner(
        self,
    ) -> None:
        observations = tuple(
            replace(
                edge(f"late-reversed:{index}", coordinate),
                canonical_direction_degrees=0.0,
                fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                full_direction_interval_degrees=FiniteInterval.exact(0.0),
            )
            for index, coordinate in enumerate(
                (10.0, 120.0, 130.0, 230.0)
            )
        )
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(80.0, 130.0),
        )
        base = fit_template_phase(observations, spec)
        base_fit = base.best
        assert base_fit is not None

        def role_binding(
            observation: BoundaryEdgeObservation,
        ) -> SequenceRoleBinding:
            return SequenceRoleBinding(
                use=SequenceBindingUse.PHASE_ANCHOR,
                observation_id=observation.observation_id,
                evidence_group_id=observation.observation_id,
                canonical_position_px=observation.canonical_position_px,
                fit_position_interval_px=(
                    observation.fit_position_interval_px
                ),
                full_position_interval_px=(
                    observation.full_position_interval_px
                ),
                line_evidence=None,
            )

        normal_fit = replace(
            base_fit,
            model_role_positions_px=tuple(
                item.canonical_position_px for item in observations
            ),
            model_role_intervals_px=tuple(
                item.fit_position_interval_px for item in observations
            ),
            model_full_role_intervals_px=tuple(
                item.full_position_interval_px for item in observations
            ),
            role_bindings=tuple(role_binding(item) for item in observations),
            phase_support_coverage=0.0,
        )
        wrong_bindings = list(normal_fit.role_bindings)
        wrong_bindings[1] = role_binding(observations[2])
        wrong_bindings[2] = None
        wrong_fit = replace(
            normal_fit,
            role_bindings=tuple(wrong_bindings),
            phase_support_coverage=0.0,
        )
        band = separator(
            "late-reversed:separator",
            observations[1],
            observations[2],
            FiniteInterval(9.8, 10.2),
            region_count=2,
        )
        measurement_sets = (
            phase_sequence_measurement(
                "late-reversed-candidate-elimination",
                FiniteInterval(0.0, 260.0),
            ),
        )
        wrong_authority = assess_direct_role_binding_authority(
            wrong_fit,
            observations,
            (band,),
            measurement_sets,
        )
        runner_authority = assess_direct_role_binding_authority(
            normal_fit,
            observations,
            (band,),
            measurement_sets,
        )
        self.assertEqual(wrong_authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(runner_authority.state, EvidenceState.SUPPORTED)
        refined_wrong = _refine_local_role_bindings(
            wrong_fit,
            observations,
            (band,),
            intrinsic_coordinate_authority_ids=frozenset(
                item.observation_id for item in observations
            ),
        ).fit
        self.assertEqual(
            refined_wrong.binding_observation_ids[2],
            observations[1].observation_id,
        )

        def eligible_projection(fit, authority):
            return PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=PhaseCandidateProjectionOutcome.UNCHANGED,
                basis=PhaseCandidateProjectionBasis.DIRECT_BINDINGS,
                projected_out_bindings=(),
                retained_direct_constraint_rank=direct_role_constraint_rank(
                    fit,
                    authority.supported_role_indices,
                ),
                reason=None,
            )

        competition = replace(
            base,
            best=wrong_fit,
            runner_up=normal_fit,
            status=PhaseFitStatus.RESOLVED,
            ambiguity_reason=None,
            failure_kind=None,
            winner_basis=PhaseWinnerBasis.INDEPENDENT_SUPPORT,
            best_phase_candidate_authority_projection=(
                eligible_projection(wrong_fit, wrong_authority)
            ),
            runner_phase_candidate_authority_projection=(
                eligible_projection(normal_fit, runner_authority)
            ),
        )
        phase_input = TemplatePhaseInput(
            observations=observations,
            separator_bands=(band,),
            template=spec,
            calibrated_nominal_grid_prior=(
                unavailable_nominal_grid_prior(spec)
            ),
            scale_px_per_mm=None,
            holder_span_px=FiniteInterval(0.0, 260.0),
            phase_authority_px=None,
            sequence_measurement_sets=measurement_sets,
        )

        result = _refine_selected_roles_with_candidate_elimination(
            competition,
            phase_input,
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.binding_observation_ids[1:3],
            (
                observations[1].observation_id,
                observations[2].observation_id,
            ),
        )
        self.assertEqual(
            result.winner_basis,
            PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY,
        )
        self.assertEqual(
            len(result.eliminated_candidate_authority_projections),
            1,
        )
        eliminated = result.eliminated_candidate_authority_projections[0]
        self.assertEqual(
            eliminated.outcome,
            PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
        )
        self.assertEqual(
            tuple(
                item.role_index
                for item in eliminated.input_direct_role_authority.facts
                if item.state == EvidenceState.CONTRADICTED
            ),
            (1, 2),
        )

    def test_unique_source_wide_band_grants_separator_roles(self) -> None:
        observations = tuple(
            edge(f"edge:unique-source-wide:{index}", coordinate)
            for index, coordinate in enumerate((110.0, 130.0))
        )
        authority = _separator_role_authority(
            observations,
            (
                separator(
                    "separator:unique-source-wide",
                    observations[0],
                    observations[1],
                    FiniteInterval(19.8, 20.2),
                ),
            )
        )

        self.assertEqual(
            authority,
            {
                observations[0].observation_id: frozenset(
                    (BoundaryRole.END,)
                ),
                observations[1].observation_id: frozenset(
                    (BoundaryRole.START,)
                ),
            },
        )

    def test_unique_source_wide_pair_retains_roles_across_leaf_alternative(
        self,
    ) -> None:
        observations = list(
            edge(f"edge:source-wide:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 110.0, 130.0, 150.0, 250.0))
        )
        observations[1] = replace(
            observations[1],
            polarity=-1,
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        observations[2] = replace(
            observations[2],
            polarity=1,
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        observations[3] = replace(
            observations[3],
            polarity=1,
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        authority = _separator_role_authority(
            tuple(observations),
            (
                separator(
                    "separator:local-alternative",
                    observations[1],
                    observations[3],
                    FiniteInterval(39.8, 40.2),
                    region_count=2,
                ),
                separator(
                    "separator:source-wide",
                    observations[1],
                    observations[2],
                    FiniteInterval(19.8, 20.2),
                ),
            ),
        )
        self.assertEqual(
            authority,
            {
                observations[1].observation_id: frozenset(
                    (BoundaryRole.END,)
                ),
                observations[2].observation_id: frozenset(
                    (BoundaryRole.START,)
                ),
            },
        )

    def test_local_separator_center_protects_only_its_weak_edge(self) -> None:
        observations = (
            replace(
                edge("material:outer-start", 10.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("material:strong-end", 110.0),
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            replace(
                edge("material:weak-start", 130.0, support_fraction=0.4),
                polarity=1,
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("material:outer-end", 230.0),
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
        )
        result = fit_template_phase(
            observations,
            template(2),
            separator_bands=(
                separator(
                    "material:local-band",
                    observations[1],
                    observations[2],
                    FiniteInterval(19.8, 20.0),
                    region_count=2,
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.model_full_role_intervals_px[1],
            observations[1].full_position_interval_px,
        )
        self.assertLess(
            result.best.model_full_role_intervals_px[2].minimum,
            observations[2].full_position_interval_px.minimum,
        )

    def test_two_direct_gap_anomalies_bind_two_measured_relations(self) -> None:
        nominal_edges = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 250.0, 350.0)
            )
        )
        fit = fit_template_phase(nominal_edges, template(3)).best
        assert fit is not None
        bands = (
            separator(
                "separator:first",
                nominal_edges[1],
                nominal_edges[2],
                FiniteInterval(22.8, 23.2),
            ),
            separator(
                "separator:second",
                nominal_edges[3],
                nominal_edges[4],
                FiniteInterval(22.8, 23.2),
            ),
        )
        analysis = derive_adjacency_relations(
            fit,
            _continuity_for_residual(fit, nominal_edges, bands),
        )
        self.assertEqual(
            analysis.pattern,
            ResidualPattern.MEASURED_RELATIONS,
        )
        self.assertEqual(analysis.anomaly_ordinals, (1, 2))
        self.assertEqual(
            tuple(item.kind for item in analysis.relations),
            (SeparatorRelationKind.WIDE, SeparatorRelationKind.WIDE),
        )
        self.assertIsNone(analysis.unresolved_reason)
        self.assertEqual(analysis.evaluated_adjacency_count, 2)

    def test_direct_normal_gap_replaces_pitch_only_for_an_inferred_suffix(
        self,
    ) -> None:
        spec = template(3)
        fit = placement_sequence(spec, missing=(4, 5))
        observations = tuple(
            edge(f"sequence:{index}", coordinate)
            for index, coordinate in enumerate(
                (100.0, 200.0, 220.0, 320.0, 340.0, 440.0)
            )
        )
        bands = (
            separator(
                "separator:normal-measured",
                observations[1],
                observations[2],
                FiniteInterval(19.8, 20.2),
            ),
        )

        analysis = derive_adjacency_relations(
            fit,
            _continuity_for_residual(fit, observations, bands),
        )

        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
        self.assertEqual(analysis.anomaly_ordinals, ())
        self.assertEqual(len(analysis.relations), 1)
        relation = analysis.relations[0]
        self.assertIsInstance(relation, SeparatorRelation)
        assert isinstance(relation, SeparatorRelation)
        self.assertEqual(relation.kind, SeparatorRelationKind.NORMAL)
        self.assertTrue(relation.is_measured)
        self.assertFalse(relation.is_anomaly)
        self.assertEqual(relation.canonical_signed_gap_px, 20.0)

    def test_reversed_direct_edges_form_one_bounded_overlap_relation(self) -> None:
        regular = tuple(
            edge(f"edge:contact:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 250.0, 350.0)
            )
        )
        fit = fit_template_phase(regular, template(3)).best
        assert fit is not None
        overlap = list(regular)
        overlap[2] = edge("edge:contact:2", 105.0)

        analysis = derive_adjacency_relations(
            fit,
            _continuity_for_residual(fit, tuple(overlap), ()),
        )

        self.assertEqual(analysis.pattern, ResidualPattern.MEASURED_RELATIONS)
        self.assertEqual(len(analysis.relations), 1)
        self.assertIsInstance(analysis.relations[0], OverlapRelation)
        self.assertIsNone(analysis.unresolved_reason)

    def test_repeated_direct_gap_facts_are_all_applied_before_output_bleed(self) -> None:
        regular = tuple(
            edge(f"edge:overflow:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 131.0, 231.0, 252.0, 352.0, 373.0, 473.0)
            )
        )
        fit = fit_template_phase(regular, template(4)).best
        assert fit is not None
        bands = tuple(
            separator(
                f"separator:overflow:{index}",
                regular[2 * index + 1],
                regular[2 * index + 2],
                FiniteInterval(20.8, 21.2),
            )
            for index in range(3)
        )
        analysis = derive_adjacency_relations(
            fit,
            _continuity_for_residual(fit, regular, bands),
        )
        self.assertEqual(
            analysis.pattern,
            ResidualPattern.MEASURED_RELATIONS,
        )
        self.assertEqual(len(analysis.relations), 3)
        self.assertTrue(all(item.is_anomaly for item in analysis.relations))
        result = fit_template_phase_with_adjacency_relations(
            TemplatePhaseInput(
                observations=regular,
                separator_bands=bands,
                template=template(4),
                calibrated_nominal_grid_prior=unavailable_nominal_grid_prior(template(4)),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
            )
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(len(result.best.adjacency_relations), 3)

    def test_bound_overflow_is_explicit_and_receipt_cannot_be_overstated(self) -> None:
        result = fit_template_phase(
            (edge("edge:0", 10.0), edge("edge:1", 110.0)),
            template(1),
            max_observations=1,
        )
        self.assertEqual(result.status, PhaseFitStatus.BOUND_EXCEEDED)
        self.assertIsNone(result.best_phase_candidate_authority_projection)
        self.assertIsNone(result.runner_phase_candidate_authority_projection)
        self.assertEqual(
            result.receipt.candidate_direct_role_projection_evaluation_count,
            0,
        )
        with self.assertRaises(ValueError):
            replace(result.receipt, phase_lookup_count=13).validate_bounds(
                observation_count=2,
                role_count=2,
                slot_count=1,
            )
        receipt = TemplateSearchReceipt(
            observation_count=2,
            role_count=2,
            phase_lookup_count=4,
            role_binding_count=4,
            adjacency_relation_evaluation_count=0,
            local_refinement_lookup_count=0,
            local_refinement_binding_count=0,
            phase_hypothesis_count=4,
            phase_offset_lookup_count=4,
            direct_observation_count=2,
            inferred_role_count=0,
        )
        receipt.validate_bounds(
            observation_count=2,
            role_count=2,
            slot_count=1,
        )
        replace(receipt, fit_pass_count=6).validate_bounds(
            observation_count=2,
            role_count=2,
            slot_count=1,
        )
        with self.assertRaisesRegex(ValueError, "fit pass bound"):
            replace(receipt, fit_pass_count=7).validate_bounds(
                observation_count=2,
                role_count=2,
                slot_count=1,
            )


if __name__ == "__main__":
    unittest.main()
