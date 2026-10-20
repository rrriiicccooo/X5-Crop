from __future__ import annotations

from dataclasses import replace
import itertools
import math
import random
import unittest

from scipy.optimize import linprog

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_family_membership import (
    MembershipAtom, MembershipFitBudget, MembershipReceipt, MembershipState,
    MembershipTransition, enumerate_membership_scope, new_membership_groups,
)
from tools.tests.cross_fixture_support import _problem


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

    def test_deterministic_small_scopes_match_independent_exhaustive_lp(self):
        random_source = random.Random(210024)
        for case in range(8):
            groups = {'H': (100, 110), **{
                f'A{index}': tuple(sorted(random_source.sample(range(12), 2))) for index in range(6)
            }}
            intervals = {('H', trace): (-10, 10) for trace in groups['H']}
            for name, traces in groups.items():
                if name == 'H':
                    continue
                for trace in traces:
                    center = random_source.choice((-1.0, -.25, 0.0, .25, 1.0))
                    half_width = random_source.choice((0.0, .2, 1.0))
                    intervals[name, trace] = (center - half_width, center + half_width)
            problem = _problem(groups, {'H'}, intervals)
            variables = sorted(set(groups) - {'H'})
            feasible = []
            for mask in range(1 << len(variables)):
                group = frozenset({'H'} | {name for index, name in enumerate(variables) if mask & (1 << index)})
                if self._lp_feasible(problem, group):
                    feasible.append(group)
            expected = {group for group in feasible if not any(group < other for other in feasible)}
            with self.subTest(case=case):
                scope = enumerate_membership_scope(**problem)
                self.assertEqual(scope.state, MembershipState.COMPLETE)
                self.assertEqual({frozenset(group) for group in scope.maximal_member_groups}, expected)
                self.assertEqual(enumerate_membership_scope(**{
                    **problem, 'atoms': problem['atoms'][::-1], 'transitions': problem['transitions'][::-1],
                }), scope)

    def test_large_compatible_union_closes_without_enumerating_subsets(self):
        groups = {f'A{index:03}': (2 * index, 2 * index + 1) for index in range(64)}
        scope = enumerate_membership_scope(**_problem(groups, {'A000'}))
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.maximal_member_groups, (tuple(map(ObservationId, sorted(groups))),))
        self.assertEqual(scope.work.visited_count, 65)
        self.assertEqual(scope.work.search_node_count, 1)
        self.assertEqual(scope.work.union_lookahead_count, 1)
        self.assertEqual(scope.work.search_branch_count, 0)
        self.assertEqual(scope.work.branch_filter_count, 0)

    def test_excluded_feasible_extension_prevents_a_nonmaximal_union(self):
        # A conflicts with B, B conflicts with C, but A and C jointly fit.
        # The exclude-A / exclude-B branch must not publish C by itself.
        problem = _problem({'H': (100, 110), 'A': (0, 10), 'B': (0, 20), 'C': (20, 30)}, {'H'})
        scope = enumerate_membership_scope(**problem)
        self.assertEqual(scope.maximal_member_groups, (
            (ObservationId('A'), ObservationId('C'), ObservationId('H')),
            (ObservationId('B'), ObservationId('H')),
        ))
        self.assertGreater(scope.work.maximality_extension_check_count, 0)
        self.assertEqual(scope.work.maximality_extension_check_count, scope.work.maximality_variable_visit_count)

    def test_full_raw_union_work_counts_overlapping_atoms(self):
        problem = _problem({'H': (0, 100), 'A': (40, 60)}, {'H'})
        original = problem['atoms'][1]
        atoms = (*problem['atoms'], *(replace(original, observation_id=ObservationId(name)) for name in ('B', 'C', 'D')))
        scope = enumerate_membership_scope(**{**problem, 'atoms': atoms})
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.work.raw_union_atom_visit_count, 14)
        self.assertEqual(scope.work.raw_union_input_count, 28)
        self.assertEqual(scope.maximal_member_groups, ((
            ObservationId('A'), ObservationId('B'), ObservationId('C'), ObservationId('D'), ObservationId('H'),
        ),))

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
        self.assertEqual(first.work.visited_count, 13)
        competing = _problem({'H': (1000, 1001), **{
            f'{name}{index:02}': (2 * index, 2 * index + 1) for index in range(12) for name in ('A', 'B')
        }}, {'H'})
        second = enumerate_membership_scope(**{**competing, 'parent_family_id': 'second',
                                                'remaining_visits': 4096 - first.work.visited_count})
        self.assertEqual(second.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(second.work.visited_count, 4083)
        self.assertEqual(second.maximal_member_groups, ())
        self.assertGreater(second.work.search_node_count, 1)
        self.assertGreater(second.work.maximality_extension_check_count, 0)
        third = enumerate_membership_scope(**{**problem, 'parent_family_id': 'third', 'remaining_visits': 0})
        frozen = tuple(sorted(atom.observation_id for atom in problem['atoms']))
        receipt = MembershipReceipt(MembershipState.SEARCH_BOUND_EXCEEDED, (first, second, third), (), frozen)
        self.assertEqual(sum(scope.work.visited_count for scope in receipt.scopes), 4096)
        self.assertEqual(third.maximal_member_groups, ())

    def test_exponential_real_competition_exhausts_the_unchanged_full_limit(self):
        # Each disjoint pair has two incompatible raw identities at the same
        # traces. Exactly 2**12 maximal interpretations exist; no ranking can
        # remove one to fit the unchanged 4096-oracle allowance.
        groups = {'H': (1000, 1001), **{
            f'{name}{index:02}': (2 * index, 2 * index + 1) for index in range(12) for name in ('A', 'B')
        }}
        scope = enumerate_membership_scope(**_problem(groups, {'H'}))
        self.assertEqual(scope.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(scope.work.visited_count, 4096)
        self.assertEqual(scope.maximal_member_groups, ())
        self.assertGreater(scope.work.maximality_extension_check_count, 0)
        self.assertEqual(enumerate_membership_scope(**_problem(dict(reversed(tuple(groups.items()))), {'H'})), scope)

    def test_exact_compatible_search_budget_and_work_ledger(self):
        problem = _problem({f'A{i:02}': (2 * i, 2 * i + 1) for i in range(12)}, {'A00'})
        complete = enumerate_membership_scope(**{**problem, 'remaining_visits': 13})
        exhausted = enumerate_membership_scope(**{**problem, 'remaining_visits': 12})
        self.assertEqual(complete.state, MembershipState.COMPLETE)
        self.assertEqual(exhausted.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(exhausted.work.visited_count, 12)
        self.assertEqual(exhausted.work.search_node_count, 1)
        self.assertEqual(exhausted.work.union_lookahead_count, 0)
        self.assertEqual(exhausted.maximal_member_groups, ())
        with self.assertRaises(ValueError):
            replace(complete.work, initial_filter_count=complete.work.initial_filter_count - 1)
        with self.assertRaises(ValueError):
            replace(complete, work=replace(complete.work, search_node_count=2))
        with self.assertRaises(ValueError):
            replace(complete, work=replace(complete.work, raw_union_atom_visit_count=13 * 12 + 1))

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

    def test_pairwise_compatible_variables_do_not_replace_the_joint_domain(self):
        groups = {'H': (-20, -10), 'A': (0, 10), 'B': (100, 110), 'C': (50, 60)}
        intervals = {('H', trace): (-100, 100) for trace in groups['H']}
        intervals.update({('A', 0): (0, 1), ('A', 10): (-100, 100), ('B', 100): (0, 1),
                          ('B', 110): (-100, 100), ('C', 50): (-1, -.3), ('C', 60): (-100, 100)})
        problem = _problem(groups, {'H'}, intervals)
        expected = {frozenset(('H', *pair)) for pair in itertools.combinations(('A', 'B', 'C'), 2)}
        self.assertTrue(all(self._lp_feasible(problem, group) for group in expected))
        self.assertFalse(self._lp_feasible(problem, groups))
        scope = enumerate_membership_scope(**problem)
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual({frozenset(group) for group in scope.maximal_member_groups}, expected)

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
        same_union = replace(scope, maximal_member_groups=((ObservationId('A'), ObservationId('C')),))
        scopes = tuple(replace(item, parent_family_id=parent) for item in (scope, same_union)
                       for parent in ('parent', 'another'))
        groups = new_membership_groups(scopes, atoms, set())
        self.assertEqual(len(groups), 2)
        self.assertEqual(len({(role, union) for role, _members, union in groups}), 1)
        self.assertTrue(all(parents == ('another', 'parent') for parents in groups.values()))
        existing = {(role, union) for role, _members, union in groups}
        self.assertEqual(new_membership_groups(scopes, atoms, existing), {})


if __name__ == '__main__':
    unittest.main()
