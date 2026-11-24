from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
import itertools
import math
import random
import sys
import unittest
from unittest.mock import patch

from scipy.optimize import linprog

from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_family_membership import (
    MembershipAtom, MembershipFitBudget, MembershipReceipt, MembershipState, MembershipIdentityPrecheckState,
    MembershipTransition, enumerate_membership_scope, new_membership_groups,
)
from x5crop.detection.photo_geometry import template_family_membership as membership
from tools.tests.cross_fixture_support import _problem


def _sample_membership_working_memory(problem, retained_scopes=()):
    """Independent live-object sampling with explicit borrowed input boundary."""
    borrowed = set()
    def borrow(value):
        if id(value) in borrowed:
            return
        borrowed.add(id(value))
        if isinstance(value, dict):
            for key, item in value.items():
                borrow(key)
                borrow(item)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                borrow(item)
        elif is_dataclass(value):
            if hasattr(value, '__dict__'):
                borrowed.add(id(value.__dict__))
            for field in fields(value):
                borrow(getattr(value, field.name))
    borrow(problem)

    def live_bytes(*roots):
        seen = set()
        def walk(value):
            # Strings are source identities or module constants. Source
            # dataclasses/floats are borrowed; newly made floats, integers,
            # intervals and their instance dicts are counted below.
            if id(value) in seen or id(value) in borrowed or isinstance(value, str) or callable(value):
                return 0
            seen.add(id(value))
            size = sys.getsizeof(value)
            if isinstance(value, dict):
                return size + sum(walk(key) + walk(item) for key, item in value.items())
            if isinstance(value, (list, tuple, set, frozenset)):
                return size + sum(map(walk, value))
            if is_dataclass(value) and hasattr(value, '__dict__'):
                return size + walk(value.__dict__)
            return size
        return sum(map(walk, roots))

    peaks = dict(working_bytes=0, dfs_bytes=0, oracle_bytes=0, depth=0,
                 interval_count=0, clip_vertices=0, clip_coexisting_old_new_samples=0,
                 maximal_temporary_bytes=0, returned_scope_bytes=0,
                 maximal_raw_group_count=0, prior_retained_bytes=live_bytes(*retained_scopes))
    owner_files = {membership.__file__, membership.physical_line_region.__code__.co_filename}
    def inspect(frame, event, result):
        if frame.f_code.co_filename not in owner_files:
            return inspect
        name, values = frame.f_code.co_name, frame.f_locals
        deep = name == 'search' and event == 'call' and values['depth'] > peaks['depth']
        clip = name == '_clip_line_region' and event == 'return' and (
            len(values.get('vertices', ())) > peaks['clip_vertices'])
        physical = name == 'physical_line_region_in_slopes' and event == 'return' and (
            len(values['trace_intervals']) > peaks['interval_count'])
        finishing = (name == '__post_init__' and event == 'call'
                     and isinstance(values.get('self'), membership.MembershipScope))
        if not (deep or clip or physical or finishing):
            return inspect
        chain = []
        current = frame
        while current is not None:
            chain.append(current)
            if current.f_code.co_name == 'enumerate_membership_scope':
                break
            current = current.f_back
        # Python 3.13+ may expose FrameLocalsProxy instead of dict. Materialize
        # and include a dict so the sampler traverses every referenced object;
        # this extra observation container makes the measured envelope larger.
        all_roots = [item for current in chain for item in (current, dict(current.f_locals))]
        all_roots.extend(retained_scopes)
        if event == 'return':
            all_roots.append(result)
        peaks['working_bytes'] = max(peaks['working_bytes'], live_bytes(*all_roots))
        search_roots = [item for current in chain if current.f_code.co_name == 'search'
                        for item in (current, dict(current.f_locals))]
        peaks['dfs_bytes'] = max(peaks['dfs_bytes'], live_bytes(*search_roots))
        if deep:
            peaks['depth'] = values['depth']
        if clip or physical:
            physical_roots = []
            for current in chain:
                current_name, locals_ = current.f_code.co_name, current.f_locals
                if current_name == 'feasible':
                    physical_roots.extend(locals_[key] for key in ('selected', 'inputs', 'identities', 'intervals')
                                          if key in locals_)
                elif current_name in ('_clip_line_region', 'physical_line_region', 'physical_line_region_in_slopes'):
                    physical_roots.extend((current, dict(locals_)))
                if current_name == 'physical_line_region_in_slopes':
                    peaks['interval_count'] = max(peaks['interval_count'], len(locals_['trace_intervals']))
            if event == 'return':
                physical_roots.append(result)
            peaks['oracle_bytes'] = max(peaks['oracle_bytes'], live_bytes(*physical_roots))
        if clip:
            peaks['clip_vertices'] = len(values['vertices'])
            if values.get('result') and isinstance(result, tuple) and result is not values['vertices']:
                # The old vertices, new mutable result and returned tuple
                # are all reachable in this one sampling event.
                peaks['clip_coexisting_old_new_samples'] += 1
        if finishing:
            groups = values['self'].maximal_member_groups
            maximal = chain[-1].f_locals['maximal']
            peaks['maximal_raw_group_count'] = len(maximal)
            # Deliberately retain all the native sort/validation containers
            # together. This is a conservative independently sized envelope
            # of their phases, beyond the actual traced live-object peak.
            peaks['maximal_temporary_bytes'] = live_bytes(maximal, groups, sorted(maximal), set(groups))
        return inspect

    previous = sys.gettrace()
    sys.settrace(inspect)
    try:
        scope = enumerate_membership_scope(**problem)
    finally:
        sys.settrace(previous)
    peaks['returned_scope_bytes'] = live_bytes(scope)
    return scope, peaks


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
        self.assertGreater(scope.work.maximality_variable_visit_count, 0)
        self.assertEqual(
            scope.work.maximality_variable_visit_count,
            scope.work.maximality_extension_check_count
            + scope.work.maximality_extension_reuse_count,
        )

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
        self.assertGreaterEqual(empty.cache_temporary_bytes, empty.identity_plan.base_working_temporary_bytes + 256)
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
            'remaining_visits': 4096 - first.work.visited_count,
            'retained_scope_prefix_bytes': first.retained_bytes})
        self.assertEqual(second.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(second.work.visited_count, 4083)
        self.assertEqual(second.maximal_member_groups, ())
        self.assertGreater(second.work.search_node_count, 1)
        self.assertGreater(second.work.maximality_identity_reject_count, 0)
        third = enumerate_membership_scope(**{**problem, 'parent_family_id': 'third', 'remaining_visits': 0,
            'retained_scope_prefix_bytes': first.retained_bytes + second.retained_bytes})
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
        self.assertGreater(scope.work.maximality_identity_reject_count, 0)
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

    def test_exact_filtered_union_reuses_its_own_proof_at_the_visit_limit(self):
        problem = _problem({'H': (0, 100), 'A': (40, 60)}, {'H'})
        scope = enumerate_membership_scope(**{**problem, 'remaining_visits': 2})
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.maximal_member_groups, ((ObservationId('A'), ObservationId('H')),))
        self.assertEqual(scope.work.visited_count, 2)
        self.assertEqual(scope.work.union_lookahead_count, 0)
        self.assertEqual(scope.work.union_lookahead_reuse_count, 1)
        exhausted = enumerate_membership_scope(**{**problem, 'remaining_visits': 1})
        self.assertEqual(exhausted.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(exhausted.maximal_member_groups, ())
        with self.assertRaises(ValueError):
            replace(scope, work=replace(scope.work, union_lookahead_reuse_count=0))

    def test_scope_local_mask_cache_reuses_true_and_false_with_purpose_ledger(self):
        groups = {'H': (100, 110), 'A': (0, 10), 'B': (0, 20), 'C': (20, 30)}
        problem = _problem(groups, {'H'})
        scope = enumerate_membership_scope(**problem)
        variables = sorted(set(groups) - {'H'})
        feasible = []
        for mask in range(1 << len(variables)):
            group = frozenset({'H'} | {
                name for index, name in enumerate(variables) if mask & (1 << index)
            })
            if self._lp_feasible(problem, group):
                feasible.append(group)
        expected = {
            group for group in feasible
            if not any(group < other for other in feasible)
        }
        self.assertEqual({frozenset(group) for group in scope.maximal_member_groups}, expected)
        work = scope.work
        self.assertGreater(work.cached_feasible_reuse_count, 0)
        self.assertGreater(work.cached_infeasible_reuse_count, 0)
        self.assertEqual(
            work.feasibility_lookup_count,
            work.visited_count + work.cached_feasible_reuse_count
            + work.cached_infeasible_reuse_count + work.identity_reject_count,
        )
        self.assertEqual(
            work.cached_feasible_reuse_count + work.cached_infeasible_reuse_count,
            work.initial_filter_reuse_count + work.branch_filter_reuse_count
            + work.maximality_extension_reuse_count,
        )
        self.assertLessEqual(
            work.initial_filter_count + work.initial_filter_reuse_count,
            scope.atom_count - len(scope.anchor_observation_ids),
        )
        self.assertLessEqual(
            work.branch_filter_count + work.branch_filter_reuse_count,
            scope.atom_count * work.search_branch_count,
        )

        changed = enumerate_membership_scope(**_problem(
            groups, {'H'},
            {('A', 0): (999, 1000), ('A', 10): (999, 1000)},
        ))
        self.assertEqual(changed.work.cached_feasible_reuse_count, 0)
        self.assertTrue(all(ObservationId("A") not in group
                            for group in changed.maximal_member_groups))
        self.assertGreater(changed.work.cache_peak_entry_count, 0)
        self.assertEqual(
            scope.cache_temporary_bytes,
            scope.identity_plan.base_working_temporary_bytes
            + membership._maximal_working_bytes(scope.atom_count, scope.work.search_branch_count + 1)
            + scope.identity_plan.index_planned_retained_bytes
            + max(scope.identity_plan.index_planned_build_temporary_bytes,
                  scope.identity_plan.precheck_planned_temporary_bytes
                  + 256 + scope.work.cache_peak_entry_count
                  * (192 + 8 * ((scope.atom_count + 29) // 30))),
        )
        no_anchor = enumerate_membership_scope(**_problem(self.groups, set()))
        self.assertEqual(no_anchor.cache_temporary_bytes, no_anchor.identity_plan.base_working_temporary_bytes)
        with self.assertRaises(ValueError):
            replace(scope, work=replace(work, feasibility_lookup_count=work.feasibility_lookup_count + 1))
        with self.assertRaises(ValueError):
            replace(scope, work=replace(work, initial_filter_reuse_count=work.initial_filter_reuse_count + 1))
        with self.assertRaises(ValueError):
            replace(scope, work=replace(work, cached_feasible_reuse_count=work.cached_feasible_reuse_count + 1))
        with self.assertRaises(ValueError):
            replace(scope, work=replace(work, cache_peak_entry_count=0))

    def test_filtered_anchor_only_leaf_reuses_joint_anchor_proof(self):
        problem = _problem({'A': (0, 100), 'B': (40, 60)}, {'A', 'B'})
        scope = enumerate_membership_scope(**{**problem, 'remaining_visits': 1})
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.maximal_member_groups, ((ObservationId('A'), ObservationId('B')),))
        self.assertEqual(scope.work.visited_count, 1)
        self.assertEqual(scope.work.union_lookahead_reuse_count, 1)

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
        self.assertGreater(scope.work.input_transition_visit_count, 0)
        self.assertGreater(scope.work.input_raw_visit_count, 0)
        self.assertEqual(scope.identity_plan.state, MembershipIdentityPrecheckState.NO_INDEPENDENT_ANCHOR)
        self.assertEqual(scope.work.identity_index_raw_visit_count, 0)
        self.assertEqual(scope.work.identity_precheck_count, 0)

    def test_shared_raw_is_legal_and_exact_trace_identity_is_not_quantized(self):
        problem = _problem({'H': (0, 100), 'A': (40, 60)}, {'H'})
        atom = problem['atoms'][1]
        atoms = (*problem['atoms'], replace(atom, observation_id=ObservationId('B')))
        scope = enumerate_membership_scope(**{**problem, 'atoms': atoms})
        self.assertEqual(scope.maximal_member_groups, ((ObservationId('A'), ObservationId('B'), ObservationId('H')),))
        self.assertEqual(scope.work.identity_reject_count, 0)
        self.assertGreater(scope.work.identity_precheck_count, 0)
        near = _problem({'H': (0, 100), 'A': (40, 60), 'B': (40.000000000001, 61)}, {'H'})
        actual = enumerate_membership_scope(**near)
        self.assertEqual(actual.maximal_member_groups, ((ObservationId('A'), ObservationId('B'), ObservationId('H')),))

    def test_conflicting_initial_precheck_does_not_spend_actual_or_write_memo(self):
        problem = _problem({'H': (0, 100), 'A': (0, 60)}, {'H'})
        scope = enumerate_membership_scope(**{**problem, 'remaining_visits': 1})
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.maximal_member_groups, ((ObservationId('H'),),))
        self.assertEqual(scope.work.visited_count, 1)
        self.assertEqual(scope.work.initial_filter_count, 0)
        self.assertEqual(scope.work.initial_identity_reject_count, 1)
        self.assertEqual(scope.work.cache_peak_entry_count, 1)
        self.assertEqual(scope.work.search_branch_count, 0)

    def test_anchor_internal_identity_conflict_is_still_an_actual_check(self):
        problem = _problem({'H': (0, 100), 'A': (40, 60)}, {'H'})
        point = problem['transitions'][0]
        duplicate = replace(point, transition_id=ObservationId('anchor-conflict'))
        anchor = replace(problem['atoms'][0], transition_ids=(*problem['atoms'][0].transition_ids, duplicate.transition_id))
        scope = enumerate_membership_scope(**{**problem, 'atoms': (anchor, problem['atoms'][1]),
            'transitions': (*problem['transitions'], duplicate)})
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.maximal_member_groups, ())
        self.assertEqual(scope.work.anchor_check_count, 1)
        self.assertEqual(scope.work.trace_conflict_count, 1)
        self.assertEqual(scope.work.identity_precheck_count, 0)
        self.assertEqual(scope.work.cache_peak_entry_count, 1)

    def test_true_whole_union_conflict_still_spends_actual_work_and_creates_the_branch(self):
        problem = _problem({'H': (100, 110), 'A': (0, 10), 'B': (0, 20)}, {'H'})
        scope = enumerate_membership_scope(**problem)
        self.assertEqual(scope.work.visited_count, 4)
        self.assertEqual(scope.work.union_lookahead_count, 1)
        self.assertEqual(scope.work.trace_conflict_count, 1)
        self.assertEqual(scope.work.search_branch_count, 1)
        # The same failed whole mask is already a completed physical memo
        # entry. Filter lookup must reuse it before trying the new precheck.
        self.assertGreater(scope.work.branch_filter_reuse_count, 0)
        self.assertEqual(scope.work.identity_reject_count, 0)
        self.assertEqual(scope.work.branch_filter_count, 0)
        self.assertEqual(scope.maximal_member_groups, ((ObservationId('A'), ObservationId('H')),
                                                     (ObservationId('B'), ObservationId('H'))))

    def test_precheck_pass_after_actual_budget_exhaustion_has_one_unfinished_lookup(self):
        problem = _problem({'H': (0, 100), 'A': (40, 60)}, {'H'})
        scope = enumerate_membership_scope(**{**problem, 'remaining_visits': 1})
        self.assertEqual(scope.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(scope.work.identity_precheck_count, 1)
        self.assertEqual(scope.work.identity_reject_count, 0)
        self.assertEqual(scope.work.identity_precheck_pass_without_actual_count, 1)
        self.assertEqual(scope.work.visited_count, 1)
        self.assertEqual(scope.work.cache_peak_entry_count, 1)
        self.assertEqual(scope.work.feasibility_lookup_count, 2)
        self.assertEqual(scope.maximal_member_groups, ())

    def test_every_transition_input_is_scanned_even_when_scope_is_small(self):
        problem = _problem({'H': (0, 100), 'A': (40, 60)}, {'H'})
        extra = tuple(MembershipTransition(ObservationId(f'unused:{i}'), float(1000 + i), FiniteInterval.exact(0))
                      for i in range(1071))
        scope = enumerate_membership_scope(**{**problem, 'transitions': (*problem['transitions'], *extra)})
        self.assertEqual(scope.raw_transition_count, 4)
        self.assertEqual(scope.identity_plan.input_transition_count, 1075)
        self.assertEqual(scope.work.input_transition_visit_count, 1075)
        self.assertEqual(scope.work.input_raw_visit_count, 8)
        self.assertEqual(scope.work.identity_index_raw_visit_count, 4)
        self.assertGreater(scope.identity_plan.base_working_temporary_bytes, 128 * 1075)
        no_anchor = enumerate_membership_scope(**{**problem, 'transitions': (*problem['transitions'], *extra),
            'atoms': tuple(replace(atom, independent_support_region_count=1) for atom in problem['atoms'])})
        self.assertEqual(no_anchor.work.input_transition_visit_count, 1075)
        self.assertEqual(no_anchor.cache_temporary_bytes, no_anchor.identity_plan.base_working_temporary_bytes)

    def test_cross_limb_precheck_counts_all_zero_copy_or_and_popcount_words(self):
        problem = _problem({f'A{i:02}': (2 * i, 2 * i + 1) for i in range(40)}, {'A00'})
        scope = enumerate_membership_scope(**problem)
        work = scope.work
        words = 6  # ceil(80/30) raw words and the same exact-trace words.
        self.assertEqual(work.identity_index_zero_word_count, 40 * words)
        self.assertEqual(work.identity_index_bit_build_count, 160)
        self.assertEqual(work.identity_index_word_update_count, 160)
        self.assertEqual(work.identity_precheck_count, 39)
        self.assertEqual(work.identity_precheck_atom_visit_count, 39)
        self.assertEqual(work.identity_precheck_copy_word_count, 39 * words)
        self.assertEqual(work.identity_precheck_or_word_count, 39 * words)
        self.assertEqual(work.identity_precheck_popcount_word_count, 39 * words)
        self.assertEqual(work.identity_word_access_count,
                         2 * 160 + 40 * words + 3 * 160 + (2 + 3 + 1) * 39 * words)
        # Each initial mask selects one atom, but high sparse bits span two
        # A-mask limbs. A count of 39 selected atoms alone misses that work.
        self.assertEqual(work.identity_precheck_mask_limb_span_count, 30 + 9 * 2)
        self.assertEqual(work.identity_precheck_mask_control_logical_limb_bound, 32 * (48 + 39))
        self.assertEqual(work.identity_logical_limb_access_bound,
                         work.identity_word_access_count + 32 * (48 + 39))

    def test_a_mask_control_bound_counts_four_limb_sparse_and_dense_masks(self):
        problem = _problem({f'A{i:03}': (2 * i, 2 * i + 1) for i in range(97)}, {'A000'})
        scope = enumerate_membership_scope(**problem)
        work = scope.work
        expected_spans = 30 + 30 * 2 + 30 * 3 + 6 * 4
        self.assertEqual(work.identity_precheck_atom_visit_count, 96)
        self.assertEqual(work.identity_precheck_mask_limb_span_count, expected_spans)
        self.assertEqual(work.identity_precheck_mask_control_logical_limb_bound, 32 * (expected_spans + 96))
        self.assertEqual(work.identity_logical_limb_access_bound,
                         work.identity_word_access_count + 32 * (expected_spans + 96))
        competing = enumerate_membership_scope(**_problem(self.groups, self.anchors))
        self.assertGreater(competing.work.identity_precheck_atom_visit_count,
                           competing.work.identity_precheck_count)
        self.assertGreater(competing.work.identity_precheck_mask_control_logical_limb_bound, 0)
        # Even a coordinated edit that preserves the final sum must satisfy
        # the separate width-dependent control accounting identity.
        with self.assertRaises(ValueError):
            replace(scope, work=replace(work,
                identity_precheck_mask_control_logical_limb_bound=work.identity_precheck_mask_control_logical_limb_bound - 1,
                identity_logical_limb_access_bound=work.identity_logical_limb_access_bound - 1))
        spans = {'sum': 0, 'dense': False}
        def inspect(frame, event, result):
            if (event == 'call' and frame.f_code.co_name == 'identity_possible'
                    and frame.f_code.co_filename == membership.__file__):
                mask = frame.f_locals['mask']
                # Removing the least set bit keeps the highest set bit
                # unchanged until the last iteration. This closed form is
                # independent of the implementation's per-iteration count.
                spans['sum'] += mask.bit_count() * ((mask.bit_length() + 29) // 30)
                spans['dense'] |= mask.bit_count() > 1 and mask.bit_length() > 30
        previous = sys.getprofile()
        sys.setprofile(inspect)
        try:
            dense = enumerate_membership_scope(**_problem({'H': (1000, 1001), **{
                f'A{i:03}': (0, 1) for i in range(40)}}, {'H'}))
        finally:
            sys.setprofile(previous)
        self.assertTrue(spans['dense'])
        self.assertEqual(dense.work.identity_precheck_mask_limb_span_count, spans['sum'])

    def test_base_working_reservation_includes_dfs_and_physical_scratch_only_with_anchors(self):
        problem = _problem(self.groups, self.anchors)
        scope = enumerate_membership_scope(**problem)
        a, t, s = scope.atom_count, scope.raw_transition_count, scope.identity_plan.trace_identity_count
        plan = scope.identity_plan
        inputs = (8192 + 128 * len(problem['transitions']) + 256 * a
                  + 64 * plan.atom_transition_input_count + 64 * (t + s))
        dfs = 64 * a * a + 4096 * a
        oracle = 8192 + 128 * t + 1024 * s + 64 * a
        self.assertEqual(plan.base_working_temporary_bytes, inputs + dfs + oracle)
        no_anchor = enumerate_membership_scope(**{**problem, 'atoms': tuple(
            replace(atom, independent_support_region_count=1) for atom in problem['atoms'])})
        self.assertEqual(no_anchor.identity_plan.base_working_temporary_bytes, inputs)
        self.assertEqual(no_anchor.cache_temporary_bytes, inputs)

    def test_optional_index_memory_preflight_disables_only_the_equivalent_acceleration(self):
        problem = _problem(self.groups, self.anchors)
        enabled = enumerate_membership_scope(**problem)
        # The existing memo still fits. The optional index, input maps and
        # memo cannot simultaneously fit this simulated source allowance.
        memo_bytes = membership._cache_temporary_bytes(len(problem['atoms']), 4096)
        with patch.object(membership, 'MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES', memo_bytes):
            disabled = enumerate_membership_scope(**problem)
            self.assertEqual(disabled.identity_plan.state, MembershipIdentityPrecheckState.MEMORY_ALLOWANCE_EXCEEDED)
            self.assertGreater(disabled.identity_plan.planned_peak_temporary_bytes, memo_bytes)
            self.assertEqual(disabled.work.identity_index_raw_visit_count, 0)
            self.assertEqual(disabled.work.identity_precheck_count, 0)
            self.assertEqual(disabled.maximal_member_groups, enabled.maximal_member_groups)
            self.assertGreater(disabled.work.visited_count, enabled.work.visited_count)
            self.assertEqual(disabled.cache_temporary_bytes,
                disabled.identity_plan.base_working_temporary_bytes
                + membership._maximal_working_bytes(disabled.atom_count, disabled.work.search_branch_count + 1)
                + membership._cache_temporary_bytes(disabled.atom_count, disabled.work.cache_peak_entry_count))

    def test_general_identity_competition_completes_within_the_unchanged_actual_limit(self):
        groups = {'H': (1000, 1001), **{f'{name}{i:02}': (2 * i, 2 * i + 1)
            for i in range(9) for name in ('A', 'B')}}
        problem = _problem(groups, {'H'})
        scope = enumerate_membership_scope(**problem)
        self.assertEqual(scope.state, MembershipState.COMPLETE)
        self.assertEqual(scope.work.visited_count, 3829)
        expected = {tuple(sorted(('H', *(f'{name}{i:02}' for i, name in enumerate(choice)))))
                    for choice in itertools.product(('A', 'B'), repeat=9)}
        self.assertEqual(set(scope.maximal_member_groups), expected)
        self.assertLessEqual(scope.identity_plan.planned_peak_temporary_bytes, 32 * 1024 * 1024)
        with patch.object(membership, 'MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES',
                          membership._cache_temporary_bytes(len(problem['atoms']), 4096)):
            unaccelerated = enumerate_membership_scope(**problem)
        self.assertEqual(unaccelerated.state, MembershipState.SEARCH_BOUND_EXCEEDED)
        self.assertEqual(unaccelerated.work.visited_count, 4096)
        self.assertEqual(unaccelerated.maximal_member_groups, ())

    def test_identity_plan_and_actual_work_tampering_is_rejected(self):
        scope = enumerate_membership_scope(**_problem(self.groups, self.anchors))
        work, plan = scope.work, scope.identity_plan
        for field in ('input_transition_count', 'atom_transition_input_count', 'atom_transition_unique_count',
                      'trace_identity_count', 'retained_scope_prefix_bytes', 'base_working_temporary_bytes',
                      'maximal_planned_working_bytes', 'index_planned_retained_bytes',
                      'index_planned_build_temporary_bytes', 'precheck_planned_temporary_bytes',
                      'planned_peak_temporary_bytes'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(scope, identity_plan=replace(plan, **{field: getattr(plan, field) + 1}))
        for field in ('input_transition_visit_count', 'input_atom_visit_count', 'input_raw_visit_count',
                      'identity_index_raw_visit_count', 'identity_index_atom_visit_count',
                      'identity_index_raw_input_count', 'identity_index_bit_build_count',
                      'identity_index_zero_word_count', 'identity_index_word_update_count',
                      'identity_precheck_count', 'identity_precheck_copy_word_count',
                      'identity_precheck_or_word_count', 'identity_precheck_popcount_word_count',
                      'identity_word_access_count', 'identity_precheck_mask_limb_span_count',
                      'identity_precheck_mask_control_logical_limb_bound', 'identity_logical_limb_access_bound',
                      'initial_identity_reject_count',
                      'branch_identity_reject_count', 'maximality_identity_reject_count'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(scope, work=replace(work, **{field: getattr(work, field) + 1}))

    def test_live_python_index_and_scratch_objects_fit_the_reserved_bytes(self):
        # Independently measure containers/ints, deduplicating aliases. Raw
        # measurement objects and string/float identities remain caller-owned.
        def live_bytes(*roots):
            seen = set()
            def walk(value):
                if id(value) in seen or isinstance(value, (str, float, MembershipAtom, MembershipTransition)):
                    return 0
                seen.add(id(value))
                size = sys.getsizeof(value)
                if isinstance(value, dict):
                    return size + sum(walk(key) + walk(item) for key, item in value.items())
                if isinstance(value, (list, tuple, set, frozenset)):
                    return size + sum(map(walk, value))
                return size
            return sum(map(walk, roots))

        for count in (2, 40, 128):
            problem = _problem({f'A{i:03}': (2 * i, 2 * i + 1) for i in range(count)}, {'A000'})
            peaks = {'inputs': 0, 'build': 0, 'retained': 0, 'scratch': 0, 'check': 0}
            def inspect(frame, event, result):
                if frame.f_code.co_filename != membership.__file__:
                    return inspect
                values = frame.f_locals
                if (frame.f_code.co_name == 'enumerate_membership_scope' and event == 'line'
                        and values.get('work', {}).get('identity_index_raw_input_count') == 2 * count
                        and values.get('raw_positions')):
                    inputs = tuple(values[name] for name in (
                        'raw', 'members', 'scope_raw', 'scope_traces', 'anchors', 'variables', 'work'))
                    retained = tuple(values[name] for name in ('anchor_raw_bits', 'anchor_trace_bits', 'variable_bits'))
                    build = (values['raw_positions'], values['trace_positions'])
                    peaks['inputs'] = max(peaks['inputs'], live_bytes(*inputs))
                    peaks['retained'] = max(peaks['retained'], live_bytes(*retained))
                    peaks['build'] = max(peaks['build'], live_bytes(*inputs, *retained, *build))
                if frame.f_code.co_name == 'identity_possible' and event == 'return':
                    retained = tuple(values[name] for name in ('anchor_raw_bits', 'anchor_trace_bits', 'variable_bits'))
                    scratch = (values['raw_bits'], values['trace_bits'])
                    # During |=, old and new scalar values coexist. Include
                    # operand/result and current variable-mask temporaries.
                    scalars = 256 + 32 * ((count + 29) // 30)
                    peaks['scratch'] = max(peaks['scratch'], live_bytes(*scratch) + scalars)
                    peaks['check'] = max(peaks['check'], live_bytes(*retained, *scratch) + scalars)
                return inspect
            previous = sys.gettrace()
            sys.settrace(inspect)
            try:
                scope = enumerate_membership_scope(**problem)
            finally:
                sys.settrace(previous)
            plan = scope.identity_plan
            with self.subTest(atoms=count):
                self.assertTrue(all(peaks.values()))
                self.assertLessEqual(peaks['inputs'], plan.base_working_temporary_bytes)
                self.assertLessEqual(peaks['retained'], plan.index_planned_retained_bytes)
                self.assertLessEqual(peaks['build'], plan.base_working_temporary_bytes
                    + plan.index_planned_retained_bytes + plan.index_planned_build_temporary_bytes)
                self.assertLessEqual(peaks['scratch'], plan.precheck_planned_temporary_bytes)
                self.assertLessEqual(peaks['check'], plan.index_planned_retained_bytes
                    + plan.precheck_planned_temporary_bytes)

    def test_exception_explicitly_releases_input_maps_memo_and_index(self):
        problem = _problem({'H': (0, 100), 'A': (40, 60), 'B': (70, 80)}, {'H'})
        with patch.object(membership, 'physical_line_region', side_effect=RuntimeError('injected physical failure')):
            try:
                enumerate_membership_scope(**problem)
            except RuntimeError as error:
                traceback = error.__traceback__
                while traceback.tb_frame.f_code.co_name != 'enumerate_membership_scope':
                    traceback = traceback.tb_next
                values = traceback.tb_frame.f_locals
                for name in ('raw', 'members', 'scope_raw', 'scope_traces', 'raw_positions',
                             'trace_positions', 'feasibility_cache', 'anchor_raw_bits',
                             'anchor_trace_bits', 'variable_bits', 'raw_bits', 'trace_bits', 'maximal', 'search'):
                    self.assertFalse(values[name], name)
            else:
                self.fail('injected physical exception was swallowed')

    def test_live_deep_exclude_chain_and_physical_clip_fit_the_base_working_bound(self):
        deep = _problem({'H': (1000, 1001), **{f'A{i:03}': (0, 1) for i in range(96)}}, {'H'})
        groups = {f'A{i:03}': (2 * i, 2 * i + 1) for i in range(40)}
        intervals = {(name, trace): (-1 - .0002 * (trace - 39.5) ** 2,
                                     1 + .0002 * (trace - 39.5) ** 2)
                     for name, traces in groups.items() for trace in traces}
        polygon = _problem(groups, {'A000'}, intervals)
        for label, problem in (('deep', deep), ('polygon', polygon)):
            scope, peaks = _sample_membership_working_memory(problem)
            a, t, s = scope.atom_count, scope.raw_transition_count, scope.identity_plan.trace_identity_count
            dfs = 64 * a * a + 4096 * a
            oracle = 8192 + 128 * t + 1024 * s + 64 * a
            with self.subTest(case=label, sampled=peaks):
                self.assertEqual(scope.state, MembershipState.COMPLETE)
                self.assertGreater(peaks['dfs_bytes'], 0)
                self.assertGreater(peaks['oracle_bytes'], 0)
                self.assertGreater(peaks['clip_coexisting_old_new_samples'], 0)
                self.assertLessEqual(peaks['dfs_bytes'], dfs)
                self.assertLessEqual(peaks['oracle_bytes'], oracle)
                self.assertLessEqual(peaks['working_bytes'], scope.cache_temporary_bytes)
                self.assertLessEqual(peaks['maximal_temporary_bytes'], membership._maximal_working_bytes(
                    a, scope.work.search_branch_count + 1))
                self.assertLessEqual(peaks['returned_scope_bytes'], scope.retained_bytes)
                if label == 'deep':
                    self.assertGreaterEqual(peaks['depth'], 96)
                else:
                    self.assertEqual(peaks['interval_count'], 80)
                    self.assertGreaterEqual(peaks['clip_vertices'], 80)

    def test_retained_scope_prefix_is_planned_replayed_and_checked_independently(self):
        problem = _problem(self.groups, self.anchors)
        first = enumerate_membership_scope(**problem)
        second_problem = {**problem, 'parent_family_id': 'second',
            'retained_scope_prefix_bytes': first.retained_bytes}
        second, peaks = _sample_membership_working_memory(second_problem, (first,))
        self.assertEqual(second.identity_plan.retained_scope_prefix_bytes, first.retained_bytes)
        self.assertEqual(second.cache_temporary_bytes, first.cache_temporary_bytes + first.retained_bytes)
        self.assertLessEqual(peaks['prior_retained_bytes'], first.retained_bytes)
        self.assertLessEqual(peaks['working_bytes'], second.cache_temporary_bytes)
        budgets = tuple(MembershipFitBudget(role, 0, 0, 0, 0) for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM))
        frozen = tuple(sorted(atom.observation_id for atom in problem['atoms']))
        receipt = MembershipReceipt(MembershipState.COMPLETE, (first, second), budgets, frozen)
        from x5crop.detection.photo_geometry.template_registration import CrossRegistrationWorkReceipt
        source = CrossRegistrationWorkReceipt(0, 0, 0, membership=receipt)
        self.assertEqual(source.membership_cache_peak_temporary_bytes, second.cache_temporary_bytes)
        tampered_plan = replace(second.identity_plan, retained_scope_prefix_bytes=0,
            planned_peak_temporary_bytes=second.identity_plan.planned_peak_temporary_bytes - first.retained_bytes)
        tampered = replace(second, identity_plan=tampered_plan)
        with self.assertRaises(ValueError):
            MembershipReceipt(MembershipState.COMPLETE, (first, tampered), budgets, frozen)
        prefix = 32 * 1024 * 1024 - first.identity_plan.planned_peak_temporary_bytes + 1
        disabled = enumerate_membership_scope(**{**problem, 'retained_scope_prefix_bytes': prefix})
        self.assertEqual(disabled.identity_plan.state, MembershipIdentityPrecheckState.MEMORY_ALLOWANCE_EXCEEDED)
        self.assertGreater(disabled.identity_plan.planned_peak_temporary_bytes, 32 * 1024 * 1024)
        self.assertEqual(disabled.maximal_member_groups, first.maximal_member_groups)
        self.assertGreaterEqual(disabled.cache_temporary_bytes,
                                prefix + disabled.identity_plan.base_working_temporary_bytes)

    def test_success_and_exhaustion_explicitly_release_maximal_list_and_search_cycle(self):
        problem = _problem({'H': (1000, 1001), **{f'{name}{i:02}': (2 * i, 2 * i + 1)
            for i in range(12) for name in ('A', 'B')}}, {'H'})
        cases = (_problem(self.groups, self.anchors), problem)
        for item in cases:
            captured = {}
            def inspect(frame, event, result):
                if (event == 'return' and frame.f_code.co_name == 'enumerate_membership_scope'
                        and frame.f_code.co_filename == membership.__file__):
                    captured['cleared'] = frame.f_locals['maximal'] == []
                    captured['cycle_broken'] = frame.f_locals['search'] is None
            previous = sys.getprofile()
            sys.setprofile(inspect)
            try:
                scope = enumerate_membership_scope(**item)
            finally:
                sys.setprofile(previous)
            self.assertTrue(captured['cleared'])
            self.assertTrue(captured['cycle_broken'])
            if scope.state == MembershipState.COMPLETE:
                self.assertTrue(scope.maximal_member_groups)
            else:
                self.assertEqual(scope.state, MembershipState.SEARCH_BOUND_EXCEEDED)
                self.assertEqual(scope.maximal_member_groups, ())

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
