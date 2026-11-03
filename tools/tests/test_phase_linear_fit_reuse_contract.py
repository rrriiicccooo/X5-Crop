from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.test_phase_matching_index_contract import matching_fixture
from tools.tests.template_test_support import phase_edge, phase_template
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.detection.photo_geometry import template_phase_fitting as fitting
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_model import (
    MAX_PHASE_LATTICE_FIT_CACHE_ENTRIES,
    SeparatorRelation, SeparatorRelationKind,
    phase_lattice_fit_cache_bytes,
)


class PhaseLinearFitReuseContractTest(unittest.TestCase):
    def setUp(self):
        self.template, self.observations, self.direct = matching_fixture()
        self.index = fitting._PhaseMatchingIndex(self.direct, self.template.roles, ())
        self.prepared = fitting._PhaseLinearFitPreparation(self.index)
        self.matches = tuple(zip(self.template.roles, self.direct, strict=True))
        self.arguments = dict(width=100.0, pitch=120.0, direction=1, relations=(),
            width_authority=PositiveInterval(98, 102),
            pitch_authority=FiniteInterval(118, 122),
            gap_authority=FiniteInterval(18, 22), phase_authority=None)

    def test_complete_and_low_rank_results_equal_independent_solves(self):
        for matches in (self.matches, self.matches[::2]):
            with self.subTest(matches=len(matches)):
                expected = fitting._linear_fit(matches, **self.arguments)
                with patch.object(fitting, '_linear_fit', wraps=fitting._linear_fit) as solve:
                    self.assertEqual(self.prepared.fit(matches, **self.arguments), expected)
                    self.assertEqual(self.prepared.fit(matches, **self.arguments), expected)
                solve.assert_called_once()
        self.assertEqual(self.prepared.lookup_count, 4)
        self.assertEqual(self.prepared.evaluation_count, 2)
        self.assertEqual(self.prepared.reuse_count, 2)
        self.assertEqual(self.prepared.peak_temporary_bytes,
            phase_lattice_fit_cache_bytes(len(self.template.roles), 2))

    def test_each_numerical_input_and_row_order_remains_independent(self):
        nominal = SeparatorRelation(1, SeparatorRelationKind.NOMINAL,
                                   FiniteInterval.exact(0), 0.0)
        variants = (
            {}, dict(width=101.0), dict(pitch=121.0), dict(direction=-1),
            dict(relations=(nominal,)), dict(width_authority=PositiveInterval(99, 102)),
            dict(pitch_authority=FiniteInterval(119, 122)),
            dict(gap_authority=FiniteInterval(19, 22)),
            dict(phase_authority=FiniteInterval(495, 505)),
        )
        with patch.object(fitting, '_linear_fit', wraps=fitting._linear_fit) as solve:
            for variant in variants:
                arguments = self.arguments | variant
                self.prepared.fit(self.matches[::2], **arguments)
            self.prepared.fit(tuple(reversed(self.matches[::2])), **self.arguments)
        self.assertEqual(solve.call_count, len(variants) + 1)
        original = self.prepared.fit(self.matches[::2], **self.arguments)
        changed = self.prepared.fit(self.matches[::2], **(self.arguments | dict(pitch=121.0)))
        self.assertNotEqual(original, changed)

    def test_same_identity_cannot_substitute_a_different_fact(self):
        changed = replace(self.direct[0], interval_px=FiniteInterval.exact(510))
        with self.assertRaisesRegex(ValueError, 'different input'):
            self.prepared.fit(((self.template.roles[0], changed),), **self.arguments)
        self.assertEqual(self.prepared.lookup_count, 0)
        other = fitting._PhaseLinearFitPreparation(self.index)
        with patch.object(fitting, '_linear_fit', wraps=fitting._linear_fit) as solve:
            self.prepared.fit(self.matches, **self.arguments)
            other.fit(self.matches, **self.arguments)
        self.assertEqual(solve.call_count, 2)

    def test_eviction_and_failed_solve_do_not_change_results_or_exceed_capacity(self):
        with patch.object(fitting, '_linear_fit', side_effect=ValueError('failed')):
            with self.assertRaisesRegex(ValueError, 'failed'):
                self.prepared.fit(self.matches, **self.arguments)
        self.assertEqual(self.prepared._results, {})
        for offset in range(MAX_PHASE_LATTICE_FIT_CACHE_ENTRIES + 1):
            arguments = self.arguments | dict(width=100.0 + offset)
            self.assertEqual(self.prepared.fit(self.matches[::2], **arguments),
                             fitting._linear_fit(self.matches[::2], **arguments))
        with patch.object(fitting, '_linear_fit', wraps=fitting._linear_fit) as solve:
            self.prepared.fit(self.matches[::2], **self.arguments)
        solve.assert_called_once()
        self.assertEqual(self.prepared.peak_entry_count, MAX_PHASE_LATTICE_FIT_CACHE_ENTRIES)
        self.assertEqual(len(self.prepared._results), MAX_PHASE_LATTICE_FIT_CACHE_ENTRIES)
        self.prepared.clear()
        self.assertEqual(self.prepared._results, {})

    def test_competition_preserves_every_candidate_and_releases_cache_on_all_paths(self):
        template = replace(phase_template(2), frame_width_px=PositiveInterval(97, 103),
                           pitch_px=PositiveInterval(116, 124))
        observations = tuple(replace(phase_edge(str(index), coordinate),
            qualified_anchor_roles=(BoundaryRole.START if index % 2 == 0 else BoundaryRole.END,))
            for index, coordinate in enumerate((499.75, 600.5, 619.75, 719.75)))
        original = fitting._PhaseLinearFitPreparation.fit
        def uncached(prepared, *args, **kwargs):
            prepared.clear()
            return original(prepared, *args, **kwargs)
        with patch.object(fitting._PhaseLinearFitPreparation, 'fit', uncached):
            independent = fit_template_phase(observations, template)
        contexts = []
        factory = fitting._PhaseLinearFitPreparation
        def capture(index):
            value = factory(index)
            contexts.append(value)
            return value
        with patch.object(fitting, '_PhaseLinearFitPreparation', side_effect=capture):
            result = fit_template_phase(observations, template)
        self.assertEqual(result.best, independent.best)
        self.assertEqual(result.runner_up, independent.runner_up)
        self.assertEqual(result.status, independent.status)
        self.assertEqual(
            tuple((member.input_fit, member.projected_fit) for scope in result.competition_scopes for member in scope.members),
            tuple((member.input_fit, member.projected_fit) for scope in independent.competition_scopes for member in scope.members))
        self.assertGreater(result.receipt.lattice_fit_reuse_count, 0)
        self.assertLess(result.receipt.lattice_fit_evaluation_count,
                        independent.receipt.lattice_fit_evaluation_count)
        self.assertTrue(all(not value._results for value in contexts))
        def capture_populated(index):
            value = capture(index)
            value.fit(tuple(zip(index.roles, index.direct, strict=True)), **self.arguments)
            self.assertTrue(value._results)
            return value
        with patch.object(fitting, '_PhaseLinearFitPreparation', side_effect=capture_populated), patch.object(
            fitting, '_fit_seed', side_effect=ValueError('candidate failure')):
            with self.assertRaisesRegex(ValueError, 'candidate failure'):
                fit_template_phase(self.observations, self.template)
        self.assertTrue(all(not value._results for value in contexts))

    def test_reservation_is_checked_before_any_key_is_retained(self):
        oversized = fitting._PhaseMatchingIndex(self.direct, self.template.roles * 3000, ())
        with self.assertRaisesRegex(ValueError, 'original source memory allowance'):
            fitting._PhaseLinearFitPreparation(oversized)

    def test_work_rejects_forged_counts_and_missing_memory(self):
        result = fit_template_phase(self.observations, self.template)
        receipt = result.receipt
        for changes in (
            dict(lattice_fit_lookup_count=receipt.lattice_fit_lookup_count + 1),
            dict(lattice_fit_cache_peak_entry_count=0),
            dict(lattice_fit_cache_peak_entry_count=MAX_PHASE_LATTICE_FIT_CACHE_ENTRIES + 1),
            dict(peak_temporary_bytes=0),
            dict(lattice_fit_reuse_count=True),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'lattice-fit'):
                replace(receipt, **changes)


if __name__ == '__main__':
    unittest.main()
