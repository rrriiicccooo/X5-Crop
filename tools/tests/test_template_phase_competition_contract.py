from __future__ import annotations

from dataclasses import replace
import math
import unittest

from tools.tests.template_test_support import (
    phase_edge as edge,
    placement_sequence,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
    unavailable_nominal_grid_prior,
)
from x5crop.detection.photo_geometry.model import BoundaryEvidenceState, BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    SeparatorMaterialPolarity,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.template_model import (
    OverlapRelation,
    SeparatorRelationKind,
    SeparatorRelation,
    PhaseLatticeAuthority,
    TemplateSearchReceipt,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_state import (
    _merge_continuous_placement,
    _same_continuous_placement,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase_with_adjacency_relations
from x5crop.detection.photo_geometry.template_phase_candidate_model import _BoundFit
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseWinnerBasis,
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_residual import (
    ResidualPattern,
    derive_adjacency_relations,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from tools.tests.phase_test_support import _continuity_for_residual


class TemplatePhaseCompetitionContractTest(unittest.TestCase):
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
