from __future__ import annotations

from dataclasses import fields, replace
import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from x5crop.configuration.candidate import SequenceSolverParameters
from tools.tests.frame_slot_solver_support import (
    content,
    dimensions,
    geometry,
    path,
    scope,
    separator,
    sequence_search_index,
)
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.detection.candidate.model import sequence_proof_paths_for_geometry
from x5crop.detection.physical import frame_sequence_solver as solver_module
from x5crop.detection.physical import model as physical_model
from x5crop.detection.physical.frame_dimensions import frame_dimension_evidence
from x5crop.detection.physical.frame_sequence_solver import (
    _CommonWidthHypothesis,
    _DimensionPlacementHypothesis,
    FrameSequenceSolveFailure,
    FrameSequenceSolveResult,
    _EdgeConstraint,
    _MeasuredFrameConstraint,
    _SequenceBuildObjectives,
    _dimension_frame_constraints,
    _common_measured_width_interval,
    _measured_frame_search_space,
    _measured_sequence_build,
    _measured_width_hypotheses,
    _non_dominated_width_hypotheses,
    _physically_preferred_builds,
    _strict_majority_width_consensus,
    _uncorroborated_overlap_extent,
    _unexplained_spacing_extent,
    solve_frame_sequence,
)
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameContentOccupancy,
    FrameBoundarySource,
    FrameSlot,
    ResolvedFrameBoundary,
    SeparatorBandAssignment,
)
from x5crop.detection.physical.short_axis import shared_short_axis_plan
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PixelInterval,
    SeparatorBandCrossAxisSupport,
)


_ALL_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)


def _solve(
    *,
    search_scope,
    visible_content,
    count: int,
    frame_dimensions,
    supports=(),
    strip_mode: str = "full",
    nominal_count: int | None = None,
    maximum_assignment_evaluations: int = 100_000,
):
    plan = shared_short_axis_plan(search_scope)
    return solve_frame_sequence(
        sequence_search_index(search_scope, tuple(supports)),
        search_scope,
        plan,
        count,
        frame_dimensions,
        visible_content,
        maximum_assignment_evaluations,
        strip_mode=strip_mode,
        nominal_count=count if nominal_count is None else nominal_count,
    )


