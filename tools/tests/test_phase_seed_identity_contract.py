from __future__ import annotations

from dataclasses import replace
from itertools import permutations
import unittest
from unittest.mock import patch

from x5crop.detection.photo_geometry import (
    template_phase_candidate_model as candidate_model,
    template_phase_competition as phase_competition,
    template_phase_fitting as phase_fitting,
    template_phase_observations as phase_observations,
)
from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_template,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
)
from x5crop.domain import FiniteInterval, ObservationId


def anchor(name, coordinate, role):
    return replace(phase_edge(name, coordinate), qualified_anchor_roles=(role,))


class PhaseSeedIdentityContractTest(unittest.TestCase):
    def test_compatible_recipes_still_merge_before_fitting(self):
        observations = (
            anchor("a", 10, BoundaryRole.START),
            anchor("z", 110, BoundaryRole.END),
        )
        with patch.object(phase_fitting, "_fit_seed", wraps=phase_fitting._fit_seed) as fit:
            result = phase_competition.fit_template_phase(observations, phase_template(1))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(fit.call_count, 1)
        self.assertEqual(result.best.binding_observation_ids, ("a", "z"))
        result.receipt.validate_bounds()

    def test_equal_coordinates_do_not_erase_distinct_identities(self):
        observations = (
            anchor("a", 10, BoundaryRole.START),
            anchor("b", 10, BoundaryRole.START),
            anchor("z", 110, BoundaryRole.END),
        )
        for order in permutations(observations):
            with self.subTest(order=tuple(str(item.observation_id) for item in order)):
                with patch.object(phase_fitting, "_fit_seed", wraps=phase_fitting._fit_seed) as fit:
                    result = phase_competition.fit_template_phase(order, phase_template(1))
                self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
                self.assertEqual(
                    {result.best.binding_observation_ids, result.runner_up.binding_observation_ids},
                    {("a", "z"), ("b", "z")},
                )
                # Three generated recipes, no product of conflicting bindings.
                self.assertEqual(fit.call_count, 3)
                self.assertEqual(result.receipt.phase_hypothesis_count, 3)
                result.receipt.validate_bounds()

    def test_second_material_band_preserves_both_native_interpretations(self):
        start, end = BoundaryRole.START, BoundaryRole.END
        observations = (
            anchor("a", 10, start), anchor("e", 110, end),
            anchor("s", 130, start), anchor("t", 132, start),
            anchor("z", 230, end),
        )
        bands = (
            phase_separator("band", observations[1], observations[2], FiniteInterval.exact(20)),
            phase_separator("alternative", observations[1], observations[3], FiniteInterval(20, 22)),
        )
        for order in (bands, tuple(reversed(bands))):
            with self.subTest(bands=order):
                result = phase_competition.fit_template_phase(
                    observations, phase_template(2), separator_bands=order,
                )
                self.assertEqual(result.status, PhaseFitStatus.AMBIGUOUS)
                self.assertEqual(
                    {result.best.binding_observation_ids, result.runner_up.binding_observation_ids},
                    {("a", "e", "s", "z"), ("a", "e", "t", "z")},
                )
                self.assertLessEqual(result.receipt.phase_hypothesis_count, 5 * 6)
                result.receipt.validate_bounds()

    def test_raw_recipe_overflow_cannot_hide_in_one_geometric_bucket(self):
        observations = (
            anchor("a", 10, BoundaryRole.START),
            anchor("z", 110, BoundaryRole.END),
        )
        cap = len(observations) * 6
        recipes = tuple(
            candidate_model._PhaseSeed(10.0, 120.0, ((0, ObservationId(f"choice:{i}")),))
            for i in range(cap + 1)
        )
        with patch.object(phase_observations, "_separator_phase_seeds", return_value=recipes), \
                patch.object(phase_fitting, "_fit_seed", wraps=phase_fitting._fit_seed) as fit:
            result = phase_competition.fit_template_phase(observations, phase_template(1))
        self.assertEqual(result.status, PhaseFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.failure_kind, PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED)
        self.assertIsNone(result.best)
        self.assertIsNone(result.runner_up)
        self.assertEqual(fit.call_count, 0)
        self.assertEqual(result.receipt.phase_hypothesis_count, cap + 1)
        self.assertGreaterEqual(result.receipt.peak_temporary_bytes, cap * 2 * 32)

    def test_identical_generated_recipes_are_deduplicated_before_cap(self):
        observations = (
            anchor("a", 10, BoundaryRole.START),
            anchor("z", 110, BoundaryRole.END),
        )
        seed = candidate_model._PhaseSeed(10.0, 120.0, ((0, observations[0].observation_id),))
        with patch.object(phase_observations, "_separator_phase_seeds", return_value=(seed,) * 20):
            result = phase_competition.fit_template_phase(observations, phase_template(1))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(result.receipt.phase_hypothesis_count, 1)
        result.receipt.validate_bounds()

    def test_many_compatible_recipes_do_not_consume_fit_slots(self):
        observations = tuple(
            anchor(str(i), 10 + 120 * (i // 2) + (100 if i % 2 else 0),
                   BoundaryRole.END if i % 2 else BoundaryRole.START)
            for i in range(6)
        )
        bindings = tuple((i, item.observation_id) for i, item in enumerate(observations))
        recipes = tuple(
            candidate_model._PhaseSeed(
                10.0, 120.0,
                tuple(binding for i, binding in enumerate(bindings) if mask & (1 << i)),
            )
            for mask in range(1, 64)
        )
        with patch.object(phase_observations, "_separator_phase_seeds", return_value=recipes):
            result = phase_competition.fit_template_phase(observations, phase_template(3))
        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        self.assertEqual(result.best.binding_observation_ids, tuple(str(i) for i in range(6)))
        result.receipt.validate_bounds()

    def test_geometric_bucket_overflow_returns_no_prefix_fit(self):
        observations = (
            anchor("a", 10, BoundaryRole.START),
            anchor("z", 110, BoundaryRole.END),
        )
        cap = len(observations) * 6
        recipes = tuple(candidate_model._PhaseSeed(float(i), 120.0) for i in range(cap + 1))
        with patch.object(phase_observations, "_separator_phase_seeds", return_value=recipes), \
                patch.object(phase_fitting, "_fit_seed", wraps=phase_fitting._fit_seed) as fit:
            result = phase_competition.fit_template_phase(observations, phase_template(1))
        self.assertEqual(result.status, PhaseFitStatus.BOUND_EXCEEDED)
        self.assertIsNone(result.best)
        self.assertEqual(fit.call_count, 0)
