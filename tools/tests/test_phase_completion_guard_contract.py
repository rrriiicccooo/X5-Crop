"""Bounded phase completion must not manufacture a unique winner."""
from dataclasses import replace
from itertools import permutations
import unittest
from unittest.mock import patch

from tools.tests.template_test_support import phase_edge, phase_template
from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.detection.photo_geometry.model import BoundaryRole as R
from x5crop.detection.photo_geometry import template_phase as m
from x5crop.detection.photo_geometry.template_model import (
    LatticeParameterFitBasis, SequenceBindingUse,
)
from x5crop.detection.photo_geometry.template_nominal_grid_model import CalibratedNominalGridFitState
from x5crop.detection.photo_geometry.template_phase_candidates import _BoundFit, _clear_winner_basis


def full_fit(phase=10):
    observations = tuple(phase_edge(str(i), phase + 120*(i//2) + (100 if i%2 else 0)) for i in range(10))
    result = m.fit_template_phase(observations, phase_template(5))
    assert result.best is not None
    return result.best


def part(full, group, roles, local_roles=()):
    bindings = list(full.role_bindings)
    bindings[0] = replace(bindings[0], observation_id=ObservationId(group), evidence_group_id=ObservationId(group))
    bindings = tuple(
        replace(binding, use=SequenceBindingUse.LOCAL_REFINEMENT) if i in local_roles
        else binding if i in roles else None
        for i, binding in enumerate(bindings)
    )
    support = len({(i+1)//2 for i in roles if i not in local_roles})
    return _BoundFit(replace(full, role_bindings=bindings,
        contradicted_observation_count=12-sum(b is not None for b in bindings),
        phase_support_coverage=float(support), residual_sum_px=0.), True)


class CompletionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = full_fit()
        cls.shifted = full_fit(40)

    def test_eight_edge_full_owner_keeps_actual_discrete_competition(self):
        observations = tuple(replace(phase_edge(name, x), qualified_anchor_roles=(role,)) for name, x, role in (
            ('a',10,R.START), ('e',110,R.END), ('f',110,R.END), ('b',130,R.START),
            ('c',230,R.END), ('s',250,R.START), ('t',250,R.START), ('z',350,R.END)))
        fitted = []
        original = m._fit_seed
        def capture(*args, **kwargs):
            fit = original(*args, **kwargs)
            if fit is not None:
                fitted.append(fit)
            return fit
        with patch.object(m, '_fit_seed', side_effect=capture) as calls, \
                patch.object(m, '_unseparated_completion_competitor',
                             wraps=m._unseparated_completion_competitor) as guard:
            result = m.fit_template_phase(observations, phase_template(3))
        self.assertEqual(result.status.value, 'ambiguous')
        self.assertIsNone(result.winner_basis)
        self.assertIsNotNone(result.runner_up)
        self.assertEqual(calls.call_count, result.receipt.phase_hypothesis_count)
        self.assertLessEqual(calls.call_count, len(observations)*max(6, 6))
        guard.assert_called_once()
        candidate_count = len(guard.call_args.args[1])
        self.assertGreaterEqual(
            result.receipt.peak_temporary_bytes,
            calls.call_count * 6 * 32 + candidate_count * 6 * 64,
        )
        spine = next(x for x in fitted if x.fit.binding_observation_ids == ('a',None,'b','c',None,'z'))
        left = next(x for x in fitted if x.fit.binding_observation_ids == ('a','f','b','c',None,None))
        right = next(x for x in fitted if x.fit.binding_observation_ids == (None,None,'b','c','t','z'))
        alternative = m._merge_continuous_placement(m._merge_continuous_placement(spine, left), right)
        self.assertEqual(alternative.fit.phase_support_count, result.best.phase_support_count)
        self.assertIsNone(_clear_winner_basis(_BoundFit(result.best, True), alternative))

    def test_third_group_completion_cannot_be_hidden_by_runner_order(self):
        A = part(self.full, 'A', (0,1,3,5))
        A2 = part(self.full, 'A', (0,7))
        B = part(self.full, 'B', (0,1,3))
        C = part(self.full, 'C', (0,1,3))
        C2 = part(self.full, 'C', (0,5,7))
        C3 = part(self.full, 'C', (0,9))
        best = m._merge_continuous_placement(A, A2)
        third = m._merge_continuous_placement(m._merge_continuous_placement(C, C2), C3)
        self.assertEqual(best.fit.phase_support_count, 5)
        self.assertEqual(third.fit.phase_support_count, 6)
        self.assertIsNotNone(_clear_winner_basis(best, B))
        for records in permutations((A,B,C,C2,A2,C3)):
            index = m._unseparated_completion_competitor(best, records)
            self.assertIsNotNone(index)
            self.assertFalse(m._same_continuous_placement(best.fit, records[index].fit))

    def test_disconnected_dominated_component_can_still_lose(self):
        best = part(self.full, 'A', (0,1,3,5,7,9))
        B = part(self.shifted, 'B', (0,1))
        B2 = part(self.shifted, 'B', (0,3))
        self.assertEqual(best.fit.phase_lattice_fit.integer_slot_offset, B.fit.phase_lattice_fit.integer_slot_offset)
        self.assertLess(best.fit.phase_lattice_fit.absolute_phase_interval_px.maximum,
                        B.fit.phase_lattice_fit.absolute_phase_interval_px.minimum)
        for records in permutations((best,B,B2)):
            self.assertIsNone(m._unseparated_completion_competitor(best, records))

    def test_local_refinement_never_inflates_phase_support_upper_bound(self):
        best = part(self.full, 'A', (0,1,3,5))
        B = part(self.shifted, 'B', (0,1), local_roles=(3,5,7,9))
        B2 = part(self.shifted, 'B', (0,3), local_roles=(1,5,7,9))
        self.assertEqual(B.fit.phase_support_count, 2)
        self.assertEqual(B2.fit.phase_support_count, 2)
        self.assertIsNone(m._unseparated_completion_competitor(best, (best,B,B2)))

    def test_calibrated_state_is_hashable_and_part_of_identity(self):
        state = CalibratedNominalGridFitState('prior', PositiveInterval(1,1),
            FiniteInterval(100,100), FiniteInterval(120,120), 1.,
            (0,), (ObservationId('A'),), 1)
        self.assertIsInstance(hash(state), int)
        def calibrated(bound, prior):
            return replace(bound, fit=replace(bound.fit,
                lattice_parameter_fit_basis=LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID,
                calibrated_nominal_grid_fit_state=replace(state, prior_id=prior)))
        best = calibrated(part(self.full, 'A', (0,1,3,5,7)), 'best')
        B = calibrated(part(self.full, 'B', (0,1)), 'other')
        B2 = calibrated(part(self.full, 'B', (0,3)), 'other')
        self.assertIsNone(m._unseparated_completion_competitor(best, (best,B,B2)))

    def test_shared_bound_identity_cannot_lend_coverage_to_its_rival(self):
        def covered(group, roles, coverage):
            result = part(self.full, group, roles)
            return replace(result, fit=replace(result.fit, phase_support_coverage=coverage))
        best = covered('A', (0,1,3,5,7,9), 5.9)
        partial = covered('A', (0,1,3,5,7), 4.9)
        rival = covered('B', (0,1,3,5,7,9), 5.2)
        rival_partial = covered('B', (0,1,3,5,7), 4.2)
        self.assertIsNotNone(_clear_winner_basis(best, rival))
        for records in permutations((best, partial, rival, rival_partial)):
            self.assertIsNone(m._unseparated_completion_competitor(best, records))

    def test_disjoint_unbound_role_cannot_borrow_winner_support(self):
        def widened(bound):
            return replace(bound, fit=replace(
                bound.fit,
                phase_lattice_fit=replace(
                    bound.fit.phase_lattice_fit,
                    cycle_phase_interval_px=FiniteInterval(0, 60),
                    absolute_phase_interval_px=FiniteInterval(0, 60),
                ),
            ))
        best = widened(part(self.full, 'A', (0,1,3,5,7,9)))
        partial = widened(part(self.full, 'A', (0,1,3,5,7)))
        rival = widened(part(self.shifted, 'B', (1,3,5,7,9)))
        self.assertFalse(m._same_continuous_placement(best.fit, rival.fit))
        self.assertIsNotNone(_clear_winner_basis(best, rival))
        for records in permutations((best, partial, rival)):
            self.assertIsNone(m._unseparated_completion_competitor(best, records))

    def test_same_identity_hull_preserves_an_unbound_bridge(self):
        def partial(phase, roles):
            bound = part(full_fit(phase), 'A', roles)
            fit = bound.fit
            return replace(bound, fit=replace(
                fit,
                phase_lattice_fit=replace(
                    fit.phase_lattice_fit,
                    cycle_phase_interval_px=FiniteInterval(0, 60),
                    absolute_phase_interval_px=FiniteInterval(0, 60),
                ),
                model_full_role_intervals_px=(
                    fit.model_full_role_intervals_px[0],
                    *(FiniteInterval(0, 1000) for _ in range(9)),
                ),
            ))
        left = partial(10, (0,1,3))
        right = partial(40, (0,1,3))
        bridge = partial(25, (5,7,9))
        best = part(full_fit(150), 'D', (0,1,3,5,7))
        self.assertTrue(m._same_continuous_placement(left.fit, right.fit))
        self.assertFalse(m._same_continuous_placement(left.fit, bridge.fit))
        self.assertFalse(m._same_continuous_placement(right.fit, bridge.fit))
        merged = m._merge_continuous_placement(left, right)
        self.assertTrue(m._same_continuous_placement(merged.fit, bridge.fit))
        completed = m._merge_continuous_placement(merged, bridge)
        self.assertEqual(completed.fit.phase_support_count, 6)
        self.assertEqual(best.fit.phase_support_count, 5)
        for records in permutations((best, left, right, bridge)):
            self.assertIsNotNone(m._unseparated_completion_competitor(best, records))
