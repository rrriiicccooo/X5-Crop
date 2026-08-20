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
    PhaseLatticeAuthority,
    TemplateSearchReceipt,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import (
    _same_continuous_placement,
    fit_template_phase,
    fit_template_phase_with_local_advance,
)
from x5crop.detection.photo_geometry.template_phase_candidates import (
    _facts,
    _match_roles,
)
from x5crop.detection.photo_geometry.template_phase_candidates import (
    _separator_role_authority,
)
from x5crop.detection.photo_geometry.template_phase_model import (
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
from x5crop.domain import FiniteInterval, ObservationId


def edge(
    name: str,
    coordinate: float,
    *,
    support_fraction: float = 1.0,
) -> BoundaryEdgeObservation:
    identity = ObservationId(name)
    interval = FiniteInterval(coordinate - 0.2, coordinate + 0.2)
    return BoundaryEdgeObservation(
        observation_id=identity,
        run_id=f"run:{name}",
        discovery_interval_px=interval,
        reference_trace_px=10.0,
        canonical_position_px=coordinate,
        fit_position_interval_px=interval,
        full_position_interval_px=interval,
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


def transformed_edge(
    observation: BoundaryEdgeObservation,
    *,
    scale: float = 1.0,
    offset: float = 0.0,
) -> BoundaryEdgeObservation:
    def interval(value: FiniteInterval) -> FiniteInterval:
        return FiniteInterval(
            value.minimum * scale + offset,
            value.maximum * scale + offset,
        )

    return replace(
        observation,
        discovery_interval_px=interval(observation.discovery_interval_px),
        reference_trace_px=observation.reference_trace_px * scale,
        canonical_position_px=(
            observation.canonical_position_px * scale + offset
        ),
        fit_position_interval_px=interval(
            observation.fit_position_interval_px
        ),
        full_position_interval_px=interval(
            observation.full_position_interval_px
        ),
        trace_coordinates_px=tuple(
            int(round(value * scale))
            for value in observation.trace_coordinates_px
        ),
        fit_residual_px=observation.fit_residual_px * scale,
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
    *,
    region_count: int = 3,
) -> SeparatorBandObservation:
    material = tuple(
        SeparatorMaterialRegionObservation(
            region_index=index,
            sample_count=3,
            darkness_contrast_interval=FiniteInterval(1.0, 2.0),
            texture_contrast_interval=FiniteInterval(0.5, 1.0),
        )
        for index in range(region_count)
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
        independent_support_region_count=region_count,
        continuous_support_fraction=1.0,
        darkness_contrast=1.5,
        darkness_contrast_interval=FiniteInterval(1.0, 2.0),
        texture_contrast=0.75,
        texture_contrast_interval=FiniteInterval(0.5, 1.0),
        material_regions=material,
    )


class TemplatePhaseContractTest(unittest.TestCase):
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
            phase=100.0,
            width=100.0,
            pitch=120.0,
            direction=1,
            prefixes=(0.0,),
            frame_width=template.frame_width_px,
            fit_residual_limit_px=None,
        )

        self.assertEqual(matches, ())

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
        self.assertEqual(result.best.independent_support_count, 6)
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
            result.best.role_observation_ids[0],
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
            translated.best.role_observation_ids,
            base.best.role_observation_ids,
        )
        self.assertEqual(
            scaled.best.role_observation_ids,
            base.best.role_observation_ids,
        )
        for original, moved in zip(
            base.best.canonical_role_positions_px,
            translated.best.canonical_role_positions_px,
            strict=True,
        ):
            self.assertAlmostEqual(moved, original + 37.25)
        for original, resized in zip(
            base.best.canonical_role_positions_px,
            scaled.best.canonical_role_positions_px,
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
            result.best.canonical_role_positions_px[-2],
            phase + (count - 1) * pitch,
            places=9,
        )
        self.assertAlmostEqual(
            result.best.canonical_role_positions_px[-1],
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
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(result.best.phase_lattice_fit.integer_slot_offset, 0)
        self.assertEqual(result.best.inferred_role_indices[:2], (0, 1))
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
            narrowed.best.role_observation_ids,
            result.best.role_observation_ids,
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
            narrowed.best.canonical_role_positions_px,
            result.best.canonical_role_positions_px,
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
        self.assertEqual(result.best.independent_support_count, 6)

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
        self.assertEqual(result.best.independent_support_count, 6)

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
            result.best.role_observation_ids,
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
            result.best.role_observation_ids,
            (
                None,
                None,
                None,
                left.observation_id,
                right.observation_id,
                None,
            ),
        )
        self.assertEqual(len(result.best.direct_observation_ids), 2)
        self.assertEqual(result.best.independent_support_count, 1)
        self.assertEqual(
            result.best.independent_support_ids,
            (band.observation_id,),
        )
        self.assertAlmostEqual(result.best.independent_support_coverage, 0.2)

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
        self.assertIsNotNone(result.runner_up)
        assert result.runner_up is not None
        self.assertGreater(
            result.best.independent_support_count,
            result.runner_up.independent_support_count,
        )
        self.assertEqual(
            result.winner_basis,
            PhaseWinnerBasis.INDEPENDENT_SUPPORT,
        )
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

        self.assertIn(
            AnchorDependencyEffect.DISCRETE_SLOT_JUMP,
            tuple(item.effect for item in analysis.dependencies),
        )

    def test_leave_one_anchor_out_reports_continuous_shift(self) -> None:
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
            ),
        )

        self.assertIn(
            AnchorDependencyEffect.CONTINUOUS_SHIFT,
            tuple(item.effect for item in analysis.dependencies),
        )

    def test_leave_only_anchor_out_reports_unresolved(self) -> None:
        observations = (edge("only-anchor", 40.0),)
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
            analysis.dependencies[0].effect,
            AnchorDependencyEffect.UNRESOLVED_WITHOUT_ANCHOR,
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
                    result.best.canonical_role_positions_px,
                    result.runner_up.canonical_role_positions_px,
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
        positions = list(fit.canonical_role_positions_px)
        positions[2] += 2.0
        positions[3] += 2.0
        role_intervals = list(fit.role_positions_px)
        full_intervals = list(fit.role_full_position_intervals_px)
        for index in (2, 3):
            role_intervals[index] = FiniteInterval.exact(positions[index])
            full_intervals[index] = FiniteInterval.exact(positions[index])
        alternative_ids = (
            ObservationId("connected:alternate:start"),
            ObservationId("connected:alternate:end"),
        )
        role_ids = list(fit.role_observation_ids)
        original_ids = (role_ids[2], role_ids[3])
        role_ids[2:4] = alternative_ids
        direct_ids = tuple(
            alternative_ids[0]
            if identity == original_ids[0]
            else alternative_ids[1]
            if identity == original_ids[1]
            else identity
            for identity in fit.direct_observation_ids
        )
        alternative = replace(
            fit,
            canonical_role_positions_px=tuple(positions),
            role_positions_px=tuple(role_intervals),
            role_full_position_intervals_px=tuple(full_intervals),
            role_observation_ids=tuple(role_ids),
            direct_observation_ids=direct_ids,
        )
        first_support = ObservationId("separator-support:first")
        second_support = ObservationId("separator-support:second")
        connected = {
            original_ids[0]: first_support,
            alternative_ids[0]: first_support,
            original_ids[1]: second_support,
            alternative_ids[1]: second_support,
        }

        self.assertTrue(_same_continuous_placement(fit, alternative, connected))
        self.assertFalse(_same_continuous_placement(fit, alternative, {}))

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
        self.assertEqual(anomalies[0].relation_ordinal, 2)
        self.assertAlmostEqual(result.best.canonical_role_positions_px[4], 253.0)
        self.assertAlmostEqual(result.best.canonical_role_positions_px[5], 353.0)
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
        self.assertAlmostEqual(result.best.canonical_role_positions_px[2], 127.0)
        self.assertAlmostEqual(result.best.canonical_role_positions_px[4], 247.0)

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
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.role_observation_ids,
            tuple(item.observation_id for item in observations),
        )

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
            result.best.role_full_position_intervals_px[1],
            observations[1].full_position_interval_px,
        )
        self.assertLess(
            result.best.role_full_position_intervals_px[2].minimum,
            observations[2].full_position_interval_px.minimum,
        )

    def test_two_direct_gap_anomalies_exceed_the_bounded_model(self) -> None:
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
        self.assertEqual(analysis.pattern, ResidualPattern.UNRESOLVED)
        self.assertEqual(analysis.anomaly_ordinals, ())
        self.assertEqual(analysis.relations, ())
        self.assertIn("exceed bounded model", analysis.unresolved_reason or "")
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

    def test_repeated_gap_facts_within_normal_bleed_do_not_open_model(self) -> None:
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
        self.assertEqual(analysis.pattern, ResidualPattern.UNRESOLVED)
        self.assertEqual(analysis.relations, ())
        self.assertIn("exceed bounded model", analysis.unresolved_reason or "")
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
        self.assertEqual(result.best.local_advance_relations, ())

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
