from __future__ import annotations

from dataclasses import replace
import math
import unittest

from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeObservation,
    SeparatorBandObservation,
    SeparatorMaterialRegionObservation,
)
from x5crop.detection.photo_geometry.template_model import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    PhaseAnchor,
    PhaseAnchorAuthority,
    PhaseLatticeAuthority,
    TemplateSearchReceipt,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import (
    fit_template_phase,
    fit_template_phase_with_local_advance,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
    PhaseWinnerBasis,
)
from x5crop.detection.photo_geometry.template_residual import (
    derive_bounded_local_advances,
)
from x5crop.detection.photo_geometry.template_stability import (
    AnchorDependencyEffect,
    leave_one_anchor_out_phase_stability,
)
from x5crop.domain import FiniteInterval, ObservationId


def edge(
    name: str,
    coordinate: float,
    *,
    support_fraction: float = 1.0,
) -> BoundaryEdgeObservation:
    identity = ObservationId(name)
    return BoundaryEdgeObservation(
        observation_id=identity,
        run_id=f"run:{name}",
        coordinate_interval_px=FiniteInterval(coordinate - 0.2, coordinate + 0.2),
        transition_ids=(ObservationId(f"transition:{name}"),),
        trace_coordinates_px=(0, 10, 20),
        polarity=1,
        support_fraction=support_fraction,
        continuous_support_fraction=support_fraction,
        fit_residual_px=0.0,
        canonical_direction_degrees=None,
        fit_direction_interval_degrees=None,
        full_direction_interval_degrees=None,
        qualified_anchor_roles=(BoundaryRole.START, BoundaryRole.END),
    )


def template(count: int) -> TemplateSpec:
    return TemplateSpec(
        template_id="test-template",
        frame_width_px=100.0,
        pitch_px=120.0,
        count=count,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=120.0,
            cycle_origin_px=0.0,
            minimum_slot_offset=-1,
            maximum_slot_offset=20,
        ),
        nominal_gap_px=20.0,
    )


def separator(
    name: str,
    left: BoundaryEdgeObservation,
    right: BoundaryEdgeObservation,
    gap: FiniteInterval,
) -> SeparatorBandObservation:
    material = tuple(
        SeparatorMaterialRegionObservation(
            region_index=index,
            sample_count=3,
            darkness_contrast_interval=FiniteInterval(1.0, 2.0),
            texture_contrast_interval=FiniteInterval(0.5, 1.0),
        )
        for index in range(2)
    )
    return SeparatorBandObservation(
        observation_id=ObservationId(name),
        left_edge_observation_id=left.observation_id,
        right_edge_observation_id=right.observation_id,
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        gap_interval_px=gap,
        transition_ids=(
            ObservationId(f"transition:{name}:left"),
            ObservationId(f"transition:{name}:right"),
        ),
        independent_support_region_count=2,
        continuous_support_fraction=1.0,
        darkness_contrast=1.5,
        darkness_contrast_interval=FiniteInterval(1.0, 2.0),
        texture_contrast=0.75,
        texture_contrast_interval=FiniteInterval(0.5, 1.0),
        material_regions=material,
    )


