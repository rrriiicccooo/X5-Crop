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
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
)
from x5crop.detection.photo_geometry.template_model import (
    SeparatorRelationKind,
    PhaseLatticeAuthority,
    SequenceBindingUse,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    intrinsic_direct_role_authority_bases,
)
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase import fit_template_phase_with_adjacency_relations
from x5crop.detection.photo_geometry.template_phase_fitting import _match_roles
from x5crop.detection.photo_geometry.template_phase_observations import (
    _facts,
    _refine_local_role_bindings,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from tools.tests.phase_test_support import (
    _fit_with_independent_source_width,
    _local_line,
)


class TemplatePhaseLocalRolesContractTest(unittest.TestCase):
    def test_unique_local_closure_refines_roles_without_phase_authority(
        self,
    ) -> None:
        anchor = replace(
            _local_line("anchor:start:1", 100.0, BoundaryRole.START),
            fit_residual_px=0.0,
        )
        end1 = _local_line("local:end:1", 201.0, BoundaryRole.END)
        start2 = _local_line("local:start:2", 221.0, BoundaryRole.START)
        end2 = _local_line("local:end:2", 321.0, BoundaryRole.END)
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
            _local_line("anchor:start:1", 100.0, BoundaryRole.START),
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
                    _local_line(
                        "local:start:2:a", 221.0, BoundaryRole.START
                    ),
                    _local_line(
                        "local:start:2:b", 223.0, BoundaryRole.START
                    ),
                    _local_line(
                        "local:end:2:a", 321.0, BoundaryRole.END
                    ),
                    _local_line(
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
        true_start = _local_line(
            "local:true:start:1",
            90.0,
            BoundaryRole.START,
        )
        weak_start = _local_line(
            "local:weak:start:1",
            90.25,
            BoundaryRole.START,
        )
        true_end = _local_line(
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
        first_start = _local_line(
            "local:first:start:1",
            100.0,
            BoundaryRole.START,
        )
        second_start = _local_line(
            "local:second:start:1",
            100.25,
            BoundaryRole.START,
        )
        true_end = _local_line(
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
        first_start = _local_line(
            "source-width:first:start:1",
            90.0,
            BoundaryRole.START,
        )
        true_start = _local_line(
            "source-width:true:start:1",
            100.0,
            BoundaryRole.START,
        )
        end = _local_line(
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
        start = _local_line(
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
        start = _local_line(
            "source-width:intrinsic:start:1",
            100.0,
            BoundaryRole.START,
        )
        conflicting_end = _local_line(
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
        first = _local_line(
            "source-width:first:start:1",
            99.0,
            BoundaryRole.START,
        )
        second = _local_line(
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

    def test_narrow_atomic_separator_closes_missing_roles_without_nominal_gap_permission(
        self,
    ) -> None:
        spec = replace(
            template(2),
            frame_width_px=PositiveInterval(90.0, 110.0),
            nominal_gap_px=FiniteInterval(19.0, 21.0),
        )
        fit = placement_sequence(spec, missing=(1, 2))
        end = _local_line("narrow:end", 200.0, BoundaryRole.END)
        start = _local_line("narrow:start", 210.0, BoundaryRole.START)
        alternative = _local_line("narrow:alternative", 211.0, BoundaryRole.START)
        band = separator("narrow:band", end, start, FiniteInterval(9.8, 10.2))

        refined = _refine_local_role_bindings(fit, (end, start, alternative), (band,))

        self.assertEqual(
            refined.fit.binding_observation_ids[1:3],
            (end.observation_id, start.observation_id),
        )
        self.assertEqual(refined.fit.phase_lattice_fit, fit.phase_lattice_fit)
        self.assertEqual(refined.fit.pitch_fit, fit.pitch_fit)
        self.assertEqual(refined.fit.role_bindings[0], fit.role_bindings[0])
        self.assertEqual(refined.fit.role_bindings[3], fit.role_bindings[3])
        self.assertEqual(refined.fit.role_bindings[1].canonical_position_px, 200.0)
        self.assertEqual(refined.fit.role_bindings[2].canonical_position_px, 210.0)

        competing_band = separator(
            "narrow:competing-band", end, alternative, FiniteInterval(10.8, 11.2),
        )
        partial_band = separator(
            "narrow:partial-band", end, start, FiniteInterval(9.8, 10.2), region_count=2,
        )
        for bands in ((band, competing_band), (partial_band,)):
            with self.subTest(bands=tuple(item.observation_id for item in bands)):
                unavailable = _refine_local_role_bindings(
                    fit, (end, start, alternative), bands
                )
                self.assertIsNone(unavailable.fit.role_bindings[2])
        width_conflict = _refine_local_role_bindings(
            fit, (end, start, alternative), (band,),
            frame_width_authority_px=FiniteInterval(99.0, 101.0),
        )
        self.assertIsNone(width_conflict.fit.role_bindings[2])

    def test_locally_bound_separator_drives_one_wide_advance(self) -> None:
        anchor = replace(
            _local_line("anchor:start:1", 100.0, BoundaryRole.START),
            fit_residual_px=0.0,
        )
        end1 = _local_line("local:end:1", 201.0, BoundaryRole.END)
        start2 = _local_line("local:start:2", 231.0, BoundaryRole.START)
        end2 = _local_line("local:end:2", 331.0, BoundaryRole.END)
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

    def test_local_short_edge_yields_to_correlated_source_width(self) -> None:
        observations = tuple(
            replace(
                _local_line(identity, coordinate, role),
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


if __name__ == "__main__":
    unittest.main()
