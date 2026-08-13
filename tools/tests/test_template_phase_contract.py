from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.template_model import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    PhaseAuthority,
    TemplateSearchReceipt,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import (
    PhaseFitStatus,
    fit_template_phase,
)
from x5crop.detection.photo_geometry.template_work import validate_template_work
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
    )


def template(
    count: int,
    authority: PhaseAuthority = PhaseAuthority.PARTIAL_FREE,
) -> TemplateSpec:
    return TemplateSpec(
        template_id="test-template",
        frame_width_px=100.0,
        pitch_px=120.0,
        count=count,
        phase_authority=authority,
        nominal_gap_px=20.0,
    )


class TemplatePhaseContractTest(unittest.TestCase):
    def test_full_centered_regular_sequence(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((80.0, 180.0, 200.0, 300.0, 320.0, 420.0))
        )
        result = fit_template_phase(
            observations,
            template(3, PhaseAuthority.FULL_CENTERED),
            holder_span_px=FiniteInterval(0.0, 500.0),
        )
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertAlmostEqual(result.best.canonical_phase_px, 80.0)
        self.assertEqual(result.best.support_count, 6)
        self.assertEqual(result.best.inferred_role_indices, ())

    def test_partial_free_phase_does_not_consume_centered_authority(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((35.0, 135.0, 155.0, 255.0, 275.0, 375.0))
        )
        result = fit_template_phase(observations, template(3))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertAlmostEqual(result.best.canonical_phase_px, 35.0)

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
        self.assertAlmostEqual(result.best.canonical_phase_px, 40.0)
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

    def test_close_runner_up_is_ambiguous(self) -> None:
        observations = tuple(
            edge(f"edge:{index}", coordinate)
            for index, coordinate in enumerate((40.0, 140.0, 200.0, 300.0))
        )
        result = fit_template_phase(observations, template(2))
        self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
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

    def test_bound_overflow_is_explicit_and_receipt_cannot_be_overstated(self) -> None:
        result = fit_template_phase(
            (edge("edge:0", 10.0), edge("edge:1", 110.0)),
            template(1),
            max_observations=1,
        )
        self.assertEqual(result.status, PhaseFitStatus.BOUND_EXCEEDED)
        with self.assertRaises(ValueError):
            validate_template_work(
                replace(result.receipt, phase_lookup_count=13),
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
            direct_observation_count=2,
            inferred_role_count=0,
        )
        validate_template_work(
            receipt,
            observation_count=2,
            role_count=2,
            slot_count=1,
        )


if __name__ == "__main__":
    unittest.main()
