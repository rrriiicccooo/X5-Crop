from __future__ import annotations

from dataclasses import replace
import itertools
import math
import unittest

from scipy.optimize import linprog

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_family_membership import (
    MembershipAtom, MembershipFitBudget, MembershipReceipt, MembershipState,
    MembershipTransition, enumerate_membership_scope, new_membership_groups,
)


def _problem(groups, anchors, intervals=None):
    intervals = intervals or {}
    atoms = tuple(MembershipAtom(ObservationId(name), tuple(ObservationId(f'{name}:{trace}') for trace in traces),
                                 2 if name in anchors else 1) for name, traces in groups.items())
    raw = tuple(MembershipTransition(ObservationId(f'{name}:{trace}'), float(trace),
                                     FiniteInterval(*intervals.get((name, trace), (-1, 1))))
                for name, traces in groups.items() for trace in traces)
    return dict(parent_family_id='parent', role=BoundaryRole.TOP, atoms=atoms, transitions=raw,
                query_trace_positions_px=tuple(sorted({int(point.trace_coordinate_px) for point in raw})),
                scale_px_per_mm=1.0, remaining_visits=4096)


class TemplateFamilyMembershipContractTest(unittest.TestCase):
    def setUp(self):
        self.groups = {'A': (10, 20), 'B': (10, 30), 'C': (20, 30),
                       'D': (40, 50), 'E': (40, 60), 'F': (50, 60),
                       'H1': (70, 80), 'H2': (90, 100)}
        self.anchors = {'H1', 'H2'}

    @staticmethod
    def _lp_feasible(problem, names):
        identities = {identity for atom in problem['atoms'] if atom.observation_id in names
                      for identity in atom.transition_ids}
        points = [point for point in problem['transitions'] if point.transition_id in identities]
        if len({point.trace_coordinate_px for point in points}) != len(points):
            return False
        coefficients, limits = [], []
        for point in points:
            x = point.trace_coordinate_px
            coefficients.extend(((1, x), (-1, -x)))
            limits.extend((point.physical_position_interval_px.maximum + .1,
                           -(point.physical_position_interval_px.minimum - .1)))
        cap = math.tan(math.radians(4))
        return linprog([0, 0], A_ub=coefficients, b_ub=limits,
                       bounds=[(None, None), (-cap, cap)], method='highs').success

    def test_all_maximal_interpretations_match_independent_exhaustive_lp(self):
        problem = _problem(self.groups, self.anchors)
        variables = sorted(set(self.groups) - self.anchors)
        feasible = []
        for mask in range(1 << len(variables)):
            group = frozenset(self.anchors | {name for i, name in enumerate(variables) if mask & (1 << i)})
            if self._lp_feasible(problem, group):
                feasible.append(group)
        expected = {group for group in feasible if not any(group < other for other in feasible)}
        scope = enumerate_membership_scope(**problem)
        self.assertEqual(len(feasible), 16)
        self.assertEqual(len(expected), 9)
        self.assertEqual({frozenset(group) for group in scope.maximal_member_groups}, expected)
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        reversed_problem = _problem(dict(reversed(tuple(self.groups.items()))), self.anchors)
        self.assertEqual(enumerate_membership_scope(**reversed_problem), scope)
        self.assertGreater(scope.work.polygon_vertex_evaluation_count, 0)
        self.assertLessEqual(scope.work.maximality_extension_check_count,
                             scope.work.maximality_variable_visit_count)

    def test_exhaustion_never_exposes_a_search_prefix(self):
        problem = _problem(self.groups, self.anchors)
        scope = enumerate_membership_scope(**{**problem, 'remaining_visits': 8})
        self.assertEqual(scope.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(scope.work.visited_count, 8)
        self.assertEqual(scope.maximal_member_groups, ())
        empty = enumerate_membership_scope(**{**problem, 'remaining_visits': 0})
        self.assertEqual(empty.work.visited_count, 0)
        self.assertEqual(empty.maximal_member_groups, ())
        frozen = tuple(sorted(atom.observation_id for atom in problem['atoms']))
        with self.assertRaises(ValueError):
            MembershipReceipt(MembershipState.COMPLETE, (scope,), (), frozen)

    def test_shared_budget_exactly_exhausted_withholds_the_next_scope(self):
        problem = _problem({f'A{i:02}': (2 * i, 2 * i + 1) for i in range(12)}, {'A00'})
        first = enumerate_membership_scope(**problem)
        self.assertEqual(first.work.visited_count, 2048)
        second = enumerate_membership_scope(**{**problem, 'parent_family_id': 'second',
                                               'remaining_visits': 4096 - first.work.visited_count})
        self.assertEqual(second.work.visited_count, 2048)
        third = enumerate_membership_scope(**{**problem, 'parent_family_id': 'third', 'remaining_visits': 0})
        frozen = tuple(sorted(atom.observation_id for atom in problem['atoms']))
        receipt = MembershipReceipt(MembershipState.SEARCH_BOUND_EXCEEDED, (first, second, third), (), frozen)
        self.assertEqual(sum(scope.work.visited_count for scope in receipt.scopes), 4096)
        self.assertEqual(third.maximal_member_groups, ())

    def test_multiple_mandatory_anchors_need_a_joint_domain(self):
        groups = {'A': (0, 10), 'B': (100, 110), 'C': (50, 60)}
        intervals = {('A', 0): (0, 1), ('A', 10): (-100, 100), ('B', 100): (0, 1),
                     ('B', 110): (-100, 100), ('C', 50): (-1, -.3), ('C', 60): (-100, 100)}
        problem = _problem(groups, groups, intervals)
        self.assertTrue(all(self._lp_feasible(problem, pair) for pair in itertools.combinations(groups, 2)))
        self.assertFalse(self._lp_feasible(problem, groups))
        scope = enumerate_membership_scope(**problem)
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.maximal_member_groups, ())

    def test_closed_point_intersection_is_not_discarded(self):
        problem = _problem({'A': (0, 100), 'B': (40, 60)}, {'A'},
                           {('A', 0): (-.1, -.1), ('A', 100): (-.1, -.1),
                            ('B', 40): (.1, .1), ('B', 60): (.1, .1)})
        scope = enumerate_membership_scope(**problem)
        self.assertEqual(scope.maximal_member_groups, ((ObservationId('A'), ObservationId('B')),))

    def test_no_anchor_is_ineligible_without_spending_search_work(self):
        scope = enumerate_membership_scope(**_problem(self.groups, ()))
        self.assertEqual(scope.state, MembershipState.NO_INDEPENDENT_ANCHOR)
        self.assertEqual(scope.work.visited_count, 0)

    def test_fit_preflight_uses_every_new_union_before_any_fit(self):
        budget = MembershipFitBudget(BoundaryRole.TOP, 10, 8, 7, 12)
        self.assertTrue(budget.admits_all)
        self.assertFalse(replace(budget, additional_union_count=13).admits_all)
        self.assertFalse(replace(budget, original_family_fit_count=7,
                                 original_constrained_fit_count=9).admits_all)

    def test_same_union_preserves_distinct_members_and_parent_provenance(self):
        problem = _problem({'A': (0, 100), 'B': (40, 60)}, {'A'})
        scope = enumerate_membership_scope(**problem)
        atoms = {atom.observation_id: atom for atom in problem['atoms']}
        atoms[ObservationId('C')] = replace(atoms[ObservationId('B')], observation_id=ObservationId('C'))
        scope = replace(scope, atom_count=3, maximal_member_groups=(
            (ObservationId('A'), ObservationId('B')), (ObservationId('A'), ObservationId('C'))))
        groups = new_membership_groups((scope, replace(scope, parent_family_id='another')), atoms, set())
        self.assertEqual(len(groups), 2)
        self.assertEqual(len({(role, union) for role, _members, union in groups}), 1)
        self.assertTrue(all(parents == ('another', 'parent') for parents in groups.values()))
        existing = {(role, union) for role, _members, union in groups}
        self.assertEqual(new_membership_groups((scope,), atoms, existing), {})


if __name__ == '__main__':
    unittest.main()