class TemplatePhaseContractTest(unittest.TestCase):
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
        duplicate = result.best.role_observation_ids[0]
        assert duplicate is not None
        with self.assertRaisesRegex(ValueError, "multiple template roles"):
            replace(
                result.best,
                role_observation_ids=(
                    duplicate,
                    duplicate,
                    *result.best.role_observation_ids[2:],
                ),
            )

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
        self.assertEqual(result.best.support_count, 6)
        self.assertEqual(result.best.inferred_role_indices, ())

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

    def test_direct_phase_prior_adds_one_bounded_calibration_seed(self) -> None:
        observations = (
            edge("prior-start", 40.0),
            edge("prior-next-start", 160.0),
            edge("clutter-start", 55.0),
            edge("late-end", 260.0),
        )
        result = fit_template_phase(
            observations,
            template(2),
            phase_prior_px=FiniteInterval(38.0, 42.0),
        )
        self.assertIn(result.status, (PhaseFitStatus.RESOLVED, PhaseFitStatus.AMBIGUOUS))
        assert result.best is not None
        self.assertEqual(
            result.best.role_observation_ids[0],
            ObservationId("prior-start"),
        )
        self.assertLessEqual(
            result.receipt.phase_hypothesis_count,
            result.receipt.observation_count * max(6, result.receipt.role_count),
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

    def test_phase_lattice_offset_bound_rejects_shifted_chain(self) -> None:
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
                PhaseAnchor(
                    observation_id=ObservationId(f"shifted:{role.role_index}"),
                    coordinate_interval_px=FiniteInterval.exact(coordinate),
                    role=role,
                    authority=PhaseAnchorAuthority.USER_PROVIDED,
                    authority_id="user-anchor:1",
                )
                for role, coordinate in zip(
                    constrained.roles,
                    (160.0, 260.0, 280.0, 380.0),
                    strict=True,
                )
            ),
            constrained,
        )
        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)

    def test_manual_phase_anchor_requires_explicit_user_authority(self) -> None:
        role = template(1).roles[0]
        with self.assertRaises((TypeError, ValueError)):
            PhaseAnchor(  # type: ignore[arg-type]
                observation_id=ObservationId("manual:missing-authority"),
                coordinate_interval_px=FiniteInterval.exact(40.0),
                role=role,
                authority=None,
                authority_id="",
            )
        manual = PhaseAnchor(
            observation_id=ObservationId("manual:first-left"),
            coordinate_interval_px=FiniteInterval(39.5, 40.5),
            role=role,
            authority=PhaseAnchorAuthority.USER_PROVIDED,
            authority_id="user-anchor:source-1",
        )
        result = fit_template_phase((manual,), template(1))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.role_observation_ids[role.role_index],
            manual.observation_id,
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
            narrowed.best.role_observation_ids,
            result.best.role_observation_ids,
        )
        self.assertAlmostEqual(
            narrowed.best.pitch_fit.canonical_frame_width_px,
            100.0,
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
        self.assertEqual(result.best.support_count, 6)

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
        self.assertEqual(result.best.support_count, 6)

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
            result.best.role_observation_ids,
            (ObservationId("outer-start"), ObservationId("outer-end")),
        )

    def test_one_role_residual_does_not_expand_every_direct_role(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 160.0, 260.0, 280.0, 385.0)
            )
        )
        result = fit_template_phase(observations, template(3))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        first = result.best.role_positions_px[0]
        last = result.best.role_positions_px[-1]
        self.assertLess(first.width, 6.0)
        self.assertGreater(last.width, first.width)

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
        self.assertEqual(result.best.inferred_role_indices, (2, 3))

        unresolved = fit_template_phase((), template(3))
        self.assertEqual(unresolved.status, PhaseFitStatus.UNRESOLVED)
        self.assertIn("direct", unresolved.ambiguity_reason or "")

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
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        first_missing_start = result.best.role_positions_px[2]
        last_missing_start = result.best.role_positions_px[6]
        self.assertAlmostEqual(
            last_missing_start.width - first_missing_start.width,
            8.0,
        )
        # A direct observation keeps its own local interval and is not widened
        # by pitch authority belonging to later inferred roles.
        self.assertLess(result.best.role_positions_px[0].width, 2.0)

    def test_far_separated_direct_roles_narrow_continuous_pitch(self) -> None:
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
            PhaseAnchor(
                observation_id=ObservationId(f"far-span:{role_index}"),
                coordinate_interval_px=FiniteInterval(
                    coordinate - 0.2,
                    coordinate + 0.2,
                ),
                role=compiled.roles[role_index],
                authority=PhaseAnchorAuthority.USER_PROVIDED,
                authority_id="user-anchor:far-span",
            )
            for role_index, coordinate in (
                (2, 160.0),
                (3, 260.0),
                (10, 640.0),
                (11, 740.0),
            )
        )
        result = fit_template_phase(anchors, compiled)
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertIsNone(result.runner_up)
        self.assertEqual(
            result.best.role_observation_ids,
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
        self.assertLess(result.best.role_positions_px[8].width, 3.0)

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
        slot_two_start = result.best.role_positions_px[4]
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
            observations,
            (),
            compiled,
        )
        self.assertEqual(
            analysis.receipt.refit_count,
            len(result.best.direct_observation_ids),
        )
        self.assertLessEqual(analysis.receipt.refit_count, 4)
        self.assertTrue(
            all(
                item.effect in tuple(AnchorDependencyEffect)
                for item in analysis.dependencies
            )
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

    def test_sampling_equivalent_runner_does_not_block_regular_template(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (40.0, 140.0, 43.0, 143.0, 160.0, 260.0)
            )
        )
        result = fit_template_phase(observations, template(2))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(
            result.winner_basis,
            PhaseWinnerBasis.SAMPLING_EQUIVALENT_RUNNER,
        )
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None and result.runner_up is not None
        self.assertLessEqual(
            max(
                abs(left - right)
                for left, right in zip(
                    result.best.canonical_role_positions_px,
                    result.runner_up.canonical_role_positions_px,
                    strict=True,
                )
            ),
            3.0,
        )

    def test_local_anomaly_prefix_is_transmitted_once(self) -> None:
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
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertAlmostEqual(result.best.role_positions_px[4].center, 250.0)
        self.assertAlmostEqual(result.best.role_positions_px[5].center, 350.0)

    def test_direct_separator_authorizes_one_bounded_local_refit(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 253.0, 353.0)
            )
        )
        result = fit_template_phase_with_local_advance(
            observations,
            (
                separator(
                    "separator:wide",
                    observations[3],
                    observations[4],
                    FiniteInterval(22.8, 23.2),
                ),
            ),
            template(3),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        anomalies = tuple(
            relation
            for relation in result.best.local_advance_relations
            if relation.is_anomaly
        )
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].relation_ordinal, 2)
        self.assertAlmostEqual(result.best.canonical_role_positions_px[4], 253.0)
        self.assertAlmostEqual(result.best.canonical_role_positions_px[5], 353.0)
        self.assertEqual(result.receipt.local_relation_evaluation_count, 2)
        self.assertEqual(result.receipt.fit_pass_count, 2)

    def test_separator_relation_overrides_conflicting_single_edge_role_hint(self) -> None:
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
            tuple(observations),
            (
                separator(
                    "separator:direct-role-relation",
                    observations[1],
                    observations[2],
                    FiniteInterval(19.8, 20.2),
                ),
            ),
            template(2),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.role_observation_ids,
            tuple(item.observation_id for item in observations),
        )

    def test_two_direct_gap_anomalies_are_unresolved_without_search(self) -> None:
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
        self.assertEqual(analysis.anomaly_ordinals, ())
        self.assertEqual(analysis.relations, ())
        self.assertIn("exceed", analysis.unresolved_reason or "")
        self.assertEqual(analysis.evaluated_adjacency_count, 2)

    def test_three_direct_gap_anomalies_are_unresolved_without_search(self) -> None:
        regular = tuple(
            edge(f"edge:overflow:{index}", coordinate)
            for index, coordinate in enumerate(
                (10.0, 110.0, 130.0, 230.0, 250.0, 350.0, 370.0, 470.0)
            )
        )
        fit = fit_template_phase(regular, template(4)).best
        assert fit is not None
        bands = tuple(
            separator(
                f"separator:overflow:{index}",
                regular[2 * index + 1],
                regular[2 * index + 2],
                FiniteInterval(22.8, 23.2),
            )
            for index in range(3)
        )
        analysis = derive_bounded_local_advances(fit, regular, bands)
        self.assertEqual(analysis.relations, ())
        self.assertIn("exceed", analysis.unresolved_reason or "")
        result = fit_template_phase_with_local_advance(
            regular,
            bands,
            template(4),
        )
        self.assertEqual(result.status, PhaseFitStatus.UNRESOLVED)
        self.assertEqual(result.failure_kind, PhaseFailureKind.LOCAL_ADVANCE_AMBIGUOUS)

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
