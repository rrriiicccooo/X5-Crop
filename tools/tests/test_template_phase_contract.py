from __future__ import annotations

from dataclasses import replace
import math
import unittest

from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    transformed_phase_edge as transformed_edge,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryEvidenceState,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeObservation,
    SeparatorMaterialPolarity,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.template_model import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    PhaseLatticeAuthority,
    SequenceBindingUse,
    TemplateSearchReceipt,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import (
    _merge_continuous_placement,
    _same_continuous_placement,
    fit_template_phase,
    fit_template_phase_with_local_advance,
)
from x5crop.detection.photo_geometry.template_phase_candidates import (
    _BoundFit,
    _facts,
    _match_roles,
)
from x5crop.detection.photo_geometry.template_phase_candidates import (
    _separator_role_authority,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    GlobalLatticeAuthorityEvidence,
    GlobalLatticeAuthorityBasis,
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseWinnerBasis,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_residual import (
    ResidualPattern,
    derive_bounded_local_advances,
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


class TemplatePhaseContractTest(unittest.TestCase):
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
        result = fit_template_phase_with_local_advance(
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
        result = fit_template_phase_with_local_advance(
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
                template=replace(
                    template(2),
                    frame_width_px=PositiveInterval(99.0, 101.0),
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

    def test_locally_bound_separator_drives_one_wide_advance(self) -> None:
        anchor = replace(
            self._local_line("anchor:start:1", 100.0, BoundaryRole.START),
            fit_residual_px=0.0,
        )
        end1 = self._local_line("local:end:1", 201.0, BoundaryRole.END)
        start2 = self._local_line("local:start:2", 231.0, BoundaryRole.START)
        end2 = self._local_line("local:end:2", 331.0, BoundaryRole.END)
        result = fit_template_phase_with_local_advance(
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
                template=replace(
                    template(2),
                    frame_width_px=PositiveInterval(98.0, 102.0),
                ),
                scale_px_per_mm=PositiveInterval.exact(100.0),
                holder_span_px=None,
                phase_authority_px=FiniteInterval.exact(100.0),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(result.best.phase_support_locations, (0,))
        self.assertEqual(len(result.best.local_advance_relations), 1)
        relation = result.best.local_advance_relations[0]
        self.assertEqual(relation.kind, LocalAdvanceKind.WIDE)
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
        with self.assertRaisesRegex(ValueError, "multiple template roles"):
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

        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(6),
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
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(result.best.phase_support_locations, (0, 1, 2, 3, 6))
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

    def test_grid_cannot_invent_an_entire_unanchored_outer_frame(self) -> None:
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

        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(6),
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

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE,
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
        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
                scale_px_per_mm=None,
                holder_span_px=FiniteInterval(0.0, 540.0),
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "short-unpaired-direct-role",
                        FiniteInterval(0.0, 540.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE,
        )
        assert result.direct_role_binding_authority is not None
        self.assertEqual(
            result.direct_role_binding_authority.unsupported_role_indices,
            (4,),
        )

    def test_fixed_width_pair_authorizes_two_independent_short_edges(self) -> None:
        observations = tuple(
            replace(
                edge(identity, coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
                trace_coordinates_px=(10, 20) if identity == "short:start:3" else (0, 10, 20),
                support_fraction=2.0 / 3.0 if identity == "short:start:3" else 1.0,
                continuous_support_fraction=(
                    2.0 / 3.0 if identity == "short:start:3" else 1.0
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
        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
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

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.direct_role_binding_authority is not None
        self.assertEqual(
            result.direct_role_binding_authority.unsupported_role_indices,
            (),
        )
        short_pair = tuple(
            item
            for item in result.direct_role_binding_authority.facts
            if item.role_index in {4, 5}
        )
        self.assertEqual(len(short_pair), 2)
        self.assertTrue(
            all(
                "frame_width_pair" in tuple(basis.value for basis in item.bases)
                for item in short_pair
            )
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
        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
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

    def test_edge_count_cannot_replace_phase_width_pitch_rank(self) -> None:
        observations = tuple(
            replace(
                edge(f"start:{slot}", 40.0 + 120.0 * slot),
                qualified_anchor_roles=(BoundaryRole.START,),
            )
            for slot in range(4)
        )
        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(),
                template=template(4),
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

        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE,
        )
        assert result.global_lattice_authority is not None
        self.assertEqual(
            result.global_lattice_authority.direct_role_constraint_rank,
            2,
        )
        self.assertEqual(result.global_lattice_authority.joint_constraint_rank, 2)

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

    def test_calibration_narrows_continuous_size_without_rebinding_roles(self) -> None:
        result = fit_template_phase(
            tuple(
                edge(f"edge:{index}", coordinate)
                for index, coordinate in enumerate((40.0, 140.0, 160.0, 260.0))
            ),
            template(2),
        )
        calibrated = TemplateSpec(
            template_id="test-template",
            frame_width_px=FiniteInterval(98.0, 102.0),
            pitch_px=FiniteInterval(118.0, 122.0),
            count=2,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=FiniteInterval(118.0, 122.0),
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
            nominal_gap_px=FiniteInterval(18.0, 22.0),
        )
        narrowed = result.with_calibrated_template(calibrated)
        self.assertEqual(
            narrowed.best.binding_observation_ids,
            result.best.binding_observation_ids,
        )
        self.assertAlmostEqual(
            narrowed.best.pitch_fit.canonical_frame_width_px,
            100.0,
        )

    def test_calibration_never_rewrites_a_direct_end_position(self) -> None:
        broad = TemplateSpec(
            template_id="direct-end-preservation",
            frame_width_px=FiniteInterval(98.0, 102.0),
            pitch_px=FiniteInterval(118.0, 122.0),
            count=2,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=FiniteInterval(118.0, 122.0),
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=20,
            ),
            nominal_gap_px=FiniteInterval(18.0, 22.0),
        )
        result = fit_template_phase(
            tuple(
                edge(f"direct:{index}", coordinate)
                for index, coordinate in enumerate((40.0, 141.0, 160.0, 261.0))
            ),
            broad,
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        narrowed = result.with_calibrated_template(
            replace(broad, frame_width_px=FiniteInterval(99.0, 101.0))
        )
        assert narrowed.best is not None
        self.assertEqual(
            narrowed.best.model_role_positions_px,
            result.best.model_role_positions_px,
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

    def test_more_supported_lattice_locations_outrank_more_local_edges(
        self,
    ) -> None:
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
                edge(f"contradiction:{index}", coordinate),
                qualified_anchor_roles=(role,),
                polarity=1 if role == BoundaryRole.START else -1,
            )
            for index, (coordinate, role) in enumerate(
                zip(coordinates, roles, strict=True)
            )
        )

        result = fit_template_phase(observations, template(3))

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(result.winner_basis, PhaseWinnerBasis.INDEPENDENT_SUPPORT)
        assert result.best is not None and result.runner_up is not None
        self.assertGreater(
            result.best.phase_support_count,
            result.runner_up.phase_support_count,
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
            result.best.independent_support_ids,
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

        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=observations,
                separator_bands=(conflict,),
                template=template(4),
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

    def test_local_advance_interval_is_applied_once_to_the_suffix(self) -> None:
        relation = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.WIDE,
            delta_interval_px=FiniteInterval(18.0, 22.0),
            canonical_delta_px=20.0,
            observation_ids=(ObservationId("gap:interval"),),
        )
        result = fit_template_phase(
            (edge("start", 10.0), edge("end", 110.0)),
            template(3),
            local_advance_relations=(relation,),
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

    def test_one_connected_separator_keeps_role_alternatives_continuous(self) -> None:
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
        self.assertTrue(_same_continuous_placement(fit, alternative))
        disconnected_bindings = list(alternative.role_bindings)
        for index, identity in zip((2, 3), alternative_ids, strict=True):
            binding = disconnected_bindings[index]
            assert binding is not None
            disconnected_bindings[index] = replace(
                binding,
                independent_support_id=identity,
            )
        disconnected = replace(
            alternative,
            role_bindings=tuple(disconnected_bindings),
        )
        self.assertFalse(_same_continuous_placement(fit, disconnected))

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
            left.independent_support_ids,
            right.independent_support_ids,
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

    def test_local_anomaly_prefix_is_transmitted_once_per_competing_fit(
        self,
    ) -> None:
        relation = LocalAdvanceRelation(
            relation_ordinal=1,
            kind=LocalAdvanceKind.WIDE,
            delta_interval_px=FiniteInterval.exact(20.0),
            canonical_delta_px=20.0,
            observation_ids=(ObservationId("gap:1"),),
        )
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 90.0, 130.0, 230.0, 250.0, 350.0))
        )
        result = fit_template_phase(
            observations,
            template(3),
            local_advance_relations=(relation,),
        )
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
        assert result.best is not None and result.runner_up is not None
        for fit in (result.best, result.runner_up):
            phase = fit.phase_lattice_fit.canonical_absolute_phase_px
            pitch = fit.pitch_fit.canonical_pitch_px
            self.assertAlmostEqual(
                fit.model_role_intervals_px[4].center,
                phase + 2.0 * pitch + 20.0,
            )
            self.assertAlmostEqual(
                fit.model_role_intervals_px[5].center,
                phase + 2.0 * pitch + 120.0,
            )

    def test_direct_separator_authorizes_one_bounded_local_refit(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 253.0, 353.0)
            )
        )
        result = fit_template_phase_with_local_advance(
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
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "wide-local-advance",
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
            for relation in result.best.local_advance_relations
            if relation.is_anomaly
        )
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].relation_ordinal, 2)
        self.assertAlmostEqual(result.best.model_role_positions_px[4], 253.0)
        self.assertAlmostEqual(result.best.model_role_positions_px[5], 353.0)
        self.assertEqual(result.receipt.local_relation_evaluation_count, 2)
        self.assertEqual(result.receipt.fit_pass_count, 2)

    def test_direct_narrow_separator_uses_the_same_single_suffix_relation(self) -> None:
        observations = tuple(
            edge(f"edge:narrow:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 127.0, 227.0, 247.0, 347.0)
            )
        )
        result = fit_template_phase_with_local_advance(
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
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
                sequence_measurement_sets=(
                    phase_sequence_measurement(
                        "narrow-local-advance",
                        FiniteInterval(0.0, 400.0),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        anomalies = tuple(
            relation
            for relation in result.best.local_advance_relations
            if relation.is_anomaly
        )
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].kind, LocalAdvanceKind.NARROW)
        self.assertEqual(anomalies[0].relation_ordinal, 1)
        self.assertAlmostEqual(result.best.model_role_positions_px[2], 127.0)
        self.assertAlmostEqual(result.best.model_role_positions_px[4], 247.0)

    def test_local_separator_cannot_override_conflicting_edge_roles(self) -> None:
        observations = list(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0)
            )
        )
        observations[1] = replace(
            observations[1],
            polarity=-1,
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        observations[2] = replace(
            observations[2],
            polarity=1,
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=tuple(observations),
                separator_bands=(
                separator(
                    "separator:direct-role-relation",
                    observations[1],
                    observations[2],
                    FiniteInterval(19.8, 20.2),
                    region_count=2,
                ),
                ),
                template=template(2),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
            )
        )
        self.assertNotEqual(result.status, PhaseFitStatus.RESOLVED)

    def test_source_wide_band_excludes_a_competing_local_edge_pair(self) -> None:
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
            authority[observations[1].observation_id],
            frozenset((BoundaryRole.END,)),
        )
        self.assertEqual(
            authority[observations[2].observation_id],
            frozenset((BoundaryRole.START,)),
        )
        self.assertNotIn(observations[3].observation_id, authority)

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

    def test_two_direct_gap_anomalies_bind_two_measured_advances(self) -> None:
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
        analysis = derive_bounded_local_advances(
            fit,
            nominal_edges,
            bands,
        )
        self.assertEqual(
            analysis.pattern,
            ResidualPattern.MEASURED_ADVANCES,
        )
        self.assertEqual(analysis.anomaly_ordinals, (1, 2))
        self.assertEqual(
            tuple(item.kind for item in analysis.relations),
            (LocalAdvanceKind.WIDE, LocalAdvanceKind.WIDE),
        )
        self.assertIsNone(analysis.unresolved_reason)
        self.assertEqual(analysis.evaluated_adjacency_count, 2)

    def test_direct_contact_or_overlap_without_band_stays_review_only(self) -> None:
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

        analysis = derive_bounded_local_advances(
            fit,
            tuple(overlap),
            (),
        )

        self.assertEqual(analysis.pattern, ResidualPattern.UNRESOLVED)
        self.assertEqual(analysis.relations, ())
        self.assertIn("end-then-start", analysis.unresolved_reason or "")

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
        analysis = derive_bounded_local_advances(fit, regular, bands)
        self.assertEqual(
            analysis.pattern,
            ResidualPattern.MEASURED_ADVANCES,
        )
        self.assertEqual(len(analysis.relations), 3)
        self.assertTrue(all(item.is_anomaly for item in analysis.relations))
        result = fit_template_phase_with_local_advance(
            TemplatePhaseInput(
                observations=regular,
                separator_bands=bands,
                template=template(4),
                scale_px_per_mm=None,
                holder_span_px=None,
                phase_authority_px=None,
            )
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(len(result.best.local_advance_relations), 3)

    def test_bound_overflow_is_explicit_and_receipt_cannot_be_overstated(self) -> None:
        result = fit_template_phase(
            (edge("edge:0", 10.0), edge("edge:1", 110.0)),
            template(1),
            max_observations=1,
        )
        self.assertEqual(result.status, PhaseFitStatus.BOUND_EXCEEDED)
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
            local_relation_evaluation_count=0,
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
        with self.assertRaisesRegex(ValueError, "fit pass bound"):
            replace(receipt, fit_pass_count=6).validate_bounds(
                observation_count=2,
                role_count=2,
                slot_count=1,
            )


if __name__ == "__main__":
    unittest.main()