class FrameSequenceSolverContractTest(unittest.TestCase):
    def test_unique_gray_path_locates_geometry_without_proving_edge_role(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        first, second = geometry.frame_slots
        position = second.leading.position
        inferred_leading = ResolvedFrameBoundary(
            position=position,
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=None,
            inference_provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("dimension_only_second_leading"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "synthetic dimension-only leading edge",
            ),
        )
        slots = (
            first,
            replace(
                second,
                leading=inferred_leading,
                visible_long_axis=PixelInterval(
                    inferred_leading.position.minimum,
                    second.trailing.position.maximum,
                ),
            ),
        )
        build = solver_module._SequenceBuild(
            slots=slots,
            long_axis_assignments=geometry.long_axis_assignments,
            separator_bindings=(),
            spacings=geometry.inter_frame_spacings,
            frame_width_px=geometry.common_frame_width.width_px,
            short_axis=geometry.shared_short_axis,
            residuals=geometry.residuals,
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=10.0,
                supported_separator_count=0,
                internal_boundary_measurement_quality=1.0,
                dimension_residual=0.0,
                external_boundary_measurement_quality=2.0,
                boundary_uncertainty_ratio=0.0,
                inferred_boundary_count=1,
            ),
        )
        observation = path(
            BoundaryAxis.LONG,
            position.midpoint,
            "unique_dimension_focused_path",
        )

        resolved = solver_module._assign_unique_boundary_path_observations(
            build,
            geometry.common_frame_width,
            (observation,),
        )

        boundary = resolved.slots[1].leading
        self.assertEqual(boundary.source, FrameBoundarySource.GRAY_PATH_OBSERVATION)
        self.assertEqual(boundary.role_state, EvidenceState.UNAVAILABLE)
        self.assertFalse(boundary.independently_observed)
        self.assertTrue(
            any(
                assignment.observation == observation
                for assignment in resolved.long_axis_assignments
            )
        )

    def test_unique_separator_observation_replaces_unmeasured_boundary_pair(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        first, second = geometry.frame_slots
        assignment = geometry.separator_assignments[0]

        def inferred_boundary(
            position: PixelInterval,
            label: str,
        ) -> ResolvedFrameBoundary:
            return ResolvedFrameBoundary(
                position=position,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=None,
                inference_provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (MeasurementIdentity.FRAME_DIMENSIONS,),
                    "synthetic unmeasured boundary pair",
                ),
            )

        trailing = inferred_boundary(
            assignment.observation.leading_edge,
            "unmeasured_separator_leading_edge",
        )
        leading = inferred_boundary(
            assignment.observation.trailing_edge,
            "unmeasured_separator_trailing_edge",
        )
        slots = (
            replace(
                first,
                trailing=trailing,
                visible_long_axis=PixelInterval(
                    first.leading.position.minimum,
                    trailing.position.maximum,
                ),
            ),
            replace(
                second,
                leading=leading,
                visible_long_axis=PixelInterval(
                    leading.position.minimum,
                    second.trailing.position.maximum,
                ),
            ),
        )
        build = solver_module._SequenceBuild(
            slots=slots,
            long_axis_assignments=geometry.long_axis_assignments,
            separator_bindings=(),
            spacings=geometry.inter_frame_spacings,
            frame_width_px=geometry.common_frame_width.width_px,
            short_axis=geometry.shared_short_axis,
            residuals=geometry.residuals,
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=10.0,
                supported_separator_count=0,
                internal_boundary_measurement_quality=0.0,
                dimension_residual=0.0,
                external_boundary_measurement_quality=2.0,
                boundary_uncertainty_ratio=0.0,
                inferred_boundary_count=2,
            ),
        )

        resolved = solver_module._assign_unique_separator_observations(
            build,
            geometry.common_frame_width,
            (
                SeparatorBandCrossAxisSupport(
                    assignment.observation,
                    assignment.cross_axis_measurement,
                ),
            ),
        )

        self.assertEqual(len(resolved.separator_bindings), 1)
        self.assertEqual(
            resolved.slots[0].trailing.source,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        )
        self.assertEqual(
            resolved.slots[1].leading.source,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        )
        self.assertTrue(resolved.slots[0].trailing.independently_observed)
        self.assertTrue(resolved.slots[1].leading.independently_observed)

    def test_separator_observation_supersedes_incompatible_unproven_paths(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        first, second = geometry.frame_slots
        assignment = geometry.separator_assignments[0]

        def unproven_path_boundary(
            position: PixelInterval,
            side: BoundarySide,
        ) -> ResolvedFrameBoundary:
            observation = path(
                BoundaryAxis.LONG,
                position.midpoint,
                f"unproven_{side.value}_path",
            )
            anchor = BoundaryAnchor(
                observation=observation,
                physical_role=side,
                role_state=EvidenceState.SUPPORTED,
                role_authority=BoundaryRoleAuthority.GEOMETRY_CORROBORATED,
                role_provenance=MeasurementProvenance(
                    MeasurementIdentity.PHOTO_EDGES,
                    ObservationId(f"dimension_corroborated_{side.value}_role"),
                    (
                        MeasurementIdentity.GRAY_WORK,
                        MeasurementIdentity.BOUNDARY_PATHS,
                        MeasurementIdentity.FRAME_DIMENSIONS,
                    ),
                    "synthetic geometry-corroborated photo-edge role",
                    boundary_anchors=(observation.provenance.observation_id,),
                ),
            )
            return ResolvedFrameBoundary(
                position=position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=anchor,
                inference_provenance=None,
            )

        observed_trailing = assignment.observation.leading_edge
        observed_leading = assignment.observation.trailing_edge
        displaced_trailing = unproven_path_boundary(
            PixelInterval(
                observed_trailing.minimum + 60.0,
                observed_trailing.maximum + 60.0,
            ),
            BoundarySide.TRAILING,
        )
        displaced_leading = unproven_path_boundary(
            PixelInterval(
                observed_leading.minimum + 60.0,
                observed_leading.maximum + 60.0,
            ),
            BoundarySide.LEADING,
        )
        slots = (
            replace(
                first,
                trailing=displaced_trailing,
                visible_long_axis=PixelInterval(
                    first.leading.position.minimum,
                    displaced_trailing.position.maximum,
                ),
            ),
            replace(
                second,
                leading=displaced_leading,
                visible_long_axis=PixelInterval(
                    displaced_leading.position.minimum,
                    second.trailing.position.maximum,
                ),
            ),
        )
        build = solver_module._SequenceBuild(
            slots=slots,
            long_axis_assignments=geometry.long_axis_assignments,
            separator_bindings=(),
            spacings=geometry.inter_frame_spacings,
            frame_width_px=geometry.common_frame_width.width_px,
            short_axis=geometry.shared_short_axis,
            residuals=geometry.residuals,
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=10.0,
                supported_separator_count=0,
                internal_boundary_measurement_quality=0.0,
                dimension_residual=0.0,
                external_boundary_measurement_quality=2.0,
                boundary_uncertainty_ratio=0.0,
                inferred_boundary_count=2,
            ),
        )

        resolved = solver_module._assign_unique_separator_observations(
            build,
            geometry.common_frame_width,
            (
                SeparatorBandCrossAxisSupport(
                    assignment.observation,
                    assignment.cross_axis_measurement,
                ),
            ),
        )

        self.assertEqual(len(resolved.separator_bindings), 1)
        self.assertEqual(
            resolved.slots[0].trailing.position,
            assignment.observation.leading_edge,
        )
        self.assertEqual(
            resolved.slots[1].leading.position,
            assignment.observation.trailing_edge,
        )

    def test_frame_sequence_rejects_non_monotonic_separator_assignments(
        self,
    ) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
            )
        )
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=440, height=100),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        sequence = geometry(
            search_scope,
            supports,
            dimensions(1.0, 1.0),
            solved,
            nominal_count=4,
        )
        self.assertEqual(
            tuple(item.boundary_index for item in sequence.separator_assignments),
            (1, 2, 3),
        )

        with self.assertRaisesRegex(ValueError, "unique and ordered"):
            replace(
                sequence,
                separator_assignments=tuple(reversed(sequence.separator_assignments)),
            )

    def test_indexed_anchor_distance_retains_compatible_local_width(self) -> None:
        first_measurement = MeasurementProvenance(
            MeasurementIdentity.SEPARATOR_PROFILE,
            ObservationId("synthetic_separator:compatible_first"),
            (MeasurementIdentity.GRAY_WORK,),
            "first compatible synthetic separator",
        )
        second_measurement = MeasurementProvenance(
            MeasurementIdentity.SEPARATOR_PROFILE,
            ObservationId("synthetic_separator:compatible_second"),
            (MeasurementIdentity.GRAY_WORK,),
            "second compatible synthetic separator",
        )
        assignments = (
            SimpleNamespace(
                boundary_index=1,
                following_leading_edge=SimpleNamespace(
                    position=PixelInterval.exact(100.0),
                ),
                observation=SimpleNamespace(provenance=first_measurement),
            ),
            SimpleNamespace(
                boundary_index=2,
                preceding_trailing_edge=SimpleNamespace(
                    position=PixelInterval.exact(300.0),
                ),
                observation=SimpleNamespace(provenance=second_measurement),
            ),
        )

        constraints = solver_module._indexed_anchor_distance_constraints(
            assignments,
            (),
            PixelInterval(205.0, 215.0),
        )

        self.assertIsNotNone(constraints)
        assert constraints is not None
        self.assertEqual(len(constraints), 1)
        self.assertEqual(
            constraints[0].implied_frame_width_px,
            PixelInterval.exact(200.0),
        )

    def test_inconsistent_indexed_anchor_distance_is_not_constructed(self) -> None:
        first_measurement = MeasurementProvenance(
            MeasurementIdentity.SEPARATOR_PROFILE,
            ObservationId("synthetic_separator:first"),
            (MeasurementIdentity.GRAY_WORK,),
            "first synthetic separator",
        )
        second_measurement = MeasurementProvenance(
            MeasurementIdentity.SEPARATOR_PROFILE,
            ObservationId("synthetic_separator:second"),
            (MeasurementIdentity.GRAY_WORK,),
            "second synthetic separator",
        )
        assignments = (
            SimpleNamespace(
                boundary_index=1,
                following_leading_edge=SimpleNamespace(
                    position=PixelInterval.exact(100.0),
                ),
                observation=SimpleNamespace(provenance=first_measurement),
            ),
            SimpleNamespace(
                boundary_index=2,
                preceding_trailing_edge=SimpleNamespace(
                    position=PixelInterval.exact(300.0),
                ),
                observation=SimpleNamespace(provenance=second_measurement),
            ),
        )

        constraints = solver_module._indexed_anchor_distance_constraints(
            assignments,
            (),
            PixelInterval(250.0, 260.0),
        )

        self.assertEqual(constraints, ())

    def test_missing_indexed_anchor_constraint_does_not_erase_solution(
        self,
    ) -> None:
        search_scope = scope(
            width=100,
            height=50,
            leading=0.0,
            trailing=100.0,
            top=0.0,
            bottom=50.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )

        with patch.object(
            solver_module,
            "_indexed_anchor_distance_constraints",
            return_value=(),
        ):
            solved = _solve(
                search_scope=search_scope,
                visible_content=content(
                    width=100,
                    height=50,
                    runs=((0, 100),),
                ),
                count=1,
                frame_dimensions=dimensions(2.0, 1.0),
            )

        self.assertIsInstance(solved, FrameSequenceSolveResult)

    def test_separator_assignment_carries_global_frame_width_feasibility(
        self,
    ) -> None:
        self.assertIn(
            "frame_width_px",
            {field.name for field in fields(SeparatorBandAssignment)},
        )

    def test_sequence_geometry_rejects_separator_without_supported_common_width(
        self,
    ) -> None:
        geometry_with_separator = candidate_fixture().geometry
        unresolved_width = replace(
            geometry_with_separator.common_frame_width,
            width_px=None,
            constraints=(),
            physical_scale_constraint=None,
            state=EvidenceState.UNAVAILABLE,
        )
        with self.assertRaises(ValueError):
            replace(
                geometry_with_separator,
                common_frame_width=unresolved_width,
            )

    def test_weak_separator_edges_are_geometry_hypotheses_not_hard_support(
        self,
    ) -> None:
        search_scope = scope(
            width=320,
            height=100,
            leading=0.0,
            trailing=320.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        weak = separator(100.0, 120.0, plan, supported=False)

        geometry_leading, geometry_trailing = (
            solver_module._separator_geometry_edge_candidates(
                (weak,),
                search_scope,
            )
        )
        hard_leading, hard_trailing = solver_module._separator_edge_candidates(
            (weak,),
            search_scope,
        )

        self.assertEqual(hard_leading, ())
        self.assertEqual(hard_trailing, ())
        self.assertEqual(
            geometry_leading[0][0].position,
            PixelInterval.exact(120.0),
        )
        self.assertEqual(
            geometry_trailing[0][0].position,
            PixelInterval.exact(100.0),
        )
        self.assertEqual(geometry_leading[0][0].state, EvidenceState.UNAVAILABLE)
        self.assertEqual(geometry_trailing[0][0].state, EvidenceState.UNAVAILABLE)

    def test_measured_common_width_precedes_short_axis_search_hint(self) -> None:
        measured = _CommonWidthHypothesis(
            width_px=PixelInterval(100.0, 102.0),
            boundary_anchors=(ObservationId("measured_common_width"),),
            contributor_count=2,
        )
        hint = PixelInterval(110.0, 125.0)

        branches = solver_module._dimension_placement_hypotheses(
            (measured,),
            (),
            (hint,),
            None,
        )

        self.assertEqual(branches[0].width_px, measured.width_px)
        self.assertEqual(branches[0].boundary_anchors, measured.boundary_anchors)
        self.assertEqual(branches[-1].width_px, hint)
        self.assertEqual(branches[-1].boundary_anchors, ())

    def test_recurring_boundary_width_precedes_search_hint(self) -> None:
        recurring = solver_module._RecurringBoundaryWidthHypothesis(
            width_px=PixelInterval(100.0, 102.0),
            contributor_count=4,
        )
        hint = PixelInterval(110.0, 125.0)

        branches = solver_module._dimension_placement_hypotheses(
            (),
            (recurring,),
            (hint,),
            None,
        )

        self.assertEqual(branches[0].width_px, recurring.width_px)
        self.assertEqual(branches[0].repeated_slot_count, 4)
        self.assertEqual(branches[-1].width_px, hint)
        self.assertEqual(branches[-1].repeated_slot_count, 0)

    def test_dominated_recurring_widths_share_one_search_branch(self) -> None:
        stronger = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 104.0),
            4,
        )
        weaker_overlap = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(99.0, 105.0),
            3,
        )
        distinct = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(120.0, 122.0),
            2,
        )

        branches = solver_module._dimension_placement_hypotheses(
            (),
            (weaker_overlap, distinct, stronger),
            (),
            None,
        )

        self.assertEqual(
            tuple(
                (branch.width_px, branch.repeated_slot_count)
                for branch in branches
            ),
            (
                (stronger.width_px, stronger.contributor_count),
                (distinct.width_px, distinct.contributor_count),
            ),
        )

    def test_edge_overlapping_recurring_widths_remain_distinct_branches(
        self,
    ) -> None:
        first = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(3141.0, 3182.0),
            5,
        )
        second = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(3101.0, 3143.0),
            5,
        )

        branches = solver_module._dimension_placement_hypotheses(
            (),
            (first, second),
            (),
            None,
        )

        self.assertEqual(
            tuple(branch.width_px for branch in branches),
            (first.width_px, second.width_px),
        )

    def test_frame_width_hint_orders_but_does_not_delete_recurring_widths(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plausible = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 102.0),
            4,
        )
        frequent_texture = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(20.0, 21.0),
            9,
        )
        search_index = replace(
            sequence_search_index(search_scope),
            recurring_width_hypotheses=(frequent_texture, plausible),
        )

        search_space = _measured_frame_search_space(
            search_index,
            (PixelInterval.exact(120.0), PixelInterval(98.0, 104.0)),
            PixelInterval(98.0, 104.0),
            None,
        )

        self.assertEqual(search_space.recurring_width_hypotheses[0], plausible)
        self.assertEqual(
            set(search_space.recurring_width_hypotheses),
            {plausible, frequent_texture},
        )

    def test_more_frequent_width_hint_cannot_prune_separator_backed_solution(
        self,
    ) -> None:
        search_scope = scope(
            width=400,
            height=100,
            leading=0.0,
            trailing=400.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(90.0, 100.0, plan, supported=True),
            separator(290.0, 300.0, plan, supported=True),
        )
        search_index = replace(
            sequence_search_index(search_scope, supports),
            recurring_width_hypotheses=(
                solver_module._RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(100.0),
                    9,
                ),
                solver_module._RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(90.0),
                    4,
                ),
            ),
        )
        visible_content = content(
            width=400,
            height=100,
            runs=((0, 90), (100, 190), (200, 290), (300, 390)),
        )

        solved = solve_frame_sequence(
            search_index,
            search_scope,
            plan,
            4,
            dimensions(1.0, 1.0),
            visible_content,
            100_000,
            strip_mode="full",
            nominal_count=4,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(
                (slot.visible_long_axis.minimum, slot.visible_long_axis.maximum)
                for slot in solved.frame_slots
            ),
            ((0.0, 90.0), (100.0, 190.0), (200.0, 290.0), (300.0, 390.0)),
        )
        self.assertTrue(solved.frame_slots[0].trailing.independently_observed)
        self.assertTrue(solved.frame_slots[1].leading.independently_observed)
        self.assertTrue(solved.frame_slots[2].trailing.independently_observed)
        self.assertTrue(solved.frame_slots[3].leading.independently_observed)

    def test_separator_spacing_hint_precedes_short_axis_width_hint(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        separator_aligned = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 104.0),
            4,
        )
        short_axis_aligned = solver_module._RecurringBoundaryWidthHypothesis(
            PixelInterval(126.0, 132.0),
            5,
        )
        search_index = replace(
            sequence_search_index(search_scope),
            recurring_width_hypotheses=(
                short_axis_aligned,
                separator_aligned,
            ),
        )

        search_space = _measured_frame_search_space(
            search_index,
            (PixelInterval(98.0, 105.0), PixelInterval(124.0, 134.0)),
            PixelInterval(124.0, 134.0),
            None,
        )

        self.assertEqual(
            search_space.recurring_width_hypotheses[0],
            separator_aligned,
        )

    def test_unassigned_bands_do_not_claim_common_frame_width(self) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=0.0,
            trailing=440.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (150.0, 160.0),
                (210.0, 220.0),
                (260.0, 270.0),
                (320.0, 330.0),
            )
        )

        search_index = sequence_search_index(search_scope, supports)

        self.assertEqual(search_index.width_hypotheses, ())

    def test_separator_run_width_is_search_only_until_slots_are_bound(self) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=0.0,
            trailing=440.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
            )
        )

        self.assertEqual(
            solver_module._raw_separator_frame_width_search_hints(
                supports,
                search_scope,
                4,
            ),
            (PixelInterval.exact(100.0),),
        )
        self.assertEqual(
            sequence_search_index(search_scope, supports).width_hypotheses,
            (),
        )

    def test_sparse_separator_subset_does_not_claim_adjacent_width_hint(
        self,
    ) -> None:
        search_scope = scope(
            width=650,
            height=100,
            leading=0.0,
            trailing=650.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        sparse_supports = tuple(
            separator(start, start + 10.0, plan, supported=True)
            for start in (100.0, 320.0, 540.0)
        )

        self.assertEqual(
            solver_module._raw_separator_frame_width_search_hints(
                sparse_supports,
                search_scope,
                6,
            ),
            (),
        )

    def test_graph_layer_state_index_is_built_once_per_transition(self) -> None:
        def edge(position: float) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"layer_index_edge:{position}"),
                    (),
                    "synthetic graph layer edge",
                ),
            )

        def frame(start: float, end: float) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(end - start),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = (
            frame(0.0, 100.0),
            frame(110.0, 210.0),
            frame(220.0, 320.0),
        )
        grouped = tuple(((index, option),) for index, option in enumerate(ordered))
        context = solver_module._sequence_graph_context(
            ordered,
            content(width=320, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )
        build_index = solver_module._graph_layer_state_index

        with patch.object(
            solver_module,
            "_graph_layer_state_index",
            wraps=build_index,
        ) as indexed:
            sequence = solver_module._sequence_graph_best_path(
                grouped,
                ordered,
                context,
            )

        self.assertEqual(sequence, ordered)
        self.assertEqual(indexed.call_count, len(grouped) - 1)

    def test_blank_search_retains_a_witness_for_every_feasible_anchor(self) -> None:
        def edge(position: float) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"blank_witness_edge:{position}"),
                    (),
                    "synthetic blank-search edge",
                ),
            )

        def frame(start: float) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = tuple(
            frame(start)
            for start in (0.0, 110.0, 220.0, 330.0, 650.0)
        )
        grouped = (
            ((0, ordered[0]),),
            tuple((index, ordered[index]) for index in (1, 2, 3)),
            ((4, ordered[4]),),
        )
        context = solver_module._sequence_graph_context(
            ordered,
            content(width=750, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )

        witnesses = solver_module._sequence_graph_witnesses(
            grouped,
            ordered,
            context,
        )

        witnessed_middle_options = {
            ordered.index(sequence[1]) for sequence in witnesses
        }
        self.assertEqual(witnessed_middle_options, {1, 2, 3})

    def test_blank_search_retains_frame_sized_anchor_pair_alternative(self) -> None:
        def edge(position: float) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"blank_pair_edge:{position}"),
                    (),
                    "synthetic blank-pair edge",
                ),
            )

        def frame(start: float) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        ordered = tuple(
            frame(start)
            for start in (0.0, 110.0, 220.0, 330.0, 330.0, 440.0, 550.0)
        )
        grouped = (
            ((0, ordered[0]),),
            ((1, ordered[1]),),
            ((2, ordered[2]), (3, ordered[3])),
            ((4, ordered[4]), (5, ordered[5])),
            ((6, ordered[6]),),
        )
        context = solver_module._sequence_graph_context(
            ordered,
            content(width=650, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )

        witnesses = solver_module._sequence_graph_witnesses(
            grouped,
            ordered,
            context,
        )

        self.assertIn(
            (ordered[0], ordered[1], ordered[2], ordered[5], ordered[6]),
            witnesses,
        )

    def test_sequence_graph_conservation_precedes_separator_support(self) -> None:
        search_scope = scope(
            width=5_200,
            height=100,
            leading=0.0,
            trailing=5_200.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        separator_support = separator(1_100.0, 1_110.0, plan, supported=True)
        bad_first_trailing, bad_second_leading = (
            solver_module._observed_band_edges(separator_support)
        )

        def dimension(position: float, label: str) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension edge",
                ),
            )

        def frame(
            leading: _EdgeConstraint,
            trailing: _EdgeConstraint,
        ) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        conserved = (
            frame(dimension(0.0, "good-1-leading"), dimension(100.0, "good-1-trailing")),
            frame(dimension(110.0, "good-2-leading"), dimension(210.0, "good-2-trailing")),
            frame(dimension(220.0, "good-3-leading"), dimension(320.0, "good-3-trailing")),
        )
        fragmented = (
            frame(dimension(1_000.0, "bad-1-leading"), bad_first_trailing),
            frame(bad_second_leading, dimension(1_210.0, "bad-2-trailing")),
            frame(dimension(5_000.0, "bad-3-leading"), dimension(5_100.0, "bad-3-trailing")),
        )
        ordered = (*conserved, *fragmented)
        grouped = tuple(
            (
                (layer, conserved[layer]),
                (layer + len(conserved), fragmented[layer]),
            )
            for layer in range(len(conserved))
        )

        selected = solver_module._sequence_graph_best_path(
            grouped,
            ordered,
            solver_module._sequence_graph_context(
                ordered,
                content(width=5_200, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertEqual(selected, conserved)

    def test_small_width_alternative_does_not_cap_larger_sequence_spacing(
        self,
    ) -> None:
        def edge(position: float) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"mixed_width_edge:{position}"),
                    (),
                    "synthetic mixed-width graph edge",
                ),
            )

        def frame(start: float) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        expected = tuple(frame(start) for start in (0.0, 130.0, 260.0))

        sequences, _, truncated = solver_module._measured_frame_sequences(
            expected,
            3,
            content(width=360, height=100, runs=()),
            100,
            (
                PixelInterval(20.0, 25.0),
                PixelInterval(95.0, 105.0),
            ),
            allow_nominal_slot_sized_gap=False,
        )

        self.assertFalse(truncated)
        self.assertIn(expected, sequences)

    def test_blank_pair_witness_uses_physical_prefix_and_suffix(self) -> None:
        def edge(position: float) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"blank_pair_path_edge:{position}"),
                    (),
                    "synthetic dimension edge",
                ),
            )

        def frame(start: float) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(start + 100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        correct = tuple(frame(start) for start in (0.0, 110.0, 220.0, 530.0, 640.0))
        prefix_distractor = frame(200.0)
        suffix_distractor = frame(550.0)
        alternate = tuple(
            frame(start) for start in (1_000.0, 1_110.0, 1_220.0, 1_330.0, 1_440.0)
        )
        ordered = (
            correct[0],
            alternate[0],
            correct[1],
            prefix_distractor,
            alternate[1],
            correct[2],
            alternate[2],
            correct[3],
            alternate[3],
            correct[4],
            suffix_distractor,
            alternate[4],
        )
        grouped = (
            ((0, correct[0]), (1, alternate[0])),
            (
                (2, correct[1]),
                (3, prefix_distractor),
                (4, alternate[1]),
            ),
            ((5, correct[2]), (6, alternate[2])),
            ((7, correct[3]), (8, alternate[3])),
            (
                (9, correct[4]),
                (10, suffix_distractor),
                (11, alternate[4]),
            ),
        )

        witnesses = solver_module._sequence_graph_witnesses(
            grouped,
            ordered,
            solver_module._sequence_graph_context(
                ordered,
                content(width=1_540, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertIn(correct, witnesses)

    def test_repeated_width_compatibility_is_materialized_once(self) -> None:
        def edge(position: float, identity: str) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(position),
                provenance=SimpleNamespace(
                    observation_id=ObservationId(identity),
                ),
            )

        constraints = (
            SimpleNamespace(
                leading=edge(0.0, "leading_1"),
                trailing=edge(100.0, "trailing_1"),
                width_px=PixelInterval(98.0, 102.0),
            ),
            SimpleNamespace(
                leading=edge(110.0, "leading_2"),
                trailing=edge(211.0, "trailing_2"),
                width_px=PixelInterval(99.0, 103.0),
            ),
            SimpleNamespace(
                leading=edge(220.0, "leading_3"),
                trailing=edge(320.0, "trailing_3"),
                width_px=PixelInterval(97.0, 101.0),
            ),
        )
        compatibility = solver_module._width_compatibility_matrix

        with patch.object(
            solver_module,
            "_width_compatibility_matrix",
            wraps=compatibility,
        ) as materialize:
            contributors = solver_module._repeated_width_contributor_sets(
                constraints,
                2,
            )

        self.assertTrue(contributors)
        materialize.assert_called_once()

    def test_width_contributor_index_is_reused_across_count_hypotheses(
        self,
    ) -> None:
        search_scope = scope(
            width=650,
            height=100,
            leading=0.0,
            trailing=650.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        repeated = solver_module._repeated_width_contributor_sets

        with patch.object(
            solver_module,
            "_repeated_width_contributor_sets",
            wraps=repeated,
        ) as contributor_search:
            search_index = sequence_search_index(search_scope)
            preparation_calls = contributor_search.call_count
            _measured_frame_search_space(
                search_index,
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                None,
            )
            _measured_frame_search_space(
                search_index,
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                None,
            )

        self.assertGreater(preparation_calls, 0)
        self.assertEqual(contributor_search.call_count, preparation_calls)

    def test_common_width_group_requires_an_explicit_width_hypothesis(self) -> None:
        def option(width: PixelInterval, source: str) -> SimpleNamespace:
            def supported_edge(side: str) -> SimpleNamespace:
                return SimpleNamespace(
                    state=EvidenceState.UNAVAILABLE,
                    separator_cross_axis=SimpleNamespace(
                        state=EvidenceState.SUPPORTED,
                    ),
                    provenance=SimpleNamespace(
                        observation_id=ObservationId(f"{source}:{side}"),
                    ),
                )

            return SimpleNamespace(
                width_px=width,
                leading=supported_edge("leading"),
                trailing=supported_edge("trailing"),
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
            )

        options_by_frame = (
            ((0, option(PixelInterval(98.0, 102.0), "frame_1")),),
            ((1, option(PixelInterval(99.0, 103.0), "frame_2")),),
            ((2, option(PixelInterval(100.0, 104.0), "frame_3")),),
        )

        index = solver_module._common_width_option_index(
            options_by_frame,
            3,
            (PixelInterval(80.0, 140.0),),
        )

        self.assertEqual(index.group_masks, ())

    def test_single_supported_edge_cannot_seed_common_width(self) -> None:
        supported_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
            ),
            provenance=SimpleNamespace(
                observation_id=ObservationId("supported_edge"),
            ),
        )
        unavailable_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=None,
            provenance=SimpleNamespace(
                observation_id=ObservationId("unavailable_edge"),
            ),
        )
        option = SimpleNamespace(
            width_px=PixelInterval.exact(200.0),
            leading=supported_edge,
            trailing=unavailable_edge,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
        )

        index = solver_module._common_width_option_index(
            (((0, option),), ((1, option),)),
            2,
            (PixelInterval.exact(100.0),),
        )

        self.assertEqual(index.group_masks, ())

    def test_same_observation_cannot_seed_frame_width(self) -> None:
        shared_provenance = SimpleNamespace(
            observation_id=ObservationId("one_separator_band"),
        )
        supported_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
            ),
            provenance=shared_provenance,
        )
        option = SimpleNamespace(
            width_px=PixelInterval.exact(200.0),
            leading=supported_edge,
            trailing=supported_edge,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
        )

        index = solver_module._common_width_option_index(
            (((0, option),), ((1, option),)),
            2,
            (PixelInterval.exact(100.0),),
        )

        self.assertEqual(index.group_masks, ())

    def test_common_width_group_respects_measurement_uncertainty(self) -> None:
        def option(width: PixelInterval, source: str) -> SimpleNamespace:
            def supported_edge(side: str) -> SimpleNamespace:
                return SimpleNamespace(
                    state=EvidenceState.UNAVAILABLE,
                    separator_cross_axis=SimpleNamespace(
                        state=EvidenceState.SUPPORTED,
                    ),
                    provenance=SimpleNamespace(
                        observation_id=ObservationId(f"{source}:{side}"),
                    ),
                )

            return SimpleNamespace(
                width_px=width,
                leading=supported_edge("leading"),
                trailing=supported_edge("trailing"),
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
            )

        index = solver_module._common_width_option_index(
            (
                ((0, option(PixelInterval(98.0, 100.0), "frame_1")),),
                ((1, option(PixelInterval(101.0, 103.0), "frame_2")),),
            ),
            2,
            (PixelInterval(90.0, 110.0),),
        )

        self.assertIn((1, 2), index.group_masks)

    def test_broad_width_uncertainty_cannot_bridge_disjoint_narrow_groups(
        self,
    ) -> None:
        intervals = (
            PixelInterval(95.0, 100.0),
            PixelInterval(90.0, 120.0),
            PixelInterval(110.0, 115.0),
        )
        constraints = tuple(
            SimpleNamespace(
                width_px=interval,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
            )
            for interval in intervals
        )

        common_width = solver_module._measured_constraint_common_width(
            constraints,
            3,
        )

        self.assertIsNone(common_width)

    def test_common_width_groups_remove_strictly_contained_search_surfaces(
        self,
    ) -> None:
        groups = (
            (0b001, 0b001),
            (0b011, 0b101),
            (0b100, 0b010),
        )

        self.assertEqual(
            solver_module._maximal_common_width_group_masks(groups),
            (groups[1], groups[2]),
        )

    def test_search_budget_is_checked_before_graph_witness_generation(
        self,
    ) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> _EdgeConstraint:
            observation = paths[position]
            return _EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        constraints = (
            _MeasuredFrameConstraint(
                leading=edge(0.0),
                trailing=edge(100.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            _MeasuredFrameConstraint(
                leading=edge(110.0),
                trailing=edge(210.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )
        with patch.object(
            solver_module,
            "_sequence_graph_witnesses",
            wraps=solver_module._sequence_graph_witnesses,
        ) as graph_witnesses:
            _, evaluations, truncated = solver_module._measured_frame_sequences(
                constraints,
                2,
                content(width=210, height=100),
                0,
                (PixelInterval.exact(100.0),),
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(evaluations, 0)
        self.assertTrue(truncated)
        graph_witnesses.assert_not_called()

    def test_blank_placement_disagreement_counts_all_alternative_builds(
        self,
    ) -> None:
        preferred_builds = (
            SimpleNamespace(
                slots=(SimpleNamespace(index=1, sequence_inferred=True),),
            ),
            SimpleNamespace(
                slots=(SimpleNamespace(index=6, sequence_inferred=True),),
            ),
        )

        consensus = solver_module._sequence_assignment_consensus(
            preferred_builds,
        )

        self.assertEqual(consensus.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(consensus.solution_count, 2)
        self.assertEqual(consensus.conflicting_frame_indexes, (1, 6))

    def test_same_inferred_slot_position_does_not_create_frame_disagreement(
        self,
    ) -> None:
        def boundary(start: float, end: float):
            return SimpleNamespace(position=PixelInterval(start, end))

        real_slot = SimpleNamespace(
            index=1,
            sequence_inferred=False,
            leading=boundary(0.0, 2.0),
            trailing=boundary(98.0, 100.0),
        )
        alternatives = (
            SimpleNamespace(
                slots=(
                    real_slot,
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=True,
                        leading=boundary(110.0, 112.0),
                        trailing=boundary(208.0, 210.0),
                    ),
                ),
            ),
            SimpleNamespace(
                slots=(
                    real_slot,
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=True,
                        leading=boundary(230.0, 232.0),
                        trailing=boundary(328.0, 330.0),
                    ),
                ),
            ),
        )

        consensus = solver_module._sequence_assignment_consensus(alternatives)

        self.assertEqual(consensus.state, EvidenceState.SUPPORTED)
        self.assertEqual(consensus.conflicting_frame_indexes, ())

    def test_external_safety_uncertainty_is_not_internal_assignment_disagreement(
        self,
    ) -> None:
        def boundary(start: float, end: float | None = None):
            return SimpleNamespace(
                position=PixelInterval(
                    start,
                    start if end is None else end,
                ),
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                independently_observed=True,
            )

        def build(
            leading: tuple[float, float],
            internal: tuple[float, float],
            trailing: tuple[float, float],
        ):
            return SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=boundary(*leading),
                        trailing=boundary(*internal),
                    ),
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=False,
                        leading=boundary(110.0, 112.0),
                        trailing=boundary(*trailing),
                    ),
                )
            )

        endpoint_alternatives = (
            build((0.0, 2.0), (98.0, 100.0), (208.0, 210.0)),
            build((8.0, 10.0), (98.0, 100.0), (218.0, 220.0)),
        )
        internal_alternatives = (
            build((0.0, 2.0), (98.0, 100.0), (208.0, 210.0)),
            build((0.0, 2.0), (103.0, 105.0), (208.0, 210.0)),
        )

        endpoint_consensus = solver_module._sequence_assignment_consensus(
            endpoint_alternatives,
        )
        internal_consensus = solver_module._sequence_assignment_consensus(
            internal_alternatives,
        )

        self.assertEqual(endpoint_consensus.state, EvidenceState.SUPPORTED)
        self.assertEqual(endpoint_consensus.conflicting_frame_indexes, ())
        self.assertEqual(internal_consensus.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(internal_consensus.conflicting_frame_indexes, (1,))

        observations = tuple(
            path(BoundaryAxis.LONG, position, f"external_endpoint:{position}")
            for position in (2.0, 8.0)
        )
        boundaries = tuple(
            ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=BoundarySide.LEADING,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=observation.provenance,
                ),
                inference_provenance=None,
            )
            for observation in observations
        )

        safe_boundary = solver_module._external_safety_boundary(
            BoundarySide.LEADING,
            boundaries,
            PixelInterval(0.0, 20.0),
        )
        self.assertEqual(
            safe_boundary.source,
            FrameBoundarySource.EXTERNAL_SAFETY_ENVELOPE,
        )
        self.assertEqual(safe_boundary.position, PixelInterval(2.0, 8.0))
        self.assertEqual(safe_boundary.role_state, EvidenceState.UNAVAILABLE)
        self.assertTrue(safe_boundary.geometry_resolved)

    def test_external_safety_boundary_is_clamped_to_holder_safety(self) -> None:
        observations = tuple(
            path(BoundaryAxis.LONG, position, f"clamped_endpoint:{position}")
            for position in (198.0, 207.0)
        )
        boundaries = tuple(
            ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=BoundarySide.TRAILING,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=observation.provenance,
                ),
                inference_provenance=None,
            )
            for observation in observations
        )

        safe_boundary = solver_module._external_safety_boundary(
            BoundarySide.TRAILING,
            boundaries,
            PixelInterval(0.0, 200.0),
        )

        self.assertEqual(safe_boundary.position, PixelInterval(198.0, 200.0))

    def test_distinct_observations_with_one_shared_interval_form_consensus(
        self,
    ) -> None:
        def observed_boundary(
            position: PixelInterval,
            source: str,
            side: BoundarySide,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, position.midpoint, source)
            observation = replace(
                observation,
                samples=(
                    replace(
                        observation.samples[0],
                        position=position,
                    ),
                ),
            )
            return ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=side,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=observation.provenance,
                ),
                inference_provenance=None,
            )

        fixed_leading = observed_boundary(
            PixelInterval.exact(0.0),
            "fixed_leading",
            BoundarySide.LEADING,
        )
        alternatives = tuple(
            SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=fixed_leading,
                        trailing=observed_boundary(
                            position,
                            source,
                            BoundarySide.TRAILING,
                        ),
                    ),
                ),
            )
            for position, source in (
                (PixelInterval(98.0, 106.0), "first_trailing_path"),
                (PixelInterval(102.0, 110.0), "second_trailing_path"),
            )
        )

        consensus = solver_module._sequence_assignment_consensus(alternatives)

        self.assertEqual(
            consensus.outcome,
            AssignmentConsensusOutcome.AGREED,
        )
        self.assertEqual(consensus.conflicting_frame_indexes, ())

    def test_broad_uncertainty_cannot_bridge_disjoint_placements(self) -> None:
        fixed = SimpleNamespace(
            position=PixelInterval.exact(0.0),
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            independently_observed=True,
        )
        alternatives = tuple(
            SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=fixed,
                        trailing=SimpleNamespace(
                            position=position,
                            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                            independently_observed=True,
                        ),
                    ),
                ),
            )
            for position in (
                PixelInterval(98.0, 100.0),
                PixelInterval(98.0, 110.0),
                PixelInterval(108.0, 110.0),
            )
        )

        consensus = solver_module._sequence_assignment_consensus(alternatives)

        self.assertEqual(
            consensus.outcome,
            AssignmentConsensusOutcome.DISAGREED,
        )
        self.assertEqual(consensus.conflicting_frame_indexes, (1,))

    def test_dimension_only_alternatives_form_one_geometry_uncertainty(self) -> None:
        def boundary(position: PixelInterval, label: str) -> ResolvedFrameBoundary:
            return ResolvedFrameBoundary(
                position=position,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=None,
                inference_provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (MeasurementIdentity.FRAME_DIMENSIONS,),
                    "synthetic dimension-only boundary",
                ),
            )

        alternatives = tuple(
            SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=boundary(
                            PixelInterval.exact(0.0),
                            f"fixed_leading:{offset}",
                        ),
                        trailing=boundary(
                            PixelInterval(offset, offset + 10.0),
                            f"dimension_trailing:{offset}",
                        ),
                    ),
                ),
            )
            for offset in (90.0, 120.0)
        )

        consensus = solver_module._sequence_assignment_consensus(alternatives)
        envelope = solver_module._internal_geometry_uncertainty_boundary(
            BoundarySide.TRAILING,
            tuple(build.slots[0].trailing for build in alternatives),
        )

        self.assertEqual(consensus.state, EvidenceState.SUPPORTED)
        self.assertEqual(envelope.position, PixelInterval(90.0, 130.0))
        self.assertEqual(
            envelope.source,
            FrameBoundarySource.DIMENSION_CONSTRAINED,
        )
        self.assertFalse(envelope.independently_observed)

    def test_common_width_refinement_preserves_sequence_monotonicity(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        first, second = geometry.frame_slots
        unresolved_path = path(
            BoundaryAxis.LONG,
            135.0,
            "synthetic_unresolved_trailing",
        )
        inferred_trailing = ResolvedFrameBoundary(
            position=PixelInterval(120.0, 150.0),
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=BoundaryAnchor(
                observation=unresolved_path,
                physical_role=BoundarySide.TRAILING,
                role_state=EvidenceState.UNAVAILABLE,
                role_authority=BoundaryRoleAuthority.UNAVAILABLE,
                role_provenance=unresolved_path.provenance,
            ),
            inference_provenance=None,
        )
        slots = (
            replace(
                first,
                trailing=inferred_trailing,
                visible_long_axis=PixelInterval(
                    first.leading.position.minimum,
                    inferred_trailing.position.maximum,
                ),
            ),
            second,
        )
        broad_common_width = replace(
            geometry.common_frame_width,
            width_px=PixelInterval(150.0, 350.0),
        )

        resolved = solver_module._resolve_dimension_boundaries_from_common_width(
            slots,
            broad_common_width,
            {},
        )

        self.assertEqual(resolved, slots)

    def test_separator_incumbent_prunes_only_groups_without_matching_support(
        self,
    ) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(50.0, 100.0, 110.0, 160.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        support = separator(100.0, 110.0, plan, supported=True)
        preceding_trailing, following_leading = (
            solver_module._observed_band_edges(support)
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> _EdgeConstraint:
            observation = paths[position]
            return _EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        def frame(
            leading: _EdgeConstraint,
            trailing: _EdgeConstraint,
            width: float,
        ) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=PixelInterval.exact(width),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        options = (
            frame(edge(0.0), preceding_trailing, 100.0),
            frame(following_leading, edge(210.0), 100.0),
            frame(edge(0.0), edge(50.0), 50.0),
            frame(edge(160.0), edge(210.0), 50.0),
        )
        widths = (PixelInterval.exact(100.0), PixelInterval.exact(50.0))
        visible_content = content(
            width=210,
            height=100,
            runs=((0, 100), (110, 210)),
        )

        _, unbounded_evaluations, _ = solver_module._measured_frame_sequences(
            options,
            2,
            visible_content,
            10_000,
            widths,
            allow_nominal_slot_sized_gap=False,
        )
        bounded, bounded_evaluations, truncated = (
            solver_module._measured_frame_sequences(
                options,
                2,
                visible_content,
                10_000,
                widths,
                allow_nominal_slot_sized_gap=False,
                minimum_supported_separator_count=1,
            )
        )

        self.assertTrue(bounded)
        self.assertFalse(truncated)
        self.assertLessEqual(bounded_evaluations, unbounded_evaluations)
        self.assertTrue(
            all(
                sequence[0].trailing.separator is not None
                and sequence[0].trailing.separator
                is sequence[1].leading.separator
                for sequence in bounded
            )
        )

        with patch.object(
            solver_module,
            "_sequence_graph_witnesses",
            return_value=(options[2:], options[:2]),
        ):
            bounded, _, _ = solver_module._measured_frame_sequences(
                options,
                2,
                visible_content,
                10_000,
                widths,
                allow_nominal_slot_sized_gap=False,
                minimum_supported_separator_count=1,
            )

        self.assertEqual(bounded, (options[:2],))

    def test_dimension_search_uses_observed_separator_incumbent(self) -> None:
        class Build:
            __hash__ = object.__hash__

            def __init__(self) -> None:
                leading = SimpleNamespace(position=PixelInterval.exact(0.0))
                trailing = SimpleNamespace(position=PixelInterval.exact(100.0))
                self.slots = (
                    SimpleNamespace(leading=leading, trailing=trailing),
                )
                self.objectives = _SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=4,
                    internal_boundary_measurement_quality=4.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                )

        search_scope = scope(
            width=100,
            height=100,
            leading=0.0,
            trailing=100.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        prepared_search_index = sequence_search_index(search_scope)
        search_space = solver_module._MeasuredFrameSearchSpace(
            leading_candidates=(),
            trailing_candidates=(),
            observed_constraints=(),
            width_hypotheses=(
                _CommonWidthHypothesis(
                    PixelInterval.exact(100.0),
                    (ObservationId("measured_width"),),
                    2,
                ),
            ),
            recurring_width_hypotheses=(),
        )
        incumbent_inputs: list[int] = []

        def measured_builds(*args, **kwargs):
            incumbent_inputs.append(kwargs["minimum_supported_separator_count"])
            return (
                ((Build(),) if len(incumbent_inputs) == 1 else ()),
                1,
                False,
            )

        with (
            patch.object(
                solver_module,
                "_measured_frame_search_space",
                return_value=search_space,
            ),
            patch.object(
                solver_module,
                "_dimension_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                solver_module,
                "_canonical_measured_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                solver_module,
                "_complete_separator_sequence_builds_dominate_dimension_inference",
                return_value=False,
            ),
            patch.object(
                solver_module,
                "_measured_builds_for_options",
                side_effect=measured_builds,
            ),
        ):
            solver_module._measured_path_builds(
                search_scope,
                prepared_search_index,
                (plan.span,),
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                6,
                content(width=100, height=100),
                100,
                (
                    PixelInterval.exact(100.0),
                    PixelInterval.exact(101.0),
                ),
                physical_scale_constraint=None,
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(incumbent_inputs[0], 0)
        self.assertTrue(all(value == 4 for value in incumbent_inputs[1:]))

    def test_separator_incumbent_prevents_raw_seed_fallback(self) -> None:
        class Build:
            __hash__ = object.__hash__

            def __init__(self) -> None:
                leading = SimpleNamespace(position=PixelInterval.exact(0.0))
                trailing = SimpleNamespace(position=PixelInterval.exact(100.0))
                self.slots = (
                    SimpleNamespace(leading=leading, trailing=trailing),
                )
                self.objectives = _SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=1.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                )

        search_scope = scope(
            width=220,
            height=100,
            leading=0.0,
            trailing=220.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        support = separator(100.0, 110.0, plan, supported=True)
        prepared_search_index = sequence_search_index(
            search_scope,
            (support,),
        )
        geometry_leading, geometry_trailing = (
            solver_module._separator_geometry_edge_candidates(
                prepared_search_index.separator_supports.canonical_supports,
                search_scope,
            )
        )
        search_space = solver_module._MeasuredFrameSearchSpace(
            leading_candidates=geometry_leading,
            trailing_candidates=geometry_trailing,
            observed_constraints=(),
            width_hypotheses=(),
            recurring_width_hypotheses=(
                solver_module._RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(100.0),
                    2,
                ),
                solver_module._RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(105.0),
                    2,
                ),
            ),
        )
        calls: list[int] = []

        def measured_builds(*args, **kwargs):
            calls.append(kwargs["minimum_supported_separator_count"])
            return (((Build(),) if len(calls) == 1 else ()), 1, False)

        with (
            patch.object(
                solver_module,
                "_measured_frame_search_space",
                return_value=search_space,
            ),
            patch.object(
                solver_module,
                "_dimension_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                solver_module,
                "_canonical_measured_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                solver_module,
                "_complete_separator_sequence_builds_dominate_dimension_inference",
                return_value=False,
            ),
            patch.object(
                solver_module,
                "_measured_builds_for_options",
                side_effect=measured_builds,
            ),
        ):
            solver_module._measured_path_builds(
                search_scope,
                prepared_search_index,
                (plan.span,),
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                2,
                content(width=220, height=100),
                100,
                (),
                physical_scale_constraint=None,
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(calls, [0, 1])

    def test_dimension_width_hypotheses_use_separate_bounded_graph_branches(
        self,
    ) -> None:
        search_scope = scope(
            width=400,
            height=100,
            leading=0.0,
            trailing=400.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        prepared_search_index = sequence_search_index(search_scope)
        search_space = solver_module._MeasuredFrameSearchSpace(
            leading_candidates=(),
            trailing_candidates=(),
            observed_constraints=(),
            width_hypotheses=(
                _CommonWidthHypothesis(
                    PixelInterval.exact(300.0),
                    (ObservationId("measured_width"),),
                    2,
                ),
            ),
            recurring_width_hypotheses=(),
        )
        branch_widths: list[tuple[PixelInterval, ...]] = []

        def measured_builds(*args, **kwargs):
            branch_widths.append(args[6])
            return (), 1, False

        with (
            patch.object(
                solver_module,
                "_measured_frame_search_space",
                return_value=search_space,
            ),
            patch.object(
                solver_module,
                "_dimension_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                solver_module,
                "_canonical_measured_frame_constraints",
                return_value=(SimpleNamespace(),),
            ),
            patch.object(
                solver_module,
                "_measured_builds_for_options",
                side_effect=measured_builds,
            ),
        ):
            solver_module._measured_path_builds(
                search_scope,
                prepared_search_index,
                (plan.span,),
                (PixelInterval.exact(100.0),),
                PixelInterval.exact(100.0),
                4,
                content(width=400, height=100),
                100,
                (PixelInterval.exact(400.0),),
                physical_scale_constraint=None,
                allow_nominal_slot_sized_gap=False,
            )

        self.assertEqual(
            branch_widths,
            [
                (PixelInterval.exact(300.0),),
                (PixelInterval.exact(300.0),),
                (PixelInterval.exact(400.0),),
            ],
        )

    def test_graph_witnesses_keep_measured_edge_alternative_to_geometry_contact(
        self,
    ) -> None:
        search_scope = scope(
            width=330,
            height=100,
            leading=0.0,
            trailing=330.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(230.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        internal_separator = separator(100.0, 110.0, plan, supported=True)
        trailing_holder_band = separator(320.0, 330.0, plan, supported=True)
        first_trailing, second_leading = solver_module._observed_band_edges(
            internal_separator
        )
        holder_trailing, _ = solver_module._observed_band_edges(
            trailing_holder_band
        )
        holder_trailing = replace(
            holder_trailing,
            external_side=BoundarySide.TRAILING,
        )
        raw_path = next(
            path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
            and path.position == PixelInterval.exact(230.0)
        )

        def dimension(position: float, label: str) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension edge",
                ),
            )

        def frame(
            leading: _EdgeConstraint,
            trailing: _EdgeConstraint,
        ) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        first = frame(dimension(0.0, "first-leading"), first_trailing)
        second = frame(second_leading, dimension(210.0, "second-trailing"))
        measured_last = frame(
            _EdgeConstraint(
                position=raw_path.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=raw_path.provenance,
                path=raw_path,
            ),
            holder_trailing,
        )
        contact_last = frame(
            dimension(210.0, "contact-leading"),
            dimension(310.0, "contact-trailing"),
        )
        ordered = (first, second, measured_last, contact_last)
        grouped = (
            ((0, first),),
            ((1, second),),
            ((2, measured_last), (3, contact_last)),
        )

        witnesses = solver_module._sequence_graph_witnesses(
            grouped,
            ordered,
            solver_module._sequence_graph_context(
                ordered,
                content(width=330, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertTrue(
            any(sequence[-1] is measured_last for sequence in witnesses)
        )

    def test_sequence_graph_keeps_the_physical_best_non_extreme_path(self) -> None:
        def edge(position: float) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
                    observation_id=ObservationId(f"graph-edge:{position}"),
                    dependencies=(),
                    description="synthetic dimension-constrained graph edge",
                ),
            )

        def frame(start: float, end: float) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        left = (
            frame(0.0, 100.0),
            frame(120.0, 220.0),
            frame(240.0, 340.0),
        )
        middle = (
            frame(10.0, 110.0),
            frame(110.0, 210.0),
            frame(210.0, 310.0),
        )
        right = (
            frame(20.0, 120.0),
            frame(140.0, 240.0),
            frame(260.0, 360.0),
        )
        ordered = tuple(
            frame_option
            for layer in zip(left, middle, right, strict=True)
            for frame_option in layer
        )
        grouped = tuple(
            tuple((layer * 3 + route, ordered[layer * 3 + route]) for route in range(3))
            for layer in range(3)
        )
        visible_content = content(width=360, height=100, runs=())
        graph_context = solver_module._sequence_graph_context(
            ordered,
            visible_content,
            allow_nominal_slot_sized_gap=True,
        )

        witnesses = solver_module._sequence_graph_witnesses(
            grouped,
            ordered,
            graph_context,
        )

        self.assertIn(middle, witnesses)

    def test_frame_width_hint_cannot_outrank_supported_external_boundary(
        self,
    ) -> None:
        search_scope = scope(
            width=240,
            height=100,
            leading=0.0,
            trailing=240.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        holder_band = separator(0.0, 10.0, plan, supported=True)
        _, external_leading = solver_module._observed_band_edges(holder_band)
        external_leading = replace(
            external_leading,
            external_side=BoundarySide.LEADING,
            state=EvidenceState.SUPPORTED,
        )
        raw_path = path(
            BoundaryAxis.LONG,
            0.0,
            "unsupported-leading-path",
        )
        unsupported_leading = _EdgeConstraint(
            position=raw_path.position,
            basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=raw_path.provenance,
            path=raw_path,
        )

        def dimension(position: PixelInterval, label: str) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=position,
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension edge",
                ),
            )

        shared_trailing = dimension(PixelInterval.exact(110.0), "first-trailing")
        supported_first = _MeasuredFrameConstraint(
            leading=external_leading,
            trailing=shared_trailing,
            width_px=PixelInterval.exact(100.0),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=True,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
            frame_width_hint_residual=10.0,
        )
        hinted_first = _MeasuredFrameConstraint(
            leading=unsupported_leading,
            trailing=shared_trailing,
            width_px=PixelInterval.exact(110.0),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
            frame_width_hint_residual=0.0,
        )
        second = _MeasuredFrameConstraint(
            leading=dimension(PixelInterval.exact(120.0), "second-leading"),
            trailing=dimension(PixelInterval(220.0, 230.0), "second-trailing"),
            width_px=PixelInterval(100.0, 110.0),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
            frame_width_hint_residual=0.0,
        )
        ordered = (supported_first, hinted_first, second)

        selected = solver_module._sequence_graph_best_path(
            (
                ((0, supported_first), (1, hinted_first)),
                ((2, second),),
            ),
            ordered,
            solver_module._sequence_graph_context(
                ordered,
                content(width=240, height=100, runs=()),
                allow_nominal_slot_sized_gap=True,
            ),
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIs(selected[0], supported_first)

    def test_sequence_graph_skips_nodes_outside_complete_paths(
        self,
    ) -> None:
        def edge(position: float) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"feasible-edge:{position}"),
                    (),
                    "synthetic graph edge",
                ),
            )

        def frame(start: float, end: float) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        valid = (
            frame(0.0, 100.0),
            frame(110.0, 210.0),
            frame(220.0, 320.0),
        )
        dead_middle = tuple(
            frame(-300.0 - offset, -200.0 - offset)
            for offset in range(50)
        )
        dead_trailing = tuple(
            frame(-600.0 - offset, -500.0 - offset)
            for offset in range(50)
        )
        ordered = (*valid, *dead_middle, *dead_trailing)
        grouped = (
            ((0, valid[0]),),
            (
                (1, valid[1]),
                *tuple(
                    (3 + offset, option)
                    for offset, option in enumerate(dead_middle)
                ),
            ),
            (
                (2, valid[2]),
                *tuple(
                    (3 + len(dead_middle) + offset, option)
                    for offset, option in enumerate(dead_trailing)
                ),
            ),
        )
        context = solver_module._sequence_graph_context(
            ordered,
            content(width=320, height=100, runs=()),
            allow_nominal_slot_sized_gap=True,
        )

        with patch.object(
            solver_module,
            "_best_graph_predecessor",
            wraps=solver_module._best_graph_predecessor,
        ) as best_predecessor:
            witnesses = solver_module._sequence_graph_witnesses(
                grouped,
                ordered,
                context,
            )

        self.assertIn(valid, witnesses)
        self.assertLessEqual(best_predecessor.call_count, 4)

    def test_holder_span_scale_is_weak_search_hint_without_becoming_evidence(
        self,
    ) -> None:
        search_scope = scope(
            width=1_320,
            height=100,
            leading=0.0,
            trailing=1_320.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 210.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        with patch.object(
            solver_module,
            "_measured_path_builds",
            return_value=((), 0, False),
        ) as measured_builds:
            solved = _solve(
                search_scope=search_scope,
                visible_content=content(
                    width=1_320,
                    height=100,
                    runs=((0, 100),),
                ),
                count=12,
                frame_dimensions=dimensions(1.0, 1.0),
                strip_mode="partial",
                nominal_count=13,
            )

        self.assertIsInstance(solved, FrameSequenceSolveFailure)
        search_widths = measured_builds.call_args.args[3]
        self.assertEqual(search_widths[0], PixelInterval.exact(100.0))
        self.assertEqual(search_widths[-1], PixelInterval.exact(110.0))

    def test_frame_sized_unexplained_gap_cannot_form_direct_sequence(self) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 400.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> _EdgeConstraint:
            observation = paths[position]
            return _EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        constraints = tuple(
            _MeasuredFrameConstraint(
                leading=edge(start),
                trailing=edge(end),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )
            for start, end in ((0.0, 100.0), (110.0, 210.0), (400.0, 500.0))
        )

        self.assertIsNone(
            _measured_sequence_build(
                constraints,
                shared_short_axis_plan(search_scope).span,
                search_scope.holder_safety.box,
                allow_nominal_slot_sized_gap=False,
            )
        )

    def test_dimension_inference_does_not_translate_one_anchor_across_slots(
        self,
    ) -> None:
        search_scope = scope(
            width=300,
            height=100,
            leading=0.0,
            trailing=300.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 200.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        long_paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> _EdgeConstraint:
            observation = long_paths[position]
            return _EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        leading = edge(0.0)
        first_trailing = edge(100.0)
        focused_trailing = edge(200.0)
        hypothesis = _DimensionPlacementHypothesis(
            width_px=PixelInterval.exact(100.0),
            boundary_anchors=(
                leading.provenance.observation_id,
                first_trailing.provenance.observation_id,
            ),
        )

        constraints = _dimension_frame_constraints(
            ((leading, True),),
            ((first_trailing, False), (focused_trailing, False)),
            ((leading, True),),
            ((first_trailing, False), (focused_trailing, False)),
            (hypothesis,),
            PixelInterval(0.0, 300.0),
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
        )

        self.assertTrue(
            any(
                constraint.leading.position == PixelInterval.exact(0.0)
                and constraint.trailing.position == PixelInterval.exact(100.0)
                for constraint in constraints
            )
        )
        focused = next(
            constraint
            for constraint in constraints
            if constraint.leading.position == PixelInterval.exact(100.0)
            and constraint.trailing.position == PixelInterval.exact(200.0)
        )
        self.assertEqual(focused.leading.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(focused.leading.basis, FrameBoundarySource.DIMENSION_CONSTRAINED)
        self.assertEqual(focused.trailing.state, EvidenceState.UNAVAILABLE)

    def test_focused_raw_boundary_does_not_delete_dimension_hypothesis(
        self,
    ) -> None:
        inferred = _EdgeConstraint(
            position=PixelInterval(95.0, 105.0),
            basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("focused_dimension_edge"),
                (),
                "synthetic focused dimension edge",
            ),
        )
        raw_path = next(
            path
            for path in scope(
                width=200,
                height=100,
                leading=0.0,
                trailing=200.0,
                top=0.0,
                bottom=100.0,
                internal_paths=(100.0,),
                holder_sides=_ALL_HOLDER_SIDES,
            ).raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
            and path.position == PixelInterval.exact(100.0)
        )
        observed = _EdgeConstraint(
            position=raw_path.position,
            basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=raw_path.provenance,
            path=raw_path,
        )

        focused = solver_module._focused_edge_constraints(
            inferred,
            ((observed, False),),
        )

        self.assertEqual(focused, (observed, inferred))

    def test_unassigned_gray_path_has_no_physical_measurement_quality(self) -> None:
        gray_path = scope(
            width=200,
            height=100,
            leading=0.0,
            trailing=200.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        ).raw_boundary_paths[-1]
        constraint = _EdgeConstraint(
            position=gray_path.position,
            basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=gray_path.provenance,
            path=gray_path,
        )

        self.assertEqual(constraint.measurement_quality, 0.0)

    def test_unassigned_gray_paths_cannot_create_frame_width_search_authority(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 200.0, 300.0, 400.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }

        def edge(position: float) -> _EdgeConstraint:
            path = paths[position]
            return _EdgeConstraint(
                position=path.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=path.provenance,
                path=path,
            )

        constraints = (
            _MeasuredFrameConstraint(
                leading=edge(100.0),
                trailing=edge(200.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            _MeasuredFrameConstraint(
                leading=edge(300.0),
                trailing=edge(400.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )

        self.assertEqual(_measured_width_hypotheses(constraints), ())
        search_space = _measured_frame_search_space(
            sequence_search_index(search_scope),
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
            None,
        )
        self.assertEqual(search_space.width_hypotheses, ())
        self.assertFalse(
            hasattr(search_space, "observation_width_placement_hypotheses")
        )
        self.assertFalse(
            hasattr(search_space, "observation_width_search_intervals")
        )

    def test_assignment_consensus_prefers_stronger_physical_measurement_support(
        self,
    ) -> None:
        stronger_separator = SimpleNamespace(
            slots=(),
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=0.0,
                supported_separator_count=3,
                internal_boundary_measurement_quality=2.0,
                dimension_residual=0.1,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.2,
            )
        )
        tighter_boundary = SimpleNamespace(
            slots=(),
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=0.0,
                supported_separator_count=2,
                internal_boundary_measurement_quality=2.0,
                dimension_residual=0.1,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.1,
            )
        )
        dominated = SimpleNamespace(
            slots=(),
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=1.0,
                unexplained_spacing_extent_px=1.0,
                supported_separator_count=2,
                internal_boundary_measurement_quality=1.0,
                dimension_residual=0.2,
                external_boundary_measurement_quality=0.5,
                boundary_uncertainty_ratio=0.3,
            )
        )

        retained = _physically_preferred_builds(
            (stronger_separator, tighter_boundary, dominated)
        )

        self.assertEqual(
            {id(item) for item in retained},
            {id(stronger_separator)},
        )

    def test_strictly_larger_unexplained_spacing_is_dominated(self) -> None:
        edge = SimpleNamespace(position=PixelInterval.exact(0.0))
        slots = (SimpleNamespace(leading=edge, trailing=edge),)
        compact = SimpleNamespace(
            slots=slots,
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=10.0,
                supported_separator_count=1,
                internal_boundary_measurement_quality=1.0,
                dimension_residual=0.0,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.0,
            )
        )
        fragmented = SimpleNamespace(
            slots=slots,
            objectives=_SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=100.0,
                supported_separator_count=1,
                internal_boundary_measurement_quality=1.0,
                dimension_residual=0.0,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.0,
            )
        )

        self.assertEqual(
            _physically_preferred_builds((fragmented, compact)),
            (compact,),
        )
        self.assertIs(
            solver_module._representative_build((fragmented, compact)),
            compact,
        )

    def test_strictly_larger_dimension_residual_is_dominated(
        self,
    ) -> None:
        def build(position: float, residual: float):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=2.0,
                    dimension_residual=residual,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                    inferred_boundary_count=1,
                ),
            )

        lower_residual = build(100.0, 0.01)
        higher_residual = build(200.0, 0.02)

        self.assertEqual(
            _physically_preferred_builds((higher_residual, lower_residual)),
            (lower_residual,),
        )
        self.assertIs(
            solver_module._representative_build(
                (higher_residual, lower_residual)
            ),
            lower_residual,
        )

    def test_physical_residual_tradeoff_remains_a_geometry_alternative(
        self,
    ) -> None:
        edge = SimpleNamespace(position=PixelInterval.exact(0.0))

        def build(unexplained: float, dimension_residual: float):
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=unexplained,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=1.0,
                    dimension_residual=dimension_residual,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        compact = build(10.0, 0.02)
        dimension_consistent = build(20.0, 0.01)

        self.assertEqual(
            _physically_preferred_builds((compact, dimension_consistent)),
            (compact, dimension_consistent),
        )

    def test_inferred_boundary_count_orders_without_erasing_alternative(
        self,
    ) -> None:
        def build(position: float, inferred_boundary_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=2.0,
                    dimension_residual=0.01,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                    inferred_boundary_count=inferred_boundary_count,
                ),
            )

        more_measured = build(100.0, 1)
        more_inferred = build(200.0, 2)

        self.assertEqual(
            _physically_preferred_builds((more_inferred, more_measured)),
            (more_inferred, more_measured),
        )
        self.assertIs(
            solver_module._representative_build((more_inferred, more_measured)),
            more_measured,
        )

    def test_boundary_measurement_count_does_not_erase_geometry_alternative(
        self,
    ) -> None:
        def build(position: float, internal_quality: float):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=internal_quality,
                    dimension_residual=0.01,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                    inferred_boundary_count=1,
                ),
            )

        more_roles = build(100.0, 3.0)
        fewer_roles = build(200.0, 2.0)

        self.assertEqual(
            _physically_preferred_builds((fewer_roles, more_roles)),
            (fewer_roles, more_roles),
        )
        self.assertIs(
            solver_module._representative_build((fewer_roles, more_roles)),
            more_roles,
        )

    def test_same_topology_with_strict_boundary_role_superset_dominates(
        self,
    ) -> None:
        def boundary(
            position: float,
            observation_id: str | None,
        ) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(position),
                independently_observed=observation_id is not None,
                role_provenance=(
                    None
                    if observation_id is None
                    else SimpleNamespace(
                        root_measurement=MeasurementIdentity.PHOTO_EDGES,
                        dependencies=(),
                    )
                ),
                measurement_provenance=(
                    None
                    if observation_id is None
                    else SimpleNamespace(
                        observation_id=ObservationId(observation_id)
                    )
                ),
            )

        def build(*, second_anchor: bool) -> SimpleNamespace:
            first_anchor = "first_internal_anchor"
            second = "second_internal_anchor" if second_anchor else None
            return SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=boundary(0.0, None),
                        trailing=boundary(100.0, first_anchor),
                    ),
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=False,
                        leading=boundary(110.0, first_anchor),
                        trailing=boundary(210.0, second),
                    ),
                    SimpleNamespace(
                        index=3,
                        sequence_inferred=False,
                        leading=boundary(220.0, second),
                        trailing=boundary(320.0, None),
                    ),
                ),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=2.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        subset = build(second_anchor=False)
        superset = build(second_anchor=True)

        self.assertEqual(
            _physically_preferred_builds((subset, superset)),
            (superset,),
        )

    def test_independent_separator_sequence_precedes_small_unexplained_spacing(
        self,
    ) -> None:
        def build(unexplained: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(0.0))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=unexplained,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=float(separator_count),
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        model_fitted = build(0.0, 2)
        measured_sequence = build(141.0, 4)

        self.assertEqual(
            _physically_preferred_builds((model_fitted, measured_sequence)),
            (measured_sequence,),
        )
        self.assertIs(
            solver_module._representative_build(
                (model_fitted, measured_sequence)
            ),
            measured_sequence,
        )

    def test_graph_search_preserves_independent_separator_measurements(self) -> None:
        search_scope = scope(
            width=400,
            height=100,
            leading=0.0,
            trailing=400.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        band_leading, band_trailing = solver_module._observed_band_edges(
            separator(100.0, 110.0, plan, supported=True)
        )

        def inferred_edge(position: float, label: str) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic graph boundary",
                ),
            )

        def constraint(
            leading: _EdgeConstraint,
            trailing: _EdgeConstraint,
        ) -> _MeasuredFrameConstraint:
            return _MeasuredFrameConstraint(
                leading=leading,
                trailing=trailing,
                width_px=trailing.position.minus(leading.position),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        measured_sequence = (
            constraint(inferred_edge(0.0, "measured_1_leading"), band_leading),
            constraint(band_trailing, inferred_edge(210.0, "measured_2_trailing")),
            constraint(
                inferred_edge(260.0, "measured_3_leading"),
                inferred_edge(360.0, "measured_3_trailing"),
            ),
        )
        compact_without_measurement = tuple(
            constraint(
                inferred_edge(start, f"compact_{index}_leading"),
                inferred_edge(start + 100.0, f"compact_{index}_trailing"),
            )
            for index, start in enumerate((0.0, 101.0, 202.0), start=1)
        )

        self.assertGreater(
            solver_module._graph_sequence_rank(measured_sequence),
            solver_module._graph_sequence_rank(compact_without_measurement),
        )

    def test_disjoint_observed_frame_width_is_not_dimension_compatible(self) -> None:
        def observed_edge(
            minimum: float,
            maximum: float,
            label: str,
        ) -> _EdgeConstraint:
            observation = path(
                BoundaryAxis.LONG,
                (minimum + maximum) / 2.0,
                label,
            )
            return _EdgeConstraint(
                position=PixelInterval(minimum, maximum),
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        frame_width = PixelInterval(3_101.6, 3_170.0)
        refined = solver_module._refine_frame_edges(
            observed_edge(13_323.0, 13_352.0, "narrow_frame_leading"),
            observed_edge(16_390.0, 16_419.0, "narrow_frame_trailing"),
            frame_width,
            allow_underwidth=False,
        )

        self.assertIsNotNone(refined)
        assert refined is not None
        leading, trailing = refined
        constraint = _MeasuredFrameConstraint(
            leading=leading,
            trailing=trailing,
            width_px=trailing.position.minus(leading.position),
            full_width_hypothesis_admissible=True,
            leading_holder_clip_supported=False,
            trailing_holder_clip_supported=False,
            search_order_residual=0.0,
        )
        self.assertFalse(
            solver_module._sequence_constraints_fit_physical_scale(
                (constraint,),
                physical_model.FrameWidthPhysicalScaleConstraint(
                    width_px=frame_width,
                    provenance=MeasurementProvenance(
                        root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
                        observation_id=ObservationId(
                            "physical_scale:disjoint_observed_width"
                        ),
                        dependencies=(
                            MeasurementIdentity.PHOTO_EDGES,
                            MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                        ),
                        description="independent synthetic physical scale",
                    ),
                ),
            )
        )

    def test_unmeasured_overlapping_widths_remain_geometry_alternatives(
        self,
    ) -> None:
        search_scope = scope(
            width=340,
            height=100,
            leading=0.0,
            trailing=340.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )

        def edge(minimum: float, maximum: float, label: str) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval(minimum, maximum),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension boundary",
                ),
            )

        def constraint(
            leading: tuple[float, float],
            trailing: tuple[float, float],
            label: str,
        ) -> _MeasuredFrameConstraint:
            width = PixelInterval(*trailing).minus(PixelInterval(*leading))
            return _MeasuredFrameConstraint(
                leading=edge(*leading, f"{label}:leading"),
                trailing=edge(*trailing, f"{label}:trailing"),
                width_px=width,
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            )

        shared = (
            constraint((0.0, 0.0), (100.0, 102.0), "first"),
            constraint((110.0, 110.0), (210.0, 212.0), "second"),
        )
        aligned = _measured_sequence_build(
            (*shared, constraint((220.0, 220.0), (318.0, 324.0), "aligned")),
            shared_short_axis_plan(search_scope).span,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )
        overcontained = _measured_sequence_build(
            (*shared, constraint((220.0, 220.0), (320.0, 328.0), "wide")),
            shared_short_axis_plan(search_scope).span,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )

        self.assertIsNotNone(aligned)
        self.assertIsNotNone(overcontained)
        assert aligned is not None
        assert overcontained is not None
        self.assertEqual(
            aligned.objectives.dimension_residual,
            0.0,
        )
        self.assertEqual(
            overcontained.objectives.dimension_residual,
            0.0,
        )
        alternatives = _physically_preferred_builds((overcontained, aligned))
        self.assertEqual(alternatives, (overcontained, aligned))

    def test_search_hint_residual_does_not_prevent_physical_dominance(self) -> None:
        actual_frame_scale = _SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=0.0,
            unexplained_spacing_extent_px=0.0,
            supported_separator_count=0,
            internal_boundary_measurement_quality=0.0,
            dimension_residual=0.0,
            external_boundary_measurement_quality=0.0,
            boundary_uncertainty_ratio=0.006,
            frame_width_hint_residual=0.0,
        )
        whole_holder_span = _SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=0.0,
            unexplained_spacing_extent_px=0.0,
            supported_separator_count=0,
            internal_boundary_measurement_quality=0.0,
            dimension_residual=0.0,
            external_boundary_measurement_quality=0.0,
            boundary_uncertainty_ratio=0.004,
            frame_width_hint_residual=11.0,
        )

        self.assertTrue(whole_holder_span.dominates(actual_frame_scale))
        self.assertFalse(actual_frame_scale.dominates(whole_holder_span))

    def test_spacing_interval_crossing_zero_is_uncertainty_not_physical_residual(
        self,
    ) -> None:
        spacing = SimpleNamespace(
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            signed_width_px=PixelInterval(-100.0, 5.0),
        )

        self.assertEqual(_uncorroborated_overlap_extent((spacing,)), 0.0)
        self.assertEqual(_unexplained_spacing_extent((spacing,)), 0.0)

    def test_spacing_residuals_only_count_unavoidable_overlap_or_gap(self) -> None:
        overlap = SimpleNamespace(
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            signed_width_px=PixelInterval(-100.0, -20.0),
        )
        gap = SimpleNamespace(
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            signed_width_px=PixelInterval(5.0, 40.0),
        )

        self.assertEqual(_uncorroborated_overlap_extent((overlap, gap)), 20.0)
        self.assertEqual(_unexplained_spacing_extent((overlap, gap)), 5.0)

    def test_representative_uses_physical_objectives_before_coordinates(self) -> None:
        def build(position: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=10.0,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=float(separator_count),
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        weak_leftmost = build(0.0, 1)
        supported_sequence = build(100.0, 5)

        self.assertIs(
            solver_module._representative_build(
                (weak_leftmost, supported_sequence)
            ),
            supported_sequence,
        )

    def test_uncorroborated_overlap_is_not_bought_with_extra_separator_evidence(
        self,
    ) -> None:
        def build(overlap: float, unexplained: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(0.0))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=overlap,
                    unexplained_spacing_extent_px=unexplained,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=1.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        zero_overlap_large_gap = build(0.0, 100.0, 1)
        overlapping_extra_separator = build(10.0, 20.0, 2)

        self.assertIs(
            solver_module._representative_build(
                (zero_overlap_large_gap, overlapping_extra_separator)
            ),
            zero_overlap_large_gap,
        )
        self.assertEqual(
            _physically_preferred_builds(
                (zero_overlap_large_gap, overlapping_extra_separator)
            ),
            (zero_overlap_large_gap,),
        )

    def test_sequence_conservation_precedes_extra_separator_support(self) -> None:
        def build(unresolved: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(0.0))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=_SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=unresolved,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=float(separator_count),
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        conserved = build(20.0, 4)
        extra_separator_with_broken_conservation = build(200.0, 5)

        self.assertIs(
            solver_module._representative_build(
                (extra_separator_with_broken_conservation, conserved)
            ),
            conserved,
        )
        self.assertEqual(
            _physically_preferred_builds(
                (extra_separator_with_broken_conservation, conserved)
            ),
            (conserved,),
        )

    def test_unsupported_separator_bands_do_not_gain_separator_authority(
        self,
    ) -> None:
        search_scope = scope(
            width=540,
            height=100,
            leading=0.0,
            trailing=540.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(
                100.0,
                110.0,
                210.0,
                220.0,
                320.0,
                330.0,
                430.0,
                440.0,
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=False),
            separator(210.0, 220.0, plan, supported=False),
            separator(320.0, 330.0, plan, supported=False),
            separator(430.0, 440.0, plan, supported=False),
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=540, height=100),
            count=5,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
            strip_mode="partial",
            nominal_count=12,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.separator_assignments, ())
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertTrue(
            all(
                boundary.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
                for constraint in solved.common_frame_width.constraints
                for boundary in (constraint.leading, constraint.trailing)
            )
        )

    def test_build_stage_spacing_uncertainty_does_not_assign_photo_edge_roles(
        self,
    ) -> None:
        search_scope = scope(
            width=430,
            height=100,
            leading=0.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 105.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        paths = {
            path.position.midpoint: path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        }
        plan = shared_short_axis_plan(search_scope)
        separator_support = separator(210.0, 220.0, plan, supported=True)

        def raw(position: float, interval: PixelInterval) -> _EdgeConstraint:
            observation = paths[position]
            return _EdgeConstraint(
                position=interval,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        def separator_edge(side: BoundarySide) -> _EdgeConstraint:
            observation = separator_support.observation
            return _EdgeConstraint(
                position=(
                    observation.leading_edge
                    if side == BoundarySide.TRAILING
                    else observation.trailing_edge
                ),
                basis=FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                separator=observation,
                separator_cross_axis=separator_support.measurement,
            )

        constraints = (
            _MeasuredFrameConstraint(
                leading=raw(0.0, PixelInterval.exact(0.0)),
                trailing=raw(100.0, PixelInterval(95.0, 105.0)),
                width_px=PixelInterval(95.0, 105.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            _MeasuredFrameConstraint(
                leading=raw(105.0, PixelInterval(100.0, 110.0)),
                trailing=separator_edge(BoundarySide.TRAILING),
                width_px=PixelInterval(100.0, 110.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            _MeasuredFrameConstraint(
                leading=separator_edge(BoundarySide.LEADING),
                trailing=raw(320.0, PixelInterval(315.0, 325.0)),
                width_px=PixelInterval(95.0, 105.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            _MeasuredFrameConstraint(
                leading=raw(330.0, PixelInterval(320.0, 330.0)),
                trailing=raw(430.0, PixelInterval.exact(430.0)),
                width_px=PixelInterval(100.0, 110.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )

        build = _measured_sequence_build(
            constraints,
            plan.span,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )

        self.assertIsNotNone(build)
        assert build is not None
        self.assertTrue(
            all(
                not boundary.independently_observed
                for slot in build.slots
                for boundary in (slot.leading, slot.trailing)
                if boundary.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
            )
        )

        certain_overlap_constraints = (
            replace(
                constraints[0],
                trailing=raw(105.0, PixelInterval(101.0, 111.0)),
                width_px=PixelInterval(101.0, 111.0),
            ),
            replace(
                constraints[1],
                leading=raw(100.0, PixelInterval(95.0, 100.0)),
                width_px=PixelInterval(110.0, 115.0),
            ),
            replace(
                constraints[2],
                trailing=raw(330.0, PixelInterval(321.0, 331.0)),
                width_px=PixelInterval(101.0, 111.0),
            ),
            replace(
                constraints[3],
                leading=raw(320.0, PixelInterval(315.0, 320.0)),
                width_px=PixelInterval(110.0, 115.0),
            ),
        )
        overlap_build = _measured_sequence_build(
            certain_overlap_constraints,
            plan.span,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )

        self.assertIsNotNone(overlap_build)
        assert overlap_build is not None
        self.assertFalse(overlap_build.slots[0].trailing.independently_observed)
        self.assertFalse(overlap_build.slots[1].leading.independently_observed)
        self.assertFalse(overlap_build.slots[2].trailing.independently_observed)
        self.assertFalse(overlap_build.slots[3].leading.independently_observed)

    def test_independent_coincident_measurements_corroborate_adjacent_edge_role(
        self,
    ) -> None:
        search_scope = scope(
            width=220,
            height=100,
            leading=0.0,
            trailing=220.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        gray_path = next(
            observation
            for observation in search_scope.raw_boundary_paths
            if observation.axis == BoundaryAxis.LONG
            and observation.position == PixelInterval.exact(100.0)
        )
        band_support = separator(95.0, 105.0, plan, supported=True)
        measured_trailing = ResolvedFrameBoundary(
            position=PixelInterval(97.0, 103.0),
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=BoundaryAnchor(
                observation=gray_path,
                physical_role=BoundarySide.TRAILING,
                role_state=EvidenceState.SUPPORTED,
                role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                role_provenance=gray_path.provenance,
            ),
            inference_provenance=None,
        )
        unresolved_leading = ResolvedFrameBoundary(
            position=PixelInterval(99.0, 106.0),
            source=FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=BoundaryAnchor(
                observation=band_support.observation,
                physical_role=BoundarySide.LEADING,
                role_state=EvidenceState.UNAVAILABLE,
                role_authority=BoundaryRoleAuthority.UNAVAILABLE,
                role_provenance=band_support.observation.provenance,
            ),
            inference_provenance=None,
        )

        left, right = solver_module._corroborate_adjacent_boundary_pair(
            measured_trailing,
            unresolved_leading,
        )

        self.assertIs(left, measured_trailing)
        self.assertTrue(right.independently_observed)
        self.assertEqual(
            right.measurement_provenance.root_measurement,
            MeasurementIdentity.SEPARATOR_PROFILE,
        )
        self.assertEqual(
            right.role_provenance.root_measurement,
            MeasurementIdentity.PHOTO_EDGES,
        )
        self.assertEqual(right.position, unresolved_leading.position)

    def test_content_cannot_create_a_distinct_full_edge_slot_identity(
        self,
    ) -> None:
        search_scope = scope(
            width=660,
            height=100,
            leading=0.0,
            trailing=660.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(540.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
                (430.0, 440.0),
            )
        )
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=660, height=100, runs=((50, 650),)),
            count=6,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(any(slot.sequence_inferred for slot in solved.frame_slots))
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)

    def test_holder_contact_support_does_not_depend_on_width_search_hint(self) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        search_space = _measured_frame_search_space(
            sequence_search_index(search_scope),
            (PixelInterval.exact(50.0),),
            PixelInterval.exact(50.0),
            None,
        )
        holder_adjacent = next(
            constraint
            for constraint in search_space.observed_constraints
            if constraint.leading.position.intersects(PixelInterval.exact(0.0))
            and constraint.trailing.position.intersects(PixelInterval.exact(100.0))
        )

        self.assertTrue(holder_adjacent.leading_holder_clip_supported)
        self.assertEqual(
            holder_adjacent.leading.external_side,
            BoundarySide.LEADING,
        )

    def test_holder_endpoint_cannot_seed_interior_dimension_boundaries(self) -> None:
        search_scope = scope(
            width=330,
            height=100,
            leading=0.0,
            trailing=330.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        holder_band = separator(320.0, 330.0, plan, supported=True)
        trailing_endpoint, _ = solver_module._observed_band_edges(holder_band)
        trailing_endpoint = replace(
            trailing_endpoint,
            external_side=BoundarySide.TRAILING,
        )

        constraints = _dimension_frame_constraints(
            (),
            ((trailing_endpoint, True),),
            (),
            ((trailing_endpoint, True),),
            (
                _DimensionPlacementHypothesis(
                    PixelInterval.exact(100.0),
                    (),
                ),
            ),
            PixelInterval(0.0, 330.0),
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
        )

        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0].leading.position, PixelInterval.exact(220.0))
        self.assertIs(constraints[0].trailing, trailing_endpoint)

    def test_holder_adjacent_band_edges_close_separator_sequence_endpoints(
        self,
    ) -> None:
        search_scope = scope(
            width=1_500,
            height=400,
            leading=20.0,
            trailing=1_490.0,
            top=20.0,
            bottom=380.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(10.0, 20.0, plan, supported=True),
            separator(470.0, 510.0, plan, supported=True),
            separator(960.0, 1_000.0, plan, supported=True),
            separator(1_450.0, 1_490.0, plan, supported=True),
        )

        with patch.object(
            solver_module,
            "_measured_path_builds",
            return_value=((), 0, False),
        ):
            solved = solve_frame_sequence(
                sequence_search_index(search_scope, supports),
                search_scope,
                plan,
                3,
                dimensions(70.0, 56.0),
                content(
                    width=1_500,
                    height=400,
                    runs=((20, 470), (510, 960), (1_000, 1_450)),
                ),
                10_000,
                strip_mode="full",
                nominal_count=3,
            )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(len(solved.separator_assignments), 2)
        self.assertEqual(
            tuple(
                (slot.leading.position, slot.trailing.position)
                for slot in solved.frame_slots
            ),
            (
                (PixelInterval.exact(20.0), PixelInterval.exact(470.0)),
                (PixelInterval.exact(510.0), PixelInterval.exact(960.0)),
                (PixelInterval.exact(1_000.0), PixelInterval.exact(1_450.0)),
            ),
        )

    def test_partial_single_frame_bands_without_sequence_proof_stay_unavailable(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 500.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 100.0,
            },
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(400.0, 410.0, plan, supported=True),
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=500,
                height=100,
                runs=((110, 210),),
                guidance_runs=((110, 400),),
            ),
            count=1,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        slot = solved.frame_slots[0]
        self.assertEqual(slot.leading.position, PixelInterval.exact(110.0))
        self.assertEqual(slot.trailing.position, PixelInterval.exact(210.0))
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)
        self.assertEqual(solved.separator_assignments, ())

    def test_holder_contact_and_content_guidance_do_not_create_photo_edges(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(20.0,),
            holder_sides=_ALL_HOLDER_SIDES,
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 500.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 100.0,
            },
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(210.0, 220.0, plan, supported=True),
            separator(400.0, 410.0, plan, supported=True),
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=500,
                height=100,
                runs=((20, 210),),
                guidance_runs=((0, 400),),
                position_uncertainty_px=5,
            ),
            count=1,
            frame_dimensions=dimensions(2.1, 1.0),
            supports=supports,
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        slot = solved.frame_slots[0]
        self.assertEqual(slot.leading.position, PixelInterval.exact(0.0))
        self.assertEqual(slot.trailing.position, PixelInterval.exact(210.0))
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)

    def test_isolated_holder_band_uses_photo_facing_position_without_edge_proof(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(20.0,),
            holder_sides=_ALL_HOLDER_SIDES,
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 500.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 100.0,
            },
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(0.0, 10.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(400.0, 410.0, plan, supported=True),
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=500,
                height=100,
                runs=((20, 210),),
                guidance_runs=((10, 400),),
                position_uncertainty_px=5,
            ),
            count=1,
            frame_dimensions=dimensions(2.0, 1.0),
            supports=supports,
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        slot = solved.frame_slots[0]
        self.assertEqual(slot.leading.position, PixelInterval.exact(10.0))
        self.assertEqual(slot.trailing.position, PixelInterval.exact(210.0))
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)
        self.assertEqual(solved.separator_assignments, ())

    def test_holder_adjacent_band_does_not_preprove_a_photo_edge(self) -> None:
        search_scope = scope(
            width=300,
            height=100,
            leading=0.0,
            trailing=300.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        holder_band = separator(100.0, 300.0, plan, supported=True)

        search_index = sequence_search_index(search_scope, (holder_band,))
        trailing_endpoint = next(
            edge
            for edge, _holder_adjacent in search_index.trailing_candidates
            if edge.separator == holder_band.observation
            and edge.external_side == BoundarySide.TRAILING
        )

        self.assertEqual(trailing_endpoint.state, EvidenceState.UNAVAILABLE)

    def test_non_dominated_widths_preserve_disjoint_measurements(self) -> None:
        measured_width = _CommonWidthHypothesis(
            PixelInterval(100.0, 110.0),
            (ObservationId("measured-a"), ObservationId("measured-b")),
            4,
        )
        weaker_overlapping_width = _CommonWidthHypothesis(
            PixelInterval(102.0, 108.0),
            (ObservationId("measured-c"), ObservationId("measured-d")),
            2,
        )
        disjoint_width = _CommonWidthHypothesis(
            PixelInterval(200.0, 210.0),
            (ObservationId("measured-e"), ObservationId("measured-f")),
            3,
        )

        self.assertEqual(
            _non_dominated_width_hypotheses(
                (
                    measured_width,
                    weaker_overlapping_width,
                    disjoint_width,
                )
            ),
            (measured_width, disjoint_width),
        )

    def test_frame_width_search_hint_cannot_reject_measured_sequence(self) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=210,
            height=100,
            runs=((0, 100), (110, 210)),
        )
        plan = shared_short_axis_plan(search_scope)
        support = separator(100.0, 110.0, plan, supported=True)

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, (support,)),
            search_scope,
            plan,
            2,
            dimensions(3.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=2,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.width_px.midpoint for slot in solved.frame_slots),
            (100.0, 100.0),
        )
        self.assertEqual(solved.frame_width_search_hint.width_px.midpoint, 300.0)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)

    def test_repeated_unassigned_gray_paths_are_not_pruned_by_width_search_hint(
        self,
    ) -> None:
        search_scope = scope(
            width=430,
            height=100,
            leading=0.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=430,
            height=100,
            runs=((0, 100), (110, 210), (220, 320), (330, 430)),
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=visible_content,
            count=4,
            frame_dimensions=dimensions(3.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.width_px for slot in solved.frame_slots),
            (PixelInterval.exact(100.0),) * 4,
        )
        self.assertEqual(solved.frame_width_search_hint.width_px, PixelInterval.exact(300.0))

    def test_repeated_boundary_width_is_a_search_hypothesis_not_proof(self) -> None:
        search_scope = scope(
            width=430,
            height=100,
            leading=0.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        search_index = sequence_search_index(search_scope, ())
        repeated = next(
            hypothesis
            for hypothesis in search_index.recurring_width_hypotheses
            if hypothesis.width_px == PixelInterval.exact(100.0)
        )

        self.assertGreaterEqual(repeated.contributor_count, 4)
        self.assertFalse(hasattr(repeated, "boundary_anchors"))
        self.assertEqual(search_index.width_hypotheses, ())

    def test_repeated_complete_slots_corroborate_photo_edge_roles(self) -> None:
        search_scope = scope(
            width=430,
            height=100,
            leading=0.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=430,
                height=100,
                runs=((0, 100), (110, 210), (220, 320), (330, 430)),
            ),
            count=4,
            frame_dimensions=dimensions(3.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            tuple(
                constraint.frame_index
                for constraint in solved.common_frame_width.constraints
            ),
            (2, 3),
        )
        self.assertTrue(
            all(
                boundary.role_authority
                == BoundaryRoleAuthority.MEASUREMENT_CORROBORATED
                for slot in solved.frame_slots[1:3]
                for boundary in (slot.leading, slot.trailing)
            )
        )

    def test_incompatible_repeated_slot_widths_do_not_corroborate_roles(
        self,
    ) -> None:
        search_scope = scope(
            width=470,
            height=100,
            leading=0.0,
            trailing=470.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 340.0, 350.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=470,
                height=100,
                runs=((0, 100), (110, 210), (220, 340), (350, 470)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)
        self.assertTrue(
            all(
                boundary.role_authority == BoundaryRoleAuthority.UNAVAILABLE
                for slot in solved.frame_slots[1:3]
                for boundary in (slot.leading, slot.trailing)
            )
        )

    def test_holder_adjacent_edges_do_not_create_common_width_without_complete_slot(
        self,
    ) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=210,
                height=100,
                runs=((0, 100), (110, 210)),
            ),
            count=2,
            frame_dimensions=dimensions(3.0, 1.0),
            supports=(separator(100.0, 110.0, plan, supported=True),),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(solved.common_frame_width.constraints, ())

    def test_holder_clipped_edge_frame_does_not_collapse_common_width(self) -> None:
        search_scope = scope(
            width=430,
            height=100,
            leading=15.0,
            trailing=415.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((100.0, 110.0), (210.0, 220.0), (320.0, 330.0))
        )
        frame_dimensions = dimensions(3.0, 1.0)
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=430,
                height=100,
                runs=((15, 100), (110, 210), (220, 320), (330, 415)),
            ),
            count=4,
            frame_dimensions=frame_dimensions,
            supports=supports,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.width_px, PixelInterval.exact(100.0))
        self.assertEqual(
            tuple(
                constraint.frame_index
                for constraint in solved.common_frame_width.constraints
            ),
            (2, 3),
        )
        dimension_evidence = frame_dimension_evidence(
            geometry(search_scope, supports, frame_dimensions, solved)
        )
        self.assertEqual(dimension_evidence.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            dimension_evidence.measured_width_intervals_px,
            tuple(
                constraint.width_px
                for constraint in solved.common_frame_width.constraints
            ),
        )

    def test_supported_common_width_applies_to_every_normal_frame_slot(self) -> None:
        search_scope = scope(
            width=20_000,
            height=2_067,
            leading=290.0,
            trailing=19_700.0,
            top=0.0,
            bottom=2_067.0,
            internal_paths=(
                330.0,
                1_600.0,
                2_543.0,
                3_817.0,
                5_691.0,
                5_793.0,
                8_885.0,
                10_391.0,
                11_025.0,
                11_955.0,
                12_917.0,
                14_199.0,
                15_603.0,
                15_752.0,
                16_600.0,
                17_355.0,
                17_660.0,
                18_610.0,
                19_213.0,
                19_493.0,
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (3_391.0, 3_600.0),
                (6_700.0, 6_900.0),
                (10_000.0, 10_200.0),
                (13_300.0, 13_500.0),
            )
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=20_000, height=2_067),
            count=6,
            frame_dimensions=dimensions(36.0, 24.0),
            supports=supports,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        assert solved.common_frame_width.width_px is not None
        self.assertEqual(
            tuple(
                assignment.boundary_index
                for assignment in solved.separator_assignments
            ),
            (1, 2, 3, 4),
        )
        self.assertTrue(
            all(
                slot.sequence_inferred
                or slot.edge_occlusion is not None
                or slot.width_px.intersects(solved.common_frame_width.width_px)
                for slot in solved.frame_slots
            ),
            tuple(slot.width_px for slot in solved.frame_slots),
        )
        dimension_boundaries = tuple(
            boundary
            for slot in solved.frame_slots
            for boundary in (slot.leading, slot.trailing)
            if boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        )
        self.assertTrue(dimension_boundaries)
        self.assertTrue(
            all(boundary.geometry_resolved for boundary in dimension_boundaries)
        )
        self.assertTrue(
            all(
                not boundary.independently_observed
                for boundary in dimension_boundaries
            )
        )

    def test_disjoint_exact_widths_cannot_be_reconciled_by_pixel_quantization(
        self,
    ) -> None:
        measurements = (
            PixelInterval.exact(100.0),
            PixelInterval.exact(102.0),
        )

        consensus = _common_measured_width_interval(measurements)

        self.assertIsNone(consensus)

    def test_search_width_majority_requires_a_real_shared_interval(self) -> None:
        measurements = (
            PixelInterval(90.0, 110.0),
            PixelInterval(111.0, 131.0),
            PixelInterval(132.0, 152.0),
        )

        consensus = _strict_majority_width_consensus(measurements)

        self.assertIsNone(consensus)

    def test_supported_common_width_resolves_compatible_dimension_boundary(
        self,
    ) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(320.0, 330.0, plan, supported=True),
        )
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=440,
                height=100,
                runs=((10, 100), (110, 210), (220, 320), (330, 430)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        assert solved.common_frame_width.width_px is not None
        source_slot = solved.frame_slots[1]
        inferred_trailing = ResolvedFrameBoundary(
            position=source_slot.leading.position.plus(
                solved.common_frame_width.width_px
            ),
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            geometry_state=BoundaryGeometryState.UNRESOLVED,
            boundary_anchor=None,
            inference_provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("unresolved-dimension-boundary"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "synthetic unresolved dimension boundary",
                boundary_anchors=(
                    source_slot.leading.measurement_provenance.observation_id,
                ),
            ),
        )
        unresolved_slot = replace(
            source_slot,
            trailing=inferred_trailing,
            visible_long_axis=PixelInterval(
                source_slot.leading.position.minimum,
                inferred_trailing.position.maximum,
            ),
        )

        resolved = solver_module._resolve_dimension_boundaries_from_common_width(
            (unresolved_slot,),
            solved.common_frame_width,
            {},
        )

        self.assertTrue(resolved[0].trailing.geometry_resolved)
        self.assertFalse(resolved[0].trailing.independently_observed)
        self.assertEqual(
            resolved[0].trailing.source,
            FrameBoundarySource.DIMENSION_CONSTRAINED,
        )

    def test_common_width_narrows_resolved_dimension_boundary(self) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=440,
                height=100,
                runs=((10, 100), (110, 210), (220, 320), (330, 430)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=(
                separator(100.0, 110.0, plan, supported=True),
                separator(210.0, 220.0, plan, supported=True),
                separator(320.0, 330.0, plan, supported=True),
            ),
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        assert solved.common_frame_width.width_px is not None
        source_slot = solved.frame_slots[1]
        expected = source_slot.leading.position.plus(
            solved.common_frame_width.width_px
        )
        broad_trailing = ResolvedFrameBoundary(
            position=PixelInterval(
                expected.minimum - 20.0,
                expected.maximum + 20.0,
            ),
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=None,
            inference_provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("broad-resolved-dimension-boundary"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "synthetic broad resolved dimension boundary",
            ),
        )
        broad_slot = replace(
            source_slot,
            trailing=broad_trailing,
            visible_long_axis=PixelInterval(
                source_slot.leading.position.minimum,
                broad_trailing.position.maximum,
            ),
        )

        narrowed = solver_module._resolve_dimension_boundaries_from_common_width(
            (broad_slot,),
            solved.common_frame_width,
            {},
        )

        self.assertEqual(narrowed[0].trailing.position, expected)
        self.assertTrue(narrowed[0].trailing.geometry_resolved)
        self.assertFalse(narrowed[0].trailing.independently_observed)

    def test_common_width_can_resolve_geometry_from_unproven_position_anchor(
        self,
    ) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=440, height=100),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=(
                separator(100.0, 110.0, plan, supported=True),
                separator(210.0, 220.0, plan, supported=True),
                separator(320.0, 330.0, plan, supported=True),
            ),
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        assert solved.common_frame_width.width_px is not None
        source_slot = solved.frame_slots[1]
        assert source_slot.leading.boundary_anchor is not None
        unproven_leading = replace(
            source_slot.leading,
            boundary_anchor=replace(
                source_slot.leading.boundary_anchor,
                role_state=EvidenceState.UNAVAILABLE,
                role_authority=BoundaryRoleAuthority.UNAVAILABLE,
            ),
        )
        inferred_trailing = ResolvedFrameBoundary(
            position=unproven_leading.position.plus(
                solved.common_frame_width.width_px
            ),
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            geometry_state=BoundaryGeometryState.UNRESOLVED,
            boundary_anchor=None,
            inference_provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("unproven-anchor-dimension-boundary"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "synthetic dimension boundary from an unproven position anchor",
                boundary_anchors=(
                    unproven_leading.measurement_provenance.observation_id,
                ),
            ),
        )
        unresolved_slot = replace(
            source_slot,
            leading=unproven_leading,
            trailing=inferred_trailing,
            visible_long_axis=PixelInterval(
                unproven_leading.position.minimum,
                inferred_trailing.position.maximum,
            ),
        )

        resolved = solver_module._resolve_dimension_boundaries_from_common_width(
            (unresolved_slot,),
            solved.common_frame_width,
            {},
        )

        self.assertTrue(resolved[0].trailing.geometry_resolved)
        self.assertFalse(resolved[0].leading.independently_observed)
        self.assertFalse(resolved[0].trailing.independently_observed)

    def test_common_width_replaces_incompatible_unproven_path_assignment(
        self,
    ) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=440,
                height=100,
                runs=((10, 100), (110, 210), (220, 320), (330, 430)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=(
                separator(100.0, 110.0, plan, supported=True),
                separator(210.0, 220.0, plan, supported=True),
                separator(320.0, 330.0, plan, supported=True),
            ),
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        source_slot = solved.frame_slots[1]
        target_slot = solved.frame_slots[2]
        assert target_slot.leading.boundary_anchor is not None
        assert solved.common_frame_width.width_px is not None
        expected = target_slot.trailing.position.minus(
            solved.common_frame_width.width_px
        )
        unsupported_leading = replace(
            target_slot.leading,
            position=PixelInterval(
                expected.maximum + 10.0,
                expected.maximum + 20.0,
            ),
            boundary_anchor=replace(
                target_slot.leading.boundary_anchor,
                role_state=EvidenceState.UNAVAILABLE,
                role_authority=BoundaryRoleAuthority.UNAVAILABLE,
            ),
        )
        unresolved_slot = replace(
            target_slot,
            leading=unsupported_leading,
            visible_long_axis=PixelInterval(
                unsupported_leading.position.minimum,
                target_slot.trailing.position.maximum,
            ),
        )

        resolved = solver_module._resolve_dimension_boundaries_from_common_width(
            (source_slot, unresolved_slot),
            solved.common_frame_width,
            {},
        )

        self.assertEqual(
            resolved[1].leading.source,
            FrameBoundarySource.DIMENSION_CONSTRAINED,
        )
        self.assertFalse(resolved[1].leading.independently_observed)
        self.assertEqual(resolved[1].leading.position, expected)

    def test_common_width_does_not_overwrite_supported_observed_boundary(
        self,
    ) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=440, height=100),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=(
                separator(100.0, 110.0, plan, supported=True),
                separator(210.0, 220.0, plan, supported=True),
                separator(320.0, 330.0, plan, supported=True),
            ),
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        source_slot = solved.frame_slots[1]
        target_slot = solved.frame_slots[2]
        self.assertTrue(target_slot.leading.independently_observed)
        assert solved.common_frame_width.width_px is not None
        expected = target_slot.trailing.position.minus(
            solved.common_frame_width.width_px
        )
        incompatible = replace(
            target_slot.leading,
            position=PixelInterval(
                expected.maximum + 10.0,
                expected.maximum + 20.0,
            ),
        )
        contradictory_slot = replace(
            target_slot,
            leading=incompatible,
            visible_long_axis=PixelInterval(
                incompatible.position.minimum,
                target_slot.trailing.position.maximum,
            ),
        )

        resolved = solver_module._resolve_dimension_boundaries_from_common_width(
            (source_slot, contradictory_slot),
            solved.common_frame_width,
            {},
        )

        self.assertEqual(resolved[1].leading, incompatible)

    def test_dimension_replacement_removes_superseded_path_assignment(
        self,
    ) -> None:
        geometry_model = candidate_fixture().geometry
        replaced_boundary = ResolvedFrameBoundary(
            position=geometry_model.frame_slots[0].leading.position,
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=None,
            inference_provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("dimension-replaced-leading-edge"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "dimension replacement",
            ),
        )
        slots = (
            replace(
                geometry_model.frame_slots[0],
                leading=replaced_boundary,
            ),
            *geometry_model.frame_slots[1:],
        )

        assignments = solver_module._long_axis_assignments_for_slots(
            geometry_model.long_axis_assignments,
            slots,
        )

        self.assertNotIn(
            (1, BoundarySide.LEADING),
            {(item.frame_index, item.side) for item in assignments},
        )

    def test_holder_occlusion_keeps_hidden_nominal_geometry_out_of_crop(self) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        frame_dimensions = dimensions(1.0, 1.0)
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(320.0, 330.0, plan, supported=True),
        )
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=440,
                height=100,
                runs=((10, 100), (110, 210), (220, 320), (330, 430)),
            ),
            count=4,
            frame_dimensions=frame_dimensions,
            supports=supports,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        first = solved.frame_slots[0]
        self.assertIsNotNone(first.edge_occlusion)
        self.assertEqual(first.nominal_long_axis.minimum, 0.0)
        self.assertEqual(first.visible_long_axis, PixelInterval(10.0, 100.0))
        self.assertEqual(
            first.crop_envelope(solved.shared_short_axis).box.left,
            10,
        )
        final_geometry = geometry(
            search_scope,
            supports,
            frame_dimensions,
            solved,
        )
        self.assertEqual(final_geometry.frame_crop_envelopes[0].box.left, 10)

    def test_holder_occlusion_requires_an_independently_observed_opposite_edge(
        self,
    ) -> None:
        search_scope = scope(
            width=440,
            height=100,
            leading=10.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(320.0, 330.0, plan, supported=True),
        )
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=440,
                height=100,
                runs=((10, 100), (110, 210), (220, 320), (330, 430)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertEqual(solved.common_frame_width.width_px, PixelInterval.exact(100.0))
        holder_boundary = next(
            boundary
            for boundary in search_scope.holder_safety.boundaries
            if boundary.side == BoundarySide.TRAILING
        )
        leading_path = path(
            BoundaryAxis.LONG,
            420.0,
            "unproven_trailing_frame_edge",
        )
        holder_path = holder_boundary.supporting_paths[0]

        def observed_boundary(
            path,
            side: BoundarySide,
            state: EvidenceState,
        ) -> ResolvedFrameBoundary:
            return ResolvedFrameBoundary(
                position=path.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=path,
                    physical_role=side,
                    role_state=state,
                    role_authority=(
                        BoundaryRoleAuthority.DIRECT_MEASUREMENT
                        if state == EvidenceState.SUPPORTED
                        else BoundaryRoleAuthority.UNAVAILABLE
                    ),
                    role_provenance=path.provenance,
                ),
                inference_provenance=None,
            )

        unproven_edge_slot = FrameSlot(
            index=5,
            visible_long_axis=PixelInterval(420.0, 430.0),
            leading=observed_boundary(
                leading_path,
                BoundarySide.LEADING,
                EvidenceState.UNAVAILABLE,
            ),
            trailing=observed_boundary(
                holder_path,
                BoundarySide.TRAILING,
                EvidenceState.SUPPORTED,
            ),
            content_occupancy=FrameContentOccupancy.UNAVAILABLE,
            edge_occlusion=None,
        )

        slots, _ = solver_module._apply_edge_occlusion_inference(
            (unproven_edge_slot,),
            (),
            {BoundarySide.TRAILING: holder_boundary},
            solved.common_frame_width,
            "full",
        )

        self.assertIsNone(slots[-1].edge_occlusion)
        self.assertEqual(slots[-1].trailing, unproven_edge_slot.trailing)

    def test_blank_search_does_not_receive_a_preallocated_budget(self) -> None:
        source = inspect.getsource(solve_frame_sequence)

        self.assertNotIn("direct_budget", source)
        self.assertNotIn("blank_budget", source)

    def test_missing_content_does_not_reopen_resolved_nominal_sequence(
        self,
    ) -> None:
        supported_boundary = SimpleNamespace(
            independently_observed=True,
            boundary_anchor=object(),
        )
        build = SimpleNamespace(
            slots=(
                SimpleNamespace(
                    leading=supported_boundary,
                    trailing=supported_boundary,
                    visible_long_axis=PixelInterval.exact(100.0),
                    sequence_inferred=False,
                ),
            ),
        )

        with (
            patch.object(
                solver_module,
                "_build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_physically_preferred_builds",
                return_value=(build,),
            ),
            patch.object(
                solver_module,
                "_build_supports_resolved_nominal_slots",
                return_value=True,
            ),
        ):
            resolved = solver_module._direct_nominal_geometry_is_complete(
                (build,),
                content(width=300, height=100, runs=()),
                {},
                SimpleNamespace(),
                SimpleNamespace(),
            )

        self.assertTrue(resolved)

    def test_resolved_direct_nominal_sequence_wins_over_blank_alternatives(
        self,
    ) -> None:
        search_scope = scope(
            width=660,
            height=120,
            leading=0.0,
            trailing=650.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(
                100.0,
                110.0,
                210.0,
                220.0,
                320.0,
                330.0,
                430.0,
                440.0,
                540.0,
                550.0,
            ),
            holder_sides=_ALL_HOLDER_SIDES,
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 660.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 120.0,
            },
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((100.0, 110.0), (210.0, 220.0), (320.0, 330.0))
        )

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, supports),
            search_scope,
            plan,
            6,
            dimensions(1.0, 1.0),
            content(width=660, height=120),
            100_000,
            strip_mode="full",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(any(slot.sequence_inferred for slot in solved.frame_slots))
        self.assertEqual(solved.assignment_consensus.state, EvidenceState.SUPPORTED)

    def test_resolved_direct_nominal_geometry_skips_blank_subsearch(self) -> None:
        class CapturedBuilds(Exception):
            pass

        direct = SimpleNamespace(
            slots=(),
            separator_bindings=(),
            objectives=SimpleNamespace(supported_separator_count=0),
        )
        search_scope = scope(
            width=660,
            height=120,
            leading=0.0,
            trailing=650.0,
            top=10.0,
            bottom=110.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        build_calls = 0

        def sequence_builds(*args, **kwargs):
            nonlocal build_calls
            build_calls += 1
            if build_calls > 1:
                raise AssertionError(
                    "resolved nominal geometry must not start blank subsearch"
                )
            return (direct,), 1, False

        def capture(builds):
            raise CapturedBuilds(builds)

        with (
            patch.object(
                solver_module,
                "_sequence_builds_for_count",
                side_effect=sequence_builds,
            ),
            patch.object(
                solver_module,
                "_direct_nominal_geometry_is_complete",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_does_not_contradict_common_width",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_satisfies_full_endpoint_extent",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                side_effect=lambda build, *_args: (build, SimpleNamespace()),
            ),
            patch.object(
                solver_module,
                "_physically_preferred_builds",
                side_effect=capture,
            ),
        ):
            with self.assertRaises(CapturedBuilds):
                solve_frame_sequence(
                    sequence_search_index(search_scope),
                    search_scope,
                    plan,
                    6,
                    dimensions(1.0, 1.0),
                    content(width=660, height=120),
                    100_000,
                    strip_mode="full",
                    nominal_count=6,
                )

        self.assertEqual(build_calls, 1)

    def test_one_complete_direct_geometry_prevents_blank_subsearch(self) -> None:
        anchored_slot = SimpleNamespace(
            sequence_inferred=False,
            leading=SimpleNamespace(
                independently_observed=True,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                boundary_anchor=object(),
            ),
            trailing=SimpleNamespace(
                independently_observed=False,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                boundary_anchor=None,
            ),
        )
        complete = SimpleNamespace(slots=(anchored_slot,))
        unresolved = SimpleNamespace(slots=(anchored_slot,))

        with (
            patch.object(
                solver_module,
                "_build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_physically_preferred_builds",
                return_value=(complete, unresolved),
            ),
            patch.object(
                solver_module,
                "_build_supports_resolved_nominal_slots",
                side_effect=lambda build, *args: build is complete,
            ),
        ):
            resolved = (
                solver_module._direct_nominal_geometry_is_complete(
                    (complete, unresolved),
                    content(width=100, height=20),
                    {},
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )

        self.assertTrue(resolved)

    def test_common_width_resolved_dimension_slot_completes_direct_geometry(
        self,
    ) -> None:
        dimension_boundary = SimpleNamespace(
            independently_observed=False,
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            boundary_anchor=None,
        )
        direct = SimpleNamespace(
            slots=(
                SimpleNamespace(
                    sequence_inferred=False,
                    visible_long_axis=PixelInterval(0.0, 100.0),
                    leading=dimension_boundary,
                    trailing=dimension_boundary,
                ),
            ),
        )

        with (
            patch.object(
                solver_module,
                "_build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_physically_preferred_builds",
                return_value=(direct,),
            ),
            patch.object(
                solver_module,
                "_build_supports_resolved_nominal_slots",
                return_value=True,
            ),
        ):
            resolved = (
                solver_module._direct_nominal_geometry_is_complete(
                    (direct,),
                    content(width=100, height=20, runs=((0, 100),)),
                    {},
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )

        self.assertTrue(resolved)

    def test_content_does_not_explain_dimension_only_slot_geometry(self) -> None:
        slot = SimpleNamespace(
            visible_long_axis=PixelInterval(100.0, 200.0),
            leading=SimpleNamespace(
                independently_observed=False,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                boundary_anchor=None,
            ),
            trailing=SimpleNamespace(
                independently_observed=False,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                boundary_anchor=None,
            ),
        )
        build = SimpleNamespace(slots=(slot,))

        self.assertTrue(
            solver_module._build_has_geometry_only_slot(build)
        )

    def test_frame_sized_endpoint_slack_keeps_nominal_geometry_incomplete(
        self,
    ) -> None:
        def boundary(position: float) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(position),
                geometry_state=BoundaryGeometryState.RESOLVED,
            )

        build = SimpleNamespace(
            slots=(
                SimpleNamespace(
                    leading=boundary(10.0),
                    trailing=boundary(110.0),
                ),
                SimpleNamespace(
                    leading=boundary(120.0),
                    trailing=boundary(220.0),
                ),
            ),
            objectives=SimpleNamespace(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=0.0,
                unresolved_spacing_extent_px=0.0,
            ),
        )
        holder_boundaries = {
            BoundarySide.LEADING: SimpleNamespace(
                position=PixelInterval.exact(0.0)
            ),
            BoundarySide.TRAILING: SimpleNamespace(
                position=PixelInterval.exact(400.0)
            ),
        }
        common_width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PixelInterval.exact(100.0),
        )

        with (
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                return_value=(build, common_width),
            ),
            patch.object(
                solver_module,
                "_slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
        ):
            self.assertFalse(
                solver_module._build_supports_resolved_nominal_slots(
                    build,
                    holder_boundaries,
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )

    def test_uncorroborated_overlap_cannot_complete_direct_nominal_geometry(
        self,
    ) -> None:
        def boundary(position: float) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(position),
                geometry_state=BoundaryGeometryState.RESOLVED,
            )

        build = SimpleNamespace(
            slots=(
                SimpleNamespace(
                    leading=boundary(0.0),
                    trailing=boundary(100.0),
                ),
                SimpleNamespace(
                    leading=boundary(80.0),
                    trailing=boundary(180.0),
                ),
            ),
            objectives=SimpleNamespace(
                uncorroborated_overlap_extent_px=20.0,
                unexplained_spacing_extent_px=0.0,
                unresolved_spacing_extent_px=20.0,
            ),
        )
        common_width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PixelInterval.exact(100.0),
        )

        with (
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                return_value=(build, common_width),
            ),
            patch.object(
                solver_module,
                "_slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_full_sequence_endpoint_slack_is_sub_frame",
                return_value=True,
            ),
        ):
            self.assertFalse(
                solver_module._build_supports_resolved_nominal_slots(
                    build,
                    {},
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )

    def test_spacing_created_by_common_width_resolution_keeps_direct_incomplete(
        self,
    ) -> None:
        boundary = SimpleNamespace(
            geometry_state=BoundaryGeometryState.RESOLVED,
        )
        build = SimpleNamespace(
            slots=(SimpleNamespace(leading=boundary, trailing=boundary),),
            objectives=SimpleNamespace(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=0.0,
                unresolved_spacing_extent_px=0.0,
            ),
        )
        resolved_build = SimpleNamespace(
            slots=build.slots,
            objectives=SimpleNamespace(
                uncorroborated_overlap_extent_px=10.0,
                unexplained_spacing_extent_px=0.0,
                unresolved_spacing_extent_px=10.0,
            ),
        )
        common_width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PixelInterval.exact(100.0),
        )

        with (
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                return_value=(resolved_build, common_width),
            ),
            patch.object(
                solver_module,
                "_slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_full_sequence_endpoint_slack_is_sub_frame",
                return_value=True,
            ),
        ):
            self.assertFalse(
                solver_module._build_supports_resolved_nominal_slots(
                    build,
                    {},
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )

    def test_common_width_resolves_unmeasured_boundary_before_width_check(
        self,
    ) -> None:
        def boundary(
            position: float,
            *,
            independently_observed: bool,
        ) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(position),
                independently_observed=independently_observed,
            )

        raw_slots = (
            SimpleNamespace(
                width_px=PixelInterval.exact(80.0),
                leading=boundary(20.0, independently_observed=False),
                trailing=boundary(100.0, independently_observed=True),
            ),
        )
        resolved_slots = (
            SimpleNamespace(
                width_px=PixelInterval.exact(100.0),
                leading=boundary(0.0, independently_observed=False),
                trailing=boundary(100.0, independently_observed=True),
            ),
        )
        build = SimpleNamespace(slots=raw_slots)
        common_width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PixelInterval.exact(100.0),
        )

        with (
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                return_value=(SimpleNamespace(slots=resolved_slots), common_width),
            ),
        ):
            self.assertTrue(
                solver_module._build_does_not_contradict_common_width(
                    build,
                    {},
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )

    def test_holder_occlusion_may_extend_hidden_nominal_frame_outside_canvas(
        self,
    ) -> None:
        leading = SimpleNamespace(
            position=PixelInterval.exact(10.0),
            independently_observed=False,
        )
        trailing = SimpleNamespace(
            position=PixelInterval.exact(50.0),
            independently_observed=True,
        )
        slot = SimpleNamespace(
            width_px=PixelInterval.exact(40.0),
            leading=leading,
            trailing=trailing,
        )
        holder_boundaries = {
            BoundarySide.LEADING: SimpleNamespace(
                position=PixelInterval.exact(10.0),
            ),
        }
        common_width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PixelInterval.exact(100.0),
        )

        with patch.object(
            solver_module,
            "_boundary_matches_holder",
            return_value=True,
        ):
            compatible = (
                solver_module._slots_do_not_contradict_supported_common_width(
                    (slot,),
                    holder_boundaries,
                    common_width,
                )
            )

        self.assertTrue(compatible)

    def test_common_width_resolution_cannot_create_non_monotonic_sequence(
        self,
    ) -> None:
        def boundary(position: float) -> SimpleNamespace:
            return SimpleNamespace(position=PixelInterval.exact(position))

        build = SimpleNamespace(slots=(SimpleNamespace(), SimpleNamespace()))
        resolved_slots = (
            SimpleNamespace(
                leading=boundary(100.0),
                trailing=boundary(200.0),
            ),
            SimpleNamespace(
                leading=boundary(90.0),
                trailing=boundary(210.0),
            ),
        )
        common_width = SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            width_px=PixelInterval.exact(100.0),
        )

        with (
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                return_value=(SimpleNamespace(slots=resolved_slots), common_width),
            ),
            patch.object(
                solver_module,
                "_slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
        ):
            self.assertFalse(
                solver_module._build_does_not_contradict_common_width(
                    build,
                    {},
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )

    def test_full_solver_rejects_a_sequence_isolated_inside_holder_slack(
        self,
    ) -> None:
        search_scope = scope(
            width=1_000,
            height=100,
            leading=0.0,
            trailing=1_000.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)

        def edge(position: float, label: str) -> _EdgeConstraint:
            return _EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (),
                    "synthetic dimension edge",
                ),
            )

        constraints = (
            _MeasuredFrameConstraint(
                leading=edge(400.0, "isolated-1-leading"),
                trailing=edge(500.0, "isolated-1-trailing"),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            _MeasuredFrameConstraint(
                leading=edge(510.0, "isolated-2-leading"),
                trailing=edge(610.0, "isolated-2-trailing"),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )
        build = _measured_sequence_build(
            constraints,
            plan.span,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )
        self.assertIsNotNone(build)
        assert build is not None

        with patch.object(
            solver_module,
            "_sequence_builds_for_count",
            return_value=((build,), 1, False),
        ):
            solved = solve_frame_sequence(
                sequence_search_index(search_scope),
                search_scope,
                plan,
                2,
                dimensions(36.0, 24.0),
                content(width=1_000, height=100, runs=()),
                100,
                strip_mode="full",
                nominal_count=2,
            )

        self.assertIsInstance(solved, FrameSequenceSolveFailure)

    def test_stronger_direct_separator_sequence_survives_blank_alternatives(
        self,
    ) -> None:
        class CapturedBuilds(Exception):
            pass

        anchored_slot = SimpleNamespace(
            sequence_inferred=False,
            leading=SimpleNamespace(
                independently_observed=True,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                boundary_anchor=object(),
            ),
            trailing=SimpleNamespace(
                independently_observed=False,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                boundary_anchor=None,
            ),
        )
        direct = SimpleNamespace(
            slots=(anchored_slot,),
            separator_bindings=(object(),) * 4,
            objectives=SimpleNamespace(supported_separator_count=4),
        )
        sequence_completed = SimpleNamespace(
            slots=(anchored_slot,),
            separator_bindings=(object(),) * 2,
            objectives=SimpleNamespace(supported_separator_count=2),
        )
        search_scope = scope(
            width=660,
            height=120,
            leading=0.0,
            trailing=650.0,
            top=10.0,
            bottom=110.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)

        def capture(builds):
            raise CapturedBuilds(builds)

        with (
            patch.object(
                solver_module,
                "_sequence_builds_for_count",
                side_effect=(
                    ((direct,), 0, False),
                    ((), 0, False),
                ),
            ),
            patch.object(
                solver_module,
                "_sequence_completed_builds",
                return_value=(sequence_completed,),
            ),
            patch.object(
                solver_module,
                "_build_supports_resolved_nominal_slots",
                return_value=False,
            ),
            patch.object(
                solver_module,
                "_direct_nominal_geometry_is_complete",
                return_value=False,
            ),
            patch.object(
                solver_module,
                "_infer_unique_slot_in_direct_nominal_build",
                side_effect=lambda build, *_args: build,
            ),
            patch.object(
                solver_module,
                "_preferred_direct_common_width_is_supported",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_does_not_contradict_common_width",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_satisfies_full_endpoint_extent",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                side_effect=lambda build, *_args: (build, SimpleNamespace()),
            ),
            patch.object(
                solver_module,
                "_physically_preferred_builds",
                side_effect=capture,
            ),
        ):
            with self.assertRaises(CapturedBuilds) as captured:
                solve_frame_sequence(
                    sequence_search_index(search_scope),
                    search_scope,
                    plan,
                    6,
                    dimensions(1.0, 1.0),
                    content(width=660, height=120),
                    100_000,
                    strip_mode="full",
                    nominal_count=6,
                )

        competing = captured.exception.args[0]
        self.assertIn(direct, competing)
        self.assertIn(sequence_completed, competing)

    def test_common_width_resolution_precedes_final_build_ranking(self) -> None:
        class CapturedBuilds(Exception):
            pass

        anchored_slot = SimpleNamespace(
            sequence_inferred=False,
            leading=SimpleNamespace(
                independently_observed=True,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                boundary_anchor=object(),
            ),
            trailing=SimpleNamespace(
                independently_observed=True,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                boundary_anchor=object(),
            ),
        )
        direct = SimpleNamespace(
            slots=(anchored_slot,),
            separator_bindings=(),
            objectives=SimpleNamespace(supported_separator_count=0),
        )
        sequence_completed = SimpleNamespace(
            slots=(anchored_slot,),
            separator_bindings=(),
            objectives=SimpleNamespace(supported_separator_count=0),
        )
        resolved_direct = SimpleNamespace(
            name="resolved_direct",
            slots=(anchored_slot,),
        )
        resolved_completion = SimpleNamespace(
            name="resolved_completion",
            slots=(anchored_slot,),
        )
        common_width = SimpleNamespace(state=EvidenceState.SUPPORTED)
        search_scope = scope(
            width=660,
            height=120,
            leading=0.0,
            trailing=650.0,
            top=10.0,
            bottom=110.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)

        def resolve(build, *_args):
            return (
                resolved_direct if build is direct else resolved_completion,
                common_width,
            )

        def capture(builds):
            raise CapturedBuilds(builds)

        with (
            patch.object(
                solver_module,
                "_sequence_builds_for_count",
                side_effect=(((direct,), 0, False), ((), 0, False)),
            ),
            patch.object(
                solver_module,
                "_sequence_completed_builds",
                return_value=(sequence_completed,),
            ),
            patch.object(
                solver_module,
                "_direct_nominal_geometry_is_complete",
                return_value=False,
            ),
            patch.object(
                solver_module,
                "_infer_unique_slot_in_direct_nominal_build",
                side_effect=lambda build, *_args: build,
            ),
            patch.object(
                solver_module,
                "_preferred_direct_common_width_is_supported",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_supports_resolved_nominal_slots",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_does_not_contradict_common_width",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_build_satisfies_full_endpoint_extent",
                return_value=True,
            ),
            patch.object(
                solver_module,
                "_resolve_build_physical_boundaries",
                side_effect=resolve,
            ),
            patch.object(
                solver_module,
                "_physically_preferred_builds",
                side_effect=capture,
            ),
        ):
            with self.assertRaises(CapturedBuilds) as captured:
                solve_frame_sequence(
                    sequence_search_index(search_scope),
                    search_scope,
                    plan,
                    6,
                    dimensions(1.0, 1.0),
                    content(width=660, height=120),
                    100_000,
                    strip_mode="full",
                    nominal_count=6,
                )

        self.assertEqual(
            captured.exception.args[0],
            (resolved_direct, resolved_completion),
        )

    def test_sequence_solver_has_one_canonical_search_budget(self) -> None:
        self.assertEqual(
            set(SequenceSolverParameters.__dataclass_fields__),
            {"maximum_assignment_evaluations"},
        )

    def test_one_complete_interior_slot_does_not_resolve_common_width(self) -> None:
        search_scope = scope(
            width=320,
            height=100,
            leading=0.0,
            trailing=320.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=320,
            height=100,
            runs=((0, 100), (110, 210), (220, 320)),
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
        )

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, supports),
            search_scope,
            plan,
            3,
            dimensions(3.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=3,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.width_px.midpoint for slot in solved.frame_slots),
            (100.0, 100.0, 100.0),
        )
        self.assertEqual(
            solved.common_frame_width.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(solved.separator_assignments, ())

    def test_one_separator_cannot_self_prove_two_frame_dimensions(self) -> None:
        search_scope = scope(
            width=310,
            height=100,
            leading=0.0,
            trailing=310.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=310,
            height=100,
            runs=((0, 150), (160, 310)),
        )
        plan = shared_short_axis_plan(search_scope)
        support = separator(150.0, 160.0, plan, supported=True)

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, (support,)),
            search_scope,
            plan,
            2,
            dimensions(36.0, 24.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=2,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.separator_assignments, ())
        self.assertEqual(
            solved.inter_frame_spacings[0].basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )

    def test_distinct_supported_photo_edges_measure_their_distance(
        self,
    ) -> None:
        def boundary(
            position: float,
            side: BoundarySide,
            label: str,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, position, label)
            role_provenance = MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(f"{label}:role"),
                (observation.provenance.root_measurement,),
                "synthetic independently supported photo-edge role",
                (observation.provenance.observation_id,),
            )
            return ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=side,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=role_provenance,
                ),
                inference_provenance=None,
            )

        spacing = solver_module._spacing_from_frame_edges(
            1,
            boundary(100.0, BoundarySide.TRAILING, "unrelated-trailing"),
            boundary(5_000.0, BoundarySide.LEADING, "unrelated-leading"),
        )

        self.assertEqual(
            spacing.basis,
            InterFrameSpacingBasis.OBSERVED,
        )
        self.assertEqual(spacing.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            spacing.provenance.root_measurement,
            MeasurementIdentity.PHOTO_EDGES,
        )

    def test_distinct_supported_photo_edges_measure_uncertain_spacing(self) -> None:
        def boundary(
            interval: PixelInterval,
            side: BoundarySide,
            label: str,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, interval.midpoint, label)
            observation = replace(
                observation,
                samples=tuple(
                    replace(sample, position=interval)
                    for sample in observation.samples
                ),
            )
            role_provenance = MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(f"{label}:role"),
                (observation.provenance.root_measurement,),
                "synthetic independently supported photo-edge role",
                (observation.provenance.observation_id,),
            )
            return ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=side,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=role_provenance,
                ),
                inference_provenance=None,
            )

        spacing = solver_module._spacing_from_frame_edges(
            1,
            boundary(
                PixelInterval(100.0, 105.0),
                BoundarySide.TRAILING,
                "measured-trailing",
            ),
            boundary(
                PixelInterval(99.0, 110.0),
                BoundarySide.LEADING,
                "measured-leading",
            ),
        )

        self.assertEqual(spacing.basis, InterFrameSpacingBasis.OBSERVED)
        self.assertEqual(spacing.kind, InterFrameSpacingKind.UNRESOLVED)
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(spacing.supports_output_protection)

    def test_repeated_width_role_does_not_measure_inter_frame_overlap(
        self,
    ) -> None:
        def boundary(
            position: float,
            side: BoundarySide,
            label: str,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, position, label)
            role_provenance = MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(f"{label}:repeated-width-role"),
                (
                    observation.provenance.root_measurement,
                    MeasurementIdentity.FRAME_WIDTH_PATTERN,
                ),
                "synthetic role corroborated by repeated frame width",
                (observation.provenance.observation_id,),
            )
            return ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=side,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=(
                        BoundaryRoleAuthority.MEASUREMENT_CORROBORATED
                    ),
                    role_provenance=role_provenance,
                ),
                inference_provenance=None,
            )

        spacing = solver_module._spacing_from_frame_edges(
            1,
            boundary(200.0, BoundarySide.TRAILING, "pattern-trailing"),
            boundary(100.0, BoundarySide.LEADING, "pattern-leading"),
        )

        self.assertEqual(
            spacing.basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(spacing.supports_output_protection)

    def test_shared_supported_photo_edge_is_exact_measured_contact(self) -> None:
        observation = path(BoundaryAxis.LONG, 100.0, "shared-contact")
        uncertain_position = PixelInterval(90.0, 110.0)
        observation = replace(
            observation,
            samples=tuple(
                replace(sample, position=uncertain_position)
                for sample in observation.samples
            ),
        )
        role_provenance = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("shared-contact:role"),
            (observation.provenance.root_measurement,),
            "synthetic independently supported shared photo edge",
            (observation.provenance.observation_id,),
        )

        def boundary(side: BoundarySide) -> ResolvedFrameBoundary:
            boundary_observation = (
                observation
                if side == BoundarySide.TRAILING
                else replace(observation)
            )
            return ResolvedFrameBoundary(
                position=boundary_observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=boundary_observation,
                    physical_role=side,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=role_provenance,
                ),
                inference_provenance=None,
            )

        spacing = solver_module._spacing_from_frame_edges(
            1,
            boundary(BoundarySide.TRAILING),
            boundary(BoundarySide.LEADING),
        )

        self.assertEqual(spacing.basis, InterFrameSpacingBasis.OBSERVED)
        self.assertEqual(spacing.signed_width_px, PixelInterval.exact(0.0))
        self.assertEqual(spacing.kind, InterFrameSpacingKind.CONTACT)
        self.assertEqual(spacing.state, EvidenceState.SUPPORTED)
        self.assertFalse(spacing.supports_output_protection)

        def inferred_boundary(position: float) -> ResolvedFrameBoundary:
            return ResolvedFrameBoundary(
                position=PixelInterval.exact(position),
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=None,
                inference_provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"contact-endpoint:{position}"),
                    (),
                    "synthetic contact endpoint",
                ),
            )

        left = FrameSlot(
            1,
            PixelInterval(0.0, 110.0),
            inferred_boundary(0.0),
            boundary(BoundarySide.TRAILING),
            FrameContentOccupancy.UNAVAILABLE,
            None,
        )
        right = FrameSlot(
            2,
            PixelInterval(90.0, 200.0),
            boundary(BoundarySide.LEADING),
            inferred_boundary(200.0),
            FrameContentOccupancy.UNAVAILABLE,
            None,
        )
        self.assertTrue(
            physical_model._spacing_matches_frame_slots(spacing, left, right)
        )

    def test_raw_separator_edges_require_candidate_specific_role_assignment(
        self,
    ) -> None:
        search_scope = scope(
            width=210,
            height=100,
            leading=0.0,
            trailing=210.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        support = separator(100.0, 110.0, plan, supported=True)

        preceding, following = solver_module._observed_band_edges(support)

        self.assertEqual(preceding.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(following.state, EvidenceState.UNAVAILABLE)

    def test_merged_underexposure_band_preserves_only_the_assigned_edge(
        self,
    ) -> None:
        search_scope = scope(
            width=330,
            height=100,
            leading=0.0,
            trailing=330.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=330,
            height=100,
            runs=((0, 100), (110, 180), (230, 330)),
        )
        plan = shared_short_axis_plan(search_scope)
        first_separator = separator(100.0, 110.0, plan, supported=True)
        merged_underexposure = separator(180.0, 230.0, plan, supported=True)

        solved = solve_frame_sequence(
            sequence_search_index(
                search_scope,
                (first_separator, merged_underexposure),
            ),
            search_scope,
            plan,
            3,
            dimensions(1.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=3,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.visible_long_axis for slot in solved.frame_slots),
            (
                PixelInterval(0.0, 100.0),
                PixelInterval(110.0, 210.0),
                PixelInterval(230.0, 330.0),
            ),
        )
        self.assertEqual(solved.separator_assignments, ())
        self.assertFalse(solved.frame_slots[1].trailing.independently_observed)
        self.assertTrue(solved.frame_slots[2].leading.independently_observed)

    def test_one_sided_observation_beats_unobserved_contact_geometry(self) -> None:
        search_scope = scope(
            width=330,
            height=100,
            leading=0.0,
            trailing=330.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=330,
            height=100,
            runs=((0, 100), (110, 180), (230, 260)),
        )
        plan = shared_short_axis_plan(search_scope)
        first_separator = separator(100.0, 110.0, plan, supported=True)
        merged_underexposure = separator(180.0, 230.0, plan, supported=True)

        solved = solve_frame_sequence(
            sequence_search_index(
                search_scope,
                (first_separator, merged_underexposure),
            ),
            search_scope,
            plan,
            3,
            dimensions(1.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=3,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.visible_long_axis for slot in solved.frame_slots),
            (
                PixelInterval(0.0, 100.0),
                PixelInterval(110.0, 210.0),
                PixelInterval(230.0, 330.0),
            ),
        )
        self.assertEqual(solved.separator_assignments, ())

    def test_common_width_preserves_inner_measurement_and_infers_outer_edge(
        self,
    ) -> None:
        search_scope = scope(
            width=670,
            height=100,
            leading=0.0,
            trailing=670.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(
                100.0,
                110.0,
                210.0,
                220.0,
                320.0,
                330.0,
                430.0,
                440.0,
                560.0,
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=670,
            height=100,
            runs=(
                (0, 100),
                (110, 210),
                (220, 320),
                (330, 430),
                (440, 540),
                (560, 660),
            ),
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
                (430.0, 440.0),
                (480.0, 560.0),
                (660.0, 670.0),
            )
        )

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, supports),
            search_scope,
            plan,
            6,
            dimensions(1.0, 1.0),
            visible_content,
            100_000,
            strip_mode="full",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.visible_long_axis for slot in solved.frame_slots),
            (
                PixelInterval(0.0, 100.0),
                PixelInterval(110.0, 210.0),
                PixelInterval(220.0, 320.0),
                PixelInterval(330.0, 430.0),
                PixelInterval(440.0, 540.0),
                PixelInterval(560.0, 660.0),
            ),
        )
        self.assertEqual(
            tuple(
                assignment.boundary_index
                for assignment in solved.separator_assignments
            ),
            (1, 2, 3, 4),
        )
        self.assertTrue(solved.frame_slots[-1].leading.independently_observed)
        self.assertFalse(solved.frame_slots[-1].trailing.independently_observed)

    def test_holder_adjacent_band_inner_edge_can_bound_the_edge_frame(self) -> None:
        search_scope = scope(
            width=220,
            height=100,
            leading=0.0,
            trailing=220.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=220,
            height=100,
            runs=((0, 100), (110, 210)),
        )
        plan = shared_short_axis_plan(search_scope)
        internal_separator = separator(100.0, 110.0, plan, supported=True)
        trailing_holder_band = separator(210.0, 220.0, plan, supported=True)

        solved = solve_frame_sequence(
            sequence_search_index(
                search_scope,
                (internal_separator, trailing_holder_band),
            ),
            search_scope,
            plan,
            2,
            dimensions(1.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=2,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        trailing = solved.frame_slots[-1].trailing
        self.assertEqual(trailing.position, trailing_holder_band.observation.leading_edge)
        self.assertEqual(
            trailing.source,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        )
        self.assertTrue(trailing.independently_observed)
        self.assertEqual(solved.separator_assignments, ())

    def test_frame_sized_tonal_band_cannot_become_a_hard_separator(self) -> None:
        search_scope = scope(
            width=300,
            height=100,
            leading=0.0,
            trailing=300.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(150.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=300,
            height=100,
            runs=((0, 140), (160, 300)),
        )
        plan = shared_short_axis_plan(search_scope)
        oversized = separator(75.0, 225.0, plan, supported=True)

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, (oversized,)),
            search_scope,
            plan,
            2,
            dimensions(1.5, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=2,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.separator_assignments, ())

    def test_variable_separator_width_preserves_common_frame_width(self) -> None:
        search_scope = scope(
            width=435,
            height=100,
            leading=0.0,
            trailing=435.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=435,
            height=100,
            runs=((0, 100), (105, 205), (225, 325), (335, 435)),
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(100.0, 105.0, plan, supported=True),
            separator(205.0, 225.0, plan, supported=True),
            separator(325.0, 335.0, plan, supported=True),
        )

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, supports),
            search_scope,
            plan,
            4,
            dimensions(1.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=4,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.width_px.midpoint, 100.0)
        self.assertEqual(len(solved.separator_assignments), 3)

    def test_common_width_can_use_one_edge_of_an_oversized_weak_band(self) -> None:
        search_scope = scope(
            width=560,
            height=100,
            leading=10.0,
            trailing=550.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=560,
            height=100,
            runs=(
                (10, 110),
                (120, 220),
                (230, 330),
                (340, 380),
                (450, 550),
            ),
        )
        plan = shared_short_axis_plan(search_scope)
        hard_separators = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((110, 120), (220, 230), (330, 340))
        )
        oversized_weak_band = separator(380, 450, plan, supported=False)
        supports = (*hard_separators, oversized_weak_band)

        solved = _solve(
            search_scope=search_scope,
            visible_content=visible_content,
            count=5,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.visible_long_axis for slot in solved.frame_slots),
            (
                PixelInterval(10.0, 110.0),
                PixelInterval(120.0, 220.0),
                PixelInterval(230.0, 330.0),
                PixelInterval(340.0, 440.0),
                PixelInterval(450.0, 550.0),
            ),
        )
        self.assertEqual(len(solved.separator_assignments), 3)
        fourth_trailing = solved.frame_slots[3].trailing
        fifth_leading = solved.frame_slots[4].leading
        self.assertEqual(
            fourth_trailing.source,
            FrameBoundarySource.DIMENSION_CONSTRAINED,
        )
        self.assertFalse(fourth_trailing.independently_observed)
        self.assertEqual(
            fifth_leading.source,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        )
        self.assertFalse(fifth_leading.independently_observed)
        self.assertEqual(
            fifth_leading.position,
            oversized_weak_band.observation.trailing_edge,
        )

    def test_complete_separator_sequence_uses_majority_width_consensus(
        self,
    ) -> None:
        search_scope = scope(
            width=543,
            height=100,
            leading=0.0,
            trailing=543.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=543,
            height=100,
            runs=(
                (0, 100),
                (110, 208),
                (220, 320),
                (330, 432),
                (440, 543),
            ),
        )
        plan = shared_short_axis_plan(search_scope)

        def uncertain_separator(
            start: PixelInterval,
            end: PixelInterval,
        ):
            support = separator(
                start.midpoint,
                end.midpoint,
                plan,
                supported=True,
            )
            return replace(
                support,
                observation=replace(
                    support.observation,
                    leading_edge=start,
                    trailing_edge=end,
                ),
            )

        supports = (
            uncertain_separator(
                PixelInterval.exact(100.0),
                PixelInterval.exact(110.0),
            ),
            uncertain_separator(
                PixelInterval(208.0, 211.0),
                PixelInterval.exact(220.0),
            ),
            uncertain_separator(
                PixelInterval(320.0, 323.0),
                PixelInterval.exact(330.0),
            ),
            uncertain_separator(
                PixelInterval(432.0, 435.0),
                PixelInterval.exact(440.0),
            ),
        )

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, supports),
            search_scope,
            plan,
            5,
            dimensions(1.0, 1.0),
            visible_content,
            20_000,
            strip_mode="full",
            nominal_count=5,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(len(solved.separator_assignments), 4)
        self.assertEqual(
            solved.common_frame_width.state,
            EvidenceState.SUPPORTED,
        )

    def test_complete_raw_band_sequence_resolves_without_claiming_hard_bands(
        self,
    ) -> None:
        search_scope = scope(
            width=430,
            height=100,
            leading=0.0,
            trailing=430.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=430,
            height=100,
            runs=((0, 100), (110, 210), (220, 320), (330, 430)),
        )
        plan = shared_short_axis_plan(search_scope)
        raw_bands = tuple(
            separator(start, end, plan, supported=False)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
            )
        )

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, raw_bands),
            search_scope,
            plan,
            4,
            dimensions(1.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=4,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.separator_assignments, ())
        self.assertEqual(
            solved.common_frame_width.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            solved.assignment_consensus.state,
            EvidenceState.SUPPORTED,
        )
        self.assertTrue(
            all(
                boundary.geometry_state == BoundaryGeometryState.RESOLVED
                and boundary.role_state == EvidenceState.UNAVAILABLE
                and not boundary.independently_observed
                and
                boundary.source
                == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
                for slot in solved.frame_slots[1:-1]
                for boundary in (slot.leading, slot.trailing)
            )
        )

    def test_generic_gray_path_contact_remains_a_geometry_hypothesis(self) -> None:
        search_scope = scope(
            width=200,
            height=100,
            leading=0.0,
            trailing=200.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(width=200, height=100, runs=((0, 200),))

        solved = _solve(
            search_scope=search_scope,
            visible_content=visible_content,
            count=2,
            frame_dimensions=dimensions(1.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        spacing = solved.inter_frame_spacings[0]
        self.assertEqual(spacing.kind, InterFrameSpacingKind.CONTACT)
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(spacing.basis, InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS)

    def test_unobserved_contact_does_not_erase_distinct_boundary_paths(
        self,
    ) -> None:
        search_scope = scope(
            width=320,
            height=100,
            leading=0.0,
            trailing=320.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 200.0, 210.0, 220.0, 300.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=320, height=100),
            count=3,
            frame_dimensions=dimensions(1.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.visible_long_axis for slot in solved.frame_slots),
            (
                PixelInterval(0.0, 100.0),
                PixelInterval(110.0, 210.0),
                PixelInterval(220.0, 320.0),
            ),
        )
        self.assertTrue(
            all(
                spacing.kind == InterFrameSpacingKind.SEPARATOR
                and spacing.state == EvidenceState.UNAVAILABLE
                for spacing in solved.inter_frame_spacings
            )
        )

    def test_one_measured_contact_path_owns_both_adjacent_frame_side_roles(
        self,
    ) -> None:
        search_scope = scope(
            width=200,
            height=100,
            leading=0.0,
            trailing=200.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(width=200, height=100, runs=((0, 200),))
        frame_dimensions = dimensions(1.0, 1.0)
        solved = _solve(
            search_scope=search_scope,
            visible_content=visible_content,
            count=2,
            frame_dimensions=frame_dimensions,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        sequence = geometry(
            search_scope,
            (),
            frame_dimensions,
            solved,
            nominal_count=2,
        )

        contact_assignments = tuple(
            assignment
            for assignment in sequence.long_axis_assignments
            if assignment.resolution.position == solved.frame_slots[0].trailing.position
        )
        self.assertEqual(len(contact_assignments), 2)
        self.assertEqual(
            {(item.frame_index, item.side) for item in contact_assignments},
            {
                (1, BoundarySide.TRAILING),
                (2, BoundarySide.LEADING),
            },
        )
        self.assertTrue(
            all(
                item.resolution.role_state == EvidenceState.UNAVAILABLE
                for item in contact_assignments
            )
        )

    def test_generic_gray_path_cannot_create_independent_photo_edge_roles(
        self,
    ) -> None:
        search_scope = scope(
            width=200,
            height=100,
            leading=0.0,
            trailing=200.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=200, height=100, runs=((0, 200),)),
            count=2,
            frame_dimensions=dimensions(1.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertTrue(solved.long_axis_assignments)
        self.assertTrue(
            all(
                not assignment.resolution.independently_observed
                for assignment in solved.long_axis_assignments
            )
        )
        self.assertEqual(
            solved.inter_frame_spacings[0].basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        self.assertEqual(solved.inter_frame_spacings[0].state, EvidenceState.UNAVAILABLE)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)

    def test_single_frame_can_remain_provisional_without_common_width(self) -> None:
        search_scope = scope(
            width=200,
            height=100,
            leading=0.0,
            trailing=200.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=200, height=100, runs=((0, 200),)),
            count=1,
            frame_dimensions=dimensions(1.0, 1.0),
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(len(solved.frame_slots), 1)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(solved.frame_slots[0].leading.independently_observed)
        self.assertFalse(solved.frame_slots[0].trailing.independently_observed)

    def test_single_frame_content_topology_does_not_corroborate_boundary_pair(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(170.0, 220.0, 280.0, 330.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=500,
                height=100,
                runs=((180, 320),),
                guidance_runs=((180, 320),),
                position_uncertainty_px=15,
            ),
            count=1,
            frame_dimensions=dimensions(1.6, 1.0),
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        slot = solved.frame_slots[0]
        self.assertEqual(slot.leading.position, PixelInterval.exact(170.0))
        self.assertEqual(slot.trailing.position, PixelInterval.exact(330.0))
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)
        self.assertEqual(solved.assignment_consensus.state, EvidenceState.UNAVAILABLE)

    def test_content_topology_does_not_corroborate_full_sequence_endpoints(
        self,
    ) -> None:
        search_scope = scope(
            width=340,
            height=100,
            leading=10.0,
            trailing=330.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = (
            separator(110.0, 120.0, plan, supported=True),
            separator(220.0, 230.0, plan, supported=True),
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=340,
                height=100,
                runs=((10, 330),),
                guidance_runs=((10, 330),),
                position_uncertainty_px=1,
            ),
            count=3,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(solved.frame_slots[0].leading.independently_observed)
        self.assertFalse(solved.frame_slots[-1].trailing.independently_observed)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(solved.common_frame_width.width_px)

    def test_holder_contact_uncertainty_does_not_create_common_frame_width(
        self,
    ) -> None:
        search_scope = scope(
            width=340,
            height=100,
            leading=10.0,
            trailing=333.0,
            top=0.0,
            bottom=100.0,
            holder_sides=(BoundarySide.TOP, BoundarySide.BOTTOM),
        )
        raw_paths = list(search_scope.raw_boundary_paths)
        raw_paths[0] = replace(
            raw_paths[0],
            samples=(
                replace(
                    raw_paths[0].samples[0],
                    position=PixelInterval(8.0, 12.0),
                ),
            ),
        )
        raw_paths[1] = replace(
            raw_paths[1],
            samples=(
                replace(
                    raw_paths[1].samples[0],
                    position=PixelInterval(332.0, 334.0),
                ),
            ),
        )
        search_scope = replace(search_scope, raw_boundary_paths=tuple(raw_paths))
        plan = shared_short_axis_plan(search_scope)

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=340,
                height=100,
                runs=((9, 333),),
                guidance_runs=((9, 333),),
                position_uncertainty_px=1,
            ),
            count=3,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=(
                separator(110.0, 120.0, plan, supported=True),
                separator(220.0, 230.0, plan, supported=True),
            ),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(solved.common_frame_width.width_px)
        self.assertEqual(
            solved.frame_slots[0].leading.position,
            PixelInterval(8.0, 12.0),
        )
        self.assertEqual(
            solved.frame_slots[-1].trailing.position,
            PixelInterval(332.0, 334.0),
        )
        self.assertFalse(solved.frame_slots[0].leading.independently_observed)
        self.assertFalse(solved.frame_slots[-1].trailing.independently_observed)

    def test_single_frame_ambiguous_content_brackets_do_not_gain_edge_roles(
        self,
    ) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(165.0, 171.0, 329.0, 335.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=500,
                height=100,
                runs=((180, 320),),
                guidance_runs=((168, 332),),
                position_uncertainty_px=20,
            ),
            count=1,
            frame_dimensions=dimensions(1.64, 1.0),
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        slot = solved.frame_slots[0]
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)

    def test_content_corroboration_never_creates_a_frame_boundary(self) -> None:
        search_scope = scope(
            width=500,
            height=100,
            leading=0.0,
            trailing=500.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=500,
                height=100,
                runs=((180, 320),),
                guidance_runs=((180, 320),),
                position_uncertainty_px=15,
            ),
            count=1,
            frame_dimensions=dimensions(1.6, 1.0),
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        slot = solved.frame_slots[0]
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)

    def test_single_frame_search_hint_orders_equally_provisional_geometry(self) -> None:
        search_scope = scope(
            width=1000,
            height=100,
            leading=0.0,
            trailing=1000.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(400.0, 550.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=1000,
                height=100,
                runs=((400, 550),),
            ),
            count=1,
            frame_dimensions=dimensions(1.5, 1.0),
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        slot = solved.frame_slots[0]
        self.assertEqual(slot.leading.position, PixelInterval.exact(400.0))
        self.assertEqual(slot.trailing.position, PixelInterval.exact(550.0))
        self.assertEqual(
            solved.assignment_consensus.outcome,
            AssignmentConsensusOutcome.DISAGREED,
        )
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.UNAVAILABLE)

    def test_single_frame_two_side_measurements_support_sequence_proof(self) -> None:
        search_scope = scope(
            width=200,
            height=100,
            leading=0.0,
            trailing=200.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        frame_dimensions = dimensions(1.0, 1.0)
        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=200, height=100, runs=((0, 200),)),
            count=1,
            frame_dimensions=frame_dimensions,
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        provisional_slot = solved.frame_slots[0]

        def support_role(boundary):
            assert boundary.boundary_anchor is not None
            measurement = boundary.boundary_anchor.observation.provenance
            return replace(
                boundary,
                boundary_anchor=replace(
                    boundary.boundary_anchor,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=measurement,
                ),
            )

        supported_slot = replace(
            provisional_slot,
            leading=support_role(provisional_slot.leading),
            trailing=support_role(provisional_slot.trailing),
        )
        solved = replace(
            solved,
            frame_slots=(supported_slot,),
            long_axis_assignments=tuple(
                replace(
                    assignment,
                    resolution=(
                        supported_slot.leading
                        if assignment.side == BoundarySide.LEADING
                        else supported_slot.trailing
                    ),
                )
                for assignment in solved.long_axis_assignments
            ),
        )
        frame_geometry = geometry(
            search_scope,
            (),
            frame_dimensions,
            solved,
            strip_mode="partial",
            nominal_count=6,
        )
        slot = frame_geometry.frame_slots[0]
        self.assertTrue(slot.leading.independently_observed)
        self.assertTrue(slot.trailing.independently_observed)
        evidence = SimpleNamespace(
            frame_slot_topology=SimpleNamespace(state=EvidenceState.SUPPORTED),
            independence=SimpleNamespace(state=EvidenceState.SUPPORTED),
            separator_sequence=SimpleNamespace(
                state=EvidenceState.NOT_APPLICABLE,
                hard_count=0,
            ),
            frame_dimensions=SimpleNamespace(state=EvidenceState.UNAVAILABLE),
            content_preservation_state=EvidenceState.SUPPORTED,
            internal_frame_boundary_preservation=SimpleNamespace(observations=()),
            partial_edge_safety=SimpleNamespace(state=EvidenceState.UNAVAILABLE),
            holder_occupancy=SimpleNamespace(occupancy_state="unavailable"),
        )

        paths = sequence_proof_paths_for_geometry(frame_geometry, evidence)

        self.assertEqual(paths[1].code, "dimension_sequence_led")
        self.assertEqual(paths[1].state, EvidenceState.SUPPORTED)

    def test_width_search_hint_cannot_resolve_dimension_boundaries(self) -> None:
        search_scope = scope(
            width=200,
            height=100,
            leading=0.0,
            trailing=200.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(width=200, height=100, runs=((0, 200),)),
            count=2,
            frame_dimensions=dimensions(1.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        inferred = tuple(
            boundary
            for slot in solved.frame_slots
            for boundary in (slot.leading, slot.trailing)
            if boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        )
        self.assertTrue(inferred)
        self.assertTrue(
            all(not boundary.geometry_resolved for boundary in inferred)
        )

    def test_common_width_role_corroboration_is_not_independent_measurement(
        self,
    ) -> None:
        search_scope = scope(
            width=540,
            height=100,
            leading=0.0,
            trailing=540.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0, 430.0, 440.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=540,
            height=100,
            runs=((0, 100), (110, 210), (220, 320), (330, 430), (440, 540)),
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((100, 110), (210, 220), (320, 330), (430, 440))
        )

        solved = solve_frame_sequence(
            sequence_search_index(search_scope, supports),
            search_scope,
            plan,
            5,
            dimensions(1.0, 1.0),
            visible_content,
            100_000,
            strip_mode="partial",
            nominal_count=6,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        endpoint = solved.frame_slots[-1].trailing
        self.assertEqual(endpoint.position, PixelInterval.exact(540.0))
        self.assertEqual(endpoint.role_state, EvidenceState.SUPPORTED)
        self.assertFalse(endpoint.independently_observed)
        assert endpoint.role_provenance is not None
        self.assertNotEqual(
            endpoint.role_provenance.root_measurement,
            MeasurementIdentity.FRAME_GEOMETRY,
        )
        self.assertNotIn(
            MeasurementIdentity.FRAME_GEOMETRY,
            endpoint.role_provenance.dependencies,
        )
        self.assertEqual(
            tuple(
                constraint.frame_index
                for constraint in solved.common_frame_width.constraints
            ),
            (2, 3, 4),
        )

    def test_every_solution_has_strictly_monotonic_positive_slots(self) -> None:
        search_scope = scope(
            width=325,
            height=100,
            leading=0.0,
            trailing=325.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=325,
            height=100,
            runs=((0, 100), (105, 205), (225, 325)),
        )
        plan = shared_short_axis_plan(search_scope)
        solved = solve_frame_sequence(
            sequence_search_index(
                search_scope,
                (
                    separator(100.0, 105.0, plan, supported=True),
                    separator(205.0, 225.0, plan, supported=True),
                ),
            ),
            search_scope,
            plan,
            3,
            dimensions(1.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=3,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertTrue(all(slot.width_px.minimum > 0.0 for slot in solved.frame_slots))
        self.assertTrue(
            all(
                right.leading.position.minimum > left.leading.position.maximum
                and right.trailing.position.minimum > left.trailing.position.maximum
                for left, right in zip(solved.frame_slots, solved.frame_slots[1:])
            )
        )

    def test_complete_separator_sequence_ignores_unassigned_gray_paths(self) -> None:
        baseline_scope = scope(
            width=320,
            height=100,
            leading=0.0,
            trailing=320.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        noisy_scope = scope(
            width=320,
            height=100,
            leading=0.0,
            trailing=320.0,
            top=0.0,
            bottom=100.0,
            internal_paths=tuple(float(value) for value in range(20, 301, 10)),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=320,
            height=100,
            runs=((0, 100), (110, 210), (220, 320)),
        )

        def solve(search_scope):
            plan = shared_short_axis_plan(search_scope)
            return solve_frame_sequence(
                sequence_search_index(
                    search_scope,
                    (
                        separator(100.0, 110.0, plan, supported=True),
                        separator(210.0, 220.0, plan, supported=True),
                    ),
                ),
                search_scope,
                plan,
                3,
                dimensions(3.0, 1.0),
                visible_content,
                1_000,
                strip_mode="full",
                nominal_count=3,
            )

        baseline = solve(baseline_scope)
        noisy = solve(noisy_scope)

        self.assertIsInstance(baseline, FrameSequenceSolveResult)
        self.assertIsInstance(noisy, FrameSequenceSolveResult)
        assert isinstance(baseline, FrameSequenceSolveResult)
        assert isinstance(noisy, FrameSequenceSolveResult)
        self.assertFalse(noisy.search_outcome.budget_exhausted)
        self.assertEqual(
            tuple(slot.width_px for slot in noisy.frame_slots),
            tuple(slot.width_px for slot in baseline.frame_slots),
        )
        self.assertEqual(
            tuple(
                assignment.boundary_index
                for assignment in noisy.separator_assignments
            ),
            tuple(
                assignment.boundary_index
                for assignment in baseline.separator_assignments
            ),
        )

    def test_unassigned_gray_paths_do_not_seed_supported_separator_search(
        self,
    ) -> None:
        search_scope = scope(
            width=660,
            height=100,
            leading=0.0,
            trailing=660.0,
            top=0.0,
            bottom=100.0,
            internal_paths=tuple(
                sorted(
                    {
                        *(float(value) for value in range(20, 641, 10)),
                        100.0,
                        110.0,
                        210.0,
                        220.0,
                        320.0,
                        330.0,
                        430.0,
                        440.0,
                        550.0,
                        650.0,
                    }
                )
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
                (430.0, 440.0),
            )
        )

        search_index = sequence_search_index(search_scope, supports)
        search_space = _measured_frame_search_space(
            search_index,
            (PixelInterval.exact(100.0),),
            PixelInterval.exact(100.0),
            None,
        )
        geometry_leading, geometry_trailing = (
            solver_module._separator_geometry_edge_candidates(
                search_index.separator_supports.canonical_supports,
                search_scope,
            )
        )
        leading_candidates = tuple(
            dict.fromkeys((*search_space.leading_candidates, *geometry_leading))
        )
        trailing_candidates = tuple(
            dict.fromkeys((*search_space.trailing_candidates, *geometry_trailing))
        )
        seeds = solver_module._dimension_seed_candidates(
            (*leading_candidates, *trailing_candidates)
        )

        self.assertLess(
            len(seeds),
            len(leading_candidates) + len(trailing_candidates),
        )
        self.assertTrue(
            all(
                edge.external_side is not None
                or (
                    edge.separator_cross_axis is not None
                    and solver_module._separator_edge_path_is_supported(edge)
                )
                for edge, _ in seeds
            )
        )

    def test_contradicted_bands_do_not_consume_hard_sequence_budget(self) -> None:
        search_scope = scope(
            width=660,
            height=100,
            leading=0.0,
            trailing=660.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(
                100.0,
                110.0,
                210.0,
                220.0,
                320.0,
                330.0,
                430.0,
                440.0,
                540.0,
                550.0,
                650.0,
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supported = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
                (430.0, 440.0),
                (540.0, 550.0),
            )
        )
        contradicted = tuple(
            separator(float(start), float(start + 4), plan, supported=False)
            for start in range(30, 631, 30)
            if start not in {210, 330}
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=660,
                height=100,
                runs=(
                    (0, 100),
                    (110, 210),
                    (220, 320),
                    (330, 430),
                    (440, 540),
                    (550, 650),
                ),
            ),
            count=6,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=(*supported, *contradicted),
            maximum_assignment_evaluations=1_000,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(solved.search_outcome.budget_exhausted)
        self.assertEqual(len(solved.separator_assignments), 5)

    def test_mixed_separator_and_repeated_photo_edges_resolve_sequence(
        self,
    ) -> None:
        search_scope = scope(
            width=435,
            height=100,
            leading=0.0,
            trailing=435.0,
            top=0.0,
            bottom=100.0,
            internal_paths=tuple(
                sorted(
                    {
                        *(float(value) for value in range(20, 421, 10)),
                        100.0,
                        105.0,
                        205.0,
                        225.0,
                        325.0,
                        335.0,
                    }
                )
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=435,
            height=100,
            runs=((0, 100), (105, 205), (225, 325), (335, 435)),
        )
        plan = shared_short_axis_plan(search_scope)
        solved = solve_frame_sequence(
            sequence_search_index(
                search_scope,
                (
                    separator(100.0, 105.0, plan, supported=True),
                    separator(325.0, 335.0, plan, supported=True),
                ),
            ),
            search_scope,
            plan,
            4,
            dimensions(1.0, 1.0),
            visible_content,
            20_000,
            strip_mode="full",
            nominal_count=4,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(solved.search_outcome.budget_exhausted)
        self.assertEqual(
            tuple(
                assignment.boundary_index
                for assignment in solved.separator_assignments
            ),
            (1, 3),
        )
        self.assertEqual(
            tuple(slot.width_px.midpoint for slot in solved.frame_slots),
            (100.0, 100.0, 100.0, 100.0),
        )
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            tuple(
                (
                    constraint.first_boundary_index,
                    constraint.second_boundary_index,
                )
                for constraint in solved.indexed_anchor_distance_constraints
            ),
            ((1, 3),),
        )
        self.assertEqual(
            solved.assignment_consensus.outcome,
            AssignmentConsensusOutcome.UNCONTESTED,
        )
        self.assertTrue(
            all(
                boundary.role_authority
                == BoundaryRoleAuthority.MEASUREMENT_CORROBORATED
                for slot in solved.frame_slots[1:3]
                for boundary in (slot.leading, slot.trailing)
                if boundary.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
            )
        )

    def test_dense_paths_keep_global_geometry_unresolved(
        self,
    ) -> None:
        search_scope = scope(
            width=1_000,
            height=100,
            leading=0.0,
            trailing=1_000.0,
            top=0.0,
            bottom=100.0,
            internal_paths=tuple(float(value) for value in range(40, 961, 40)),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=1_000,
                height=100,
                runs=((0, 1_000),),
            ),
            count=5,
            frame_dimensions=dimensions(2.0, 1.0),
            strip_mode="partial",
            nominal_count=6,
            maximum_assignment_evaluations=10_000,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(solved.search_outcome.budget_exhausted)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            solved.assignment_consensus.outcome,
            AssignmentConsensusOutcome.DISAGREED,
        )

    def test_dense_twelve_slot_raw_paths_are_pruned_before_graph_budget(
        self,
    ) -> None:
        search_scope = scope(
            width=1_320,
            height=100,
            leading=0.0,
            trailing=1_320.0,
            top=0.0,
            bottom=100.0,
            internal_paths=tuple(float(value) for value in range(20, 1_301, 20)),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=1_320,
            height=100,
            runs=tuple((index * 110, index * 110 + 100) for index in range(12)),
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=visible_content,
            count=12,
            frame_dimensions=dimensions(1.0, 1.0),
            strip_mode="full",
            nominal_count=12,
            maximum_assignment_evaluations=20_000,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertIn(
            PhysicalSearchFact.SOLUTION_FOUND,
            solved.search_outcome.facts,
        )
        self.assertFalse(solved.search_outcome.budget_exhausted)

    def test_common_width_grouping_does_not_scan_every_option_per_coordinate(
        self,
    ) -> None:
        unavailable_edge = SimpleNamespace(
            state=EvidenceState.UNAVAILABLE,
            separator_cross_axis=None,
        )
        width_hypotheses = tuple(
            PixelInterval.exact(float(width)) for width in range(1, 31)
        )
        options_by_frame = tuple(
            tuple(
                (
                    option_index,
                    SimpleNamespace(
                        width_px=PixelInterval(1.0, 30.0),
                        leading=unavailable_edge,
                        trailing=unavailable_edge,
                        leading_holder_clip_supported=False,
                        trailing_holder_clip_supported=False,
                    ),
                )
                for option_index in range(30)
            )
            for _ in range(12)
        )

        with patch.object(
            solver_module,
            "_common_width_coordinate_span",
            wraps=solver_module._common_width_coordinate_span,
        ) as coordinate_span:
            width_index = solver_module._common_width_option_index(
                options_by_frame,
                12,
                width_hypotheses,
            )

        self.assertEqual(len(width_index.group_masks), 1)
        self.assertEqual(coordinate_span.call_count, 360)

    def test_reachability_index_does_not_discard_a_valid_predecessor(self) -> None:
        def option(
            leading: float,
            trailing: float,
            width: PixelInterval,
        ) -> SimpleNamespace:
            def edge(position: float) -> SimpleNamespace:
                return SimpleNamespace(
                    position=PixelInterval.exact(position),
                    separator=None,
                    external_side=None,
                )

            return SimpleNamespace(
                leading=edge(leading),
                trailing=edge(trailing),
                width_px=width,
            )

        ordered = (
            option(0.0, 10.0, PixelInterval.exact(30.0)),
            option(1.0, 20.0, PixelInterval.exact(5.0)),
            option(30.0, 40.0, PixelInterval(5.0, 30.0)),
        )
        context = SimpleNamespace(
            run_starts=(),
            run_ends=(),
            coverages=((0, 10), (1, 20), (30, 40)),
            allow_nominal_slot_sized_gap=False,
        )

        with patch.object(
            solver_module,
            "_cached_sequence_graph_edge_supported",
            side_effect=lambda left, right, _ordered, _context: (left, right)
            == (0, 2),
        ) as edge_supported:
            reachable = solver_module._reachable_predecessors_for_boundary(
                (0, 1),
                (2,),
                ordered,
                context,
            )

        self.assertEqual(reachable, {2: 0})

    def test_reachability_index_does_not_discard_a_valid_successor(self) -> None:
        def option(
            leading: float,
            trailing: float,
            width: PixelInterval,
        ) -> SimpleNamespace:
            def edge(position: float) -> SimpleNamespace:
                return SimpleNamespace(
                    position=PixelInterval.exact(position),
                    separator=None,
                    external_side=None,
                )

            return SimpleNamespace(
                leading=edge(leading),
                trailing=edge(trailing),
                width_px=width,
            )

        ordered = (
            option(0.0, 10.0, PixelInterval(5.0, 30.0)),
            option(20.0, 30.0, PixelInterval.exact(5.0)),
            option(30.0, 40.0, PixelInterval.exact(30.0)),
        )
        context = SimpleNamespace(
            run_starts=(),
            run_ends=(),
            coverages=((0, 10), (20, 30), (30, 40)),
            allow_nominal_slot_sized_gap=False,
        )

        with patch.object(
            solver_module,
            "_cached_sequence_graph_edge_supported",
            side_effect=lambda left, right, _ordered, _context: (left, right)
            == (0, 2),
        ) as edge_supported:
            reachable = solver_module._reachable_successors_for_boundary(
                (0,),
                (1, 2),
                ordered,
                context,
            )

        self.assertEqual(reachable, {0: 2})

    def test_dense_paths_do_not_turn_candidate_width_into_global_consensus(
        self,
    ) -> None:
        search_scope = scope(
            width=540,
            height=100,
            leading=0.0,
            trailing=540.0,
            top=0.0,
            bottom=100.0,
            internal_paths=tuple(
                sorted(
                    {
                        *(float(value) for value in range(10, 531, 10)),
                        100.0,
                        110.0,
                        210.0,
                        220.0,
                        320.0,
                        330.0,
                        430.0,
                        440.0,
                    }
                )
            ),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=540,
            height=100,
            runs=((0, 100), (110, 210), (220, 320), (330, 430), (440, 540)),
        )
        plan = shared_short_axis_plan(search_scope)

        solved = solve_frame_sequence(
            sequence_search_index(search_scope),
            search_scope,
            plan,
            5,
            dimensions(1.0, 1.0),
            visible_content,
            20_000,
            strip_mode="full",
            nominal_count=5,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(solved.search_outcome.budget_exhausted)
        self.assertEqual(len(solved.frame_slots), 5)
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            solved.assignment_consensus.outcome,
            AssignmentConsensusOutcome.DISAGREED,
        )
        self.assertLessEqual(solved.assignment_evaluations, 20_000)

    def test_complete_observed_sequence_prunes_dimension_only_expansion(
        self,
    ) -> None:
        search_scope = scope(
            width=540,
            height=100,
            leading=0.0,
            trailing=540.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0, 320.0, 330.0, 430.0, 440.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
                (430.0, 440.0),
            )
        )

        with patch.object(
            solver_module,
            "_dimension_frame_constraints",
            wraps=solver_module._dimension_frame_constraints,
        ) as dimension_constraints:
            solved = _solve(
                search_scope=search_scope,
                visible_content=content(
                    width=540,
                    height=100,
                    runs=((0, 100), (110, 210), (220, 320), (330, 430), (440, 540)),
                ),
                count=5,
                frame_dimensions=dimensions(1.0, 1.0),
                supports=supports,
                maximum_assignment_evaluations=100_000,
            )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        dimension_constraints.assert_not_called()

    def test_unproven_observation_edge_does_not_prune_dimension_search(
        self,
    ) -> None:
        leading = SimpleNamespace(
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            independently_observed=True,
            position=PixelInterval.exact(0.0),
        )
        trailing = SimpleNamespace(
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            independently_observed=False,
            position=PixelInterval.exact(100.0),
        )
        build = SimpleNamespace(
            slots=(SimpleNamespace(leading=leading, trailing=trailing),),
            spacings=(),
            separator_bindings=(),
        )

        self.assertFalse(
            solver_module._complete_separator_sequence_builds_dominate_dimension_inference(
                (build,),
                content(width=100, height=100),
            )
        )

    def test_unresolved_internal_spacing_does_not_prune_dimension_search(
        self,
    ) -> None:
        def boundary(position: float) -> SimpleNamespace:
            return SimpleNamespace(
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                independently_observed=True,
                position=PixelInterval.exact(position),
            )

        build = SimpleNamespace(
            slots=(
                SimpleNamespace(leading=boundary(0.0), trailing=boundary(40.0)),
                SimpleNamespace(leading=boundary(60.0), trailing=boundary(100.0)),
            ),
            spacings=(
                SimpleNamespace(
                    basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
                ),
            ),
            separator_bindings=(),
        )

        self.assertFalse(
            solver_module._complete_separator_sequence_builds_dominate_dimension_inference(
                (build,),
                content(width=100, height=100),
            )
        )

    def test_observed_spacing_without_separator_sequence_keeps_dimension_search(
        self,
    ) -> None:
        def boundary(position: float) -> SimpleNamespace:
            return SimpleNamespace(
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                independently_observed=True,
                position=PixelInterval.exact(position),
            )

        build = SimpleNamespace(
            slots=(
                SimpleNamespace(leading=boundary(0.0), trailing=boundary(40.0)),
                SimpleNamespace(leading=boundary(60.0), trailing=boundary(100.0)),
            ),
            spacings=(
                SimpleNamespace(basis=InterFrameSpacingBasis.OBSERVED),
            ),
            separator_bindings=(),
        )

        self.assertFalse(
            solver_module._complete_separator_sequence_builds_dominate_dimension_inference(
                (build,),
                content(width=100, height=100),
            )
        )

    def test_common_width_supplies_missing_separator_boundaries_without_measurement(
        self,
    ) -> None:
        search_scope = scope(
            width=540,
            height=100,
            leading=0.0,
            trailing=540.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=540,
            height=100,
            runs=((0, 100), (110, 210), (220, 320), (330, 430), (440, 540)),
        )
        plan = shared_short_axis_plan(search_scope)
        solved = solve_frame_sequence(
            sequence_search_index(
                search_scope,
                (
                    separator(100.0, 110.0, plan, supported=True),
                    separator(210.0, 220.0, plan, supported=True),
                    separator(320.0, 330.0, plan, supported=True),
                ),
            ),
            search_scope,
            plan,
            5,
            dimensions(1.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=5,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertFalse(solved.search_outcome.budget_exhausted)
        self.assertEqual(
            tuple(slot.width_px.midpoint for slot in solved.frame_slots),
            (100.0, 100.0, 100.0, 100.0, 100.0),
        )
        self.assertEqual(len(solved.separator_assignments), 3)
        self.assertEqual(
            solved.frame_slots[3].trailing.source.value,
            "dimension_constrained",
        )
        self.assertEqual(
            solved.frame_slots[4].leading.source.value,
            "dimension_constrained",
        )
        self.assertEqual(
            solved.frame_slots[3].trailing.role_state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            solved.frame_slots[4].leading.role_state,
            EvidenceState.UNAVAILABLE,
        )

    def test_execution_budget_exhaustion_is_typed_unavailability(self) -> None:
        search_scope = scope(
            width=310,
            height=100,
            leading=0.0,
            trailing=310.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(150.0, 160.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=310,
                height=100,
                runs=((0, 150), (160, 310)),
            ),
            count=2,
            frame_dimensions=dimensions(1.5, 1.0),
            maximum_assignment_evaluations=1,
        )

        self.assertIsInstance(solved, FrameSequenceSolveFailure)
        self.assertIn(
            PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
            solved.search_outcome.facts,
        )

    def test_graph_budget_charges_only_physically_supported_transitions(
        self,
    ) -> None:
        feasible = ((0, 1), (2, 3, 4), (5, 6, 7, 8))

        with patch.object(
            solver_module,
            "_cached_sequence_graph_edge_supported",
            side_effect=lambda left, right, _ordered, _context: (left, right)
            in {(0, 2), (2, 5), (3, 6)},
        ):
            evaluations = solver_module._sequence_graph_evaluations(
                feasible,
                (),
                SimpleNamespace(
                    allow_nominal_slot_sized_gap=True,
                    edge_support_cache={},
                ),
            )

        empty = solver_module._SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(evaluations.incremental_cost(empty), 12)

    def test_direct_graph_budget_charges_only_inspected_transition_facts(
        self,
    ) -> None:
        feasible = ((0, 1), (2, 3, 4))
        context = SimpleNamespace(
            allow_nominal_slot_sized_gap=False,
            edge_support_cache={(0, 2): True},
        )

        evaluations = solver_module._sequence_graph_evaluations(
            feasible,
            (),
            context,
        )

        empty = solver_module._SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(evaluations.incremental_cost(empty), 6)

    def test_cached_graph_edge_is_charged_once_across_frame_layers(self) -> None:
        context = SimpleNamespace(
            allow_nominal_slot_sized_gap=False,
            edge_support_cache={(0, 1): True},
        )

        evaluations = solver_module._sequence_graph_evaluations(
            ((0,), (1,), (0,), (1,)),
            (),
            context,
        )

        empty = solver_module._SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(evaluations.incremental_cost(empty), 5)

    def test_overlapping_width_groups_charge_shared_graph_facts_once(
        self,
    ) -> None:
        context = SimpleNamespace(
            allow_nominal_slot_sized_gap=False,
            edge_support_cache={(0, 2): True, (1, 3): False},
        )
        first = solver_module._sequence_graph_evaluations(
            ((0, 1), (2, 3)),
            (),
            context,
        )
        context.edge_support_cache[(0, 4)] = True
        second = solver_module._sequence_graph_evaluations(
            ((0, 1), (2, 3, 4)),
            (),
            context,
        )

        empty = solver_module._SequenceGraphEvaluations(
            frozenset(),
            frozenset(),
            frozenset(),
        )
        self.assertEqual(first.incremental_cost(empty), 5)
        self.assertEqual(second.incremental_cost(empty), 7)
        self.assertEqual(second.incremental_cost(first), 2)

    def test_graph_edge_cache_retains_unsupported_results(self) -> None:
        context = SimpleNamespace(edge_support_cache={})

        with patch.object(
            solver_module,
            "_sequence_graph_edge_is_interval_feasible",
            return_value=False,
        ) as measure:
            first = solver_module._cached_sequence_graph_edge_supported(
                1,
                2,
                (),
                context,
            )
            second = solver_module._cached_sequence_graph_edge_supported(
                1,
                2,
                (),
                context,
            )

        self.assertFalse(first)
        self.assertFalse(second)
        measure.assert_called_once()

    def test_search_hint_only_drives_focused_dimension_options(self) -> None:
        search_scope = scope(
            width=900,
            height=100,
            leading=0.0,
            trailing=900.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(73.0, 191.0, 338.0, 529.0, 761.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        search_index = replace(
            sequence_search_index(search_scope, ()),
            width_hypotheses=(),
        )
        captured: list[tuple[_MeasuredFrameConstraint, ...]] = []

        def capture(options, *_args, **_kwargs):
            captured.append(options)
            return (), 0, False

        with patch.object(
            solver_module,
            "_measured_frame_sequences",
            side_effect=capture,
        ):
            solve_frame_sequence(
                search_index,
                search_scope,
                shared_short_axis_plan(search_scope),
                3,
                dimensions(3.0, 1.0),
                content(width=900, height=100, runs=((0, 900),)),
                10_000,
                strip_mode="partial",
                nominal_count=6,
            )

        self.assertTrue(captured)
        self.assertTrue(
            all(
                any(
                    edge.basis == FrameBoundarySource.DIMENSION_CONSTRAINED
                    for option in options
                    for edge in (option.leading, option.trailing)
                )
                for options in captured
            )
        )

    def test_weak_separator_observations_do_not_change_resolved_geometry(self) -> None:
        search_scope = scope(
            width=320,
            height=100,
            leading=0.0,
            trailing=320.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        visible_content = content(
            width=320,
            height=100,
            runs=((0, 100), (110, 210), (220, 320)),
        )
        plan = shared_short_axis_plan(search_scope)
        supported = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
        )

        baseline = solve_frame_sequence(
            sequence_search_index(search_scope, supported),
            search_scope,
            plan,
            3,
            dimensions(3.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=3,
        )

        solved = solve_frame_sequence(
            sequence_search_index(
                search_scope,
                (
                    separator(40.0, 50.0, plan),
                    supported[0],
                    separator(160.0, 170.0, plan),
                    supported[1],
                ),
            ),
            search_scope,
            plan,
            3,
            dimensions(3.0, 1.0),
            visible_content,
            10_000,
            strip_mode="full",
            nominal_count=3,
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        self.assertIsInstance(baseline, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        assert isinstance(baseline, FrameSequenceSolveResult)
        self.assertFalse(solved.search_outcome.budget_exhausted)
        self.assertEqual(
            solved.assignment_consensus.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            tuple(slot.width_px.midpoint for slot in solved.frame_slots),
            (100.0, 100.0, 100.0),
        )

    def test_measured_edge_can_locate_slot_inference_without_adding_separator(
        self,
    ) -> None:
        search_scope = scope(
            width=660,
            height=120,
            leading=0.0,
            trailing=540.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(
                100.0,
                110.0,
                210.0,
                220.0,
                320.0,
                330.0,
                430.0,
                440.0,
            ),
            holder_sides=_ALL_HOLDER_SIDES,
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 660.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 120.0,
            },
        )
        visible_content = content(
            width=660,
            height=120,
            runs=((0, 100), (110, 210), (220, 320), (330, 430), (440, 540)),
        )
        plan = shared_short_axis_plan(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((100, 110), (210, 220), (320, 330), (430, 440))
        )
        searched_counts: list[int] = []
        original_search = solver_module._sequence_builds_for_count

        def tracked_search(*args, **kwargs):
            searched_counts.append(args[4])
            return original_search(*args, **kwargs)

        with patch.object(
            solver_module,
            "_sequence_builds_for_count",
            side_effect=tracked_search,
        ):
            solved = _solve(
                search_scope=search_scope,
                visible_content=visible_content,
                count=6,
                frame_dimensions=dimensions(1.0, 1.0),
                supports=supports,
            )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        sequence = geometry(
            search_scope,
            supports,
            dimensions(1.0, 1.0),
            solved,
            nominal_count=6,
        )
        evidence = separator_sequence_evidence(sequence)
        self.assertEqual(sequence.sequence_inferred_frame_indexes, (6,))
        self.assertEqual(searched_counts, [6])
        self.assertEqual(evidence.hard_count, 4)
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            tuple(
                constraint.frame_index
                for constraint in solved.common_frame_width.constraints
            ),
            (2, 3, 4, 5),
        )

    def test_partial_sequence_never_uses_blank_region_to_resolve_count(self) -> None:
        search_scope = scope(
            width=560,
            height=120,
            leading=0.0,
            trailing=320.0,
            top=10.0,
            bottom=110.0,
            internal_paths=(100.0, 110.0, 210.0, 220.0),
            holder_sides=_ALL_HOLDER_SIDES,
            holder_positions={
                BoundarySide.LEADING: 0.0,
                BoundarySide.TRAILING: 560.0,
                BoundarySide.TOP: 0.0,
                BoundarySide.BOTTOM: 120.0,
            },
        )

        solved = _solve(
            search_scope=search_scope,
            visible_content=content(
                width=560,
                height=120,
                runs=((0, 100), (110, 210), (220, 320)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
            strip_mode="partial",
            nominal_count=4,
        )

        if isinstance(solved, FrameSequenceSolveResult):
            self.assertFalse(any(slot.sequence_inferred for slot in solved.frame_slots))


if __name__ == "__main__":
    unittest.main()
