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
from x5crop.detection.physical import frame_sequence_candidates as candidate_builds
from x5crop.detection.physical import frame_sequence_common_width as width_resolution
from x5crop.detection.physical import frame_sequence_measurements as measurements
from x5crop.detection.physical import frame_sequence_solver as solver_module
from x5crop.detection.physical import model as physical_model
from x5crop.detection.physical.frame_dimensions import frame_dimension_evidence
from x5crop.detection.physical.frame_sequence_solver import (
    FrameSequenceSolveFailure,
    FrameSequenceSolveResult,
    _dimension_frame_constraints,
    _measured_frame_search_space,
    _measured_sequence_build,
    _uncorroborated_overlap_extent,
    _unexplained_spacing_extent,
    solve_frame_sequence,
)
from x5crop.detection.physical.frame_sequence_common_width import (
    CommonWidthHypothesis,
    DimensionPlacementHypothesis,
    measured_width_hypotheses,
)
from x5crop.detection.physical.frame_sequence_measurements import (
    EdgeConstraint,
    MeasuredFrameConstraint,
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
        build = candidate_builds.SequenceBuild(
            slots=slots,
            long_axis_assignments=geometry.long_axis_assignments,
            separator_bindings=(),
            spacings=geometry.inter_frame_spacings,
            frame_width_px=geometry.common_frame_width.width_px,
            short_axis=geometry.shared_short_axis,
            residuals=geometry.residuals,
            objectives=candidate_builds.SequenceBuildObjectives(
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
        build = candidate_builds.SequenceBuild(
            slots=slots,
            long_axis_assignments=geometry.long_axis_assignments,
            separator_bindings=(),
            spacings=geometry.inter_frame_spacings,
            frame_width_px=geometry.common_frame_width.width_px,
            short_axis=geometry.shared_short_axis,
            residuals=geometry.residuals,
            objectives=candidate_builds.SequenceBuildObjectives(
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
        build = candidate_builds.SequenceBuild(
            slots=slots,
            long_axis_assignments=geometry.long_axis_assignments,
            separator_bindings=(),
            spacings=geometry.inter_frame_spacings,
            frame_width_px=geometry.common_frame_width.width_px,
            short_axis=geometry.shared_short_axis,
            residuals=geometry.residuals,
            objectives=candidate_builds.SequenceBuildObjectives(
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
        plausible = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 102.0),
            4,
        )
        frequent_texture = width_resolution.RecurringBoundaryWidthHypothesis(
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
                width_resolution.RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(100.0),
                    9,
                ),
                width_resolution.RecurringBoundaryWidthHypothesis(
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
        separator_aligned = width_resolution.RecurringBoundaryWidthHypothesis(
            PixelInterval(100.0, 104.0),
            4,
        )
        short_axis_aligned = width_resolution.RecurringBoundaryWidthHypothesis(
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
        repeated = width_resolution.repeated_width_contributor_sets

        with patch.object(
            width_resolution,
            "repeated_width_contributor_sets",
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

    def test_dimension_search_uses_observed_separator_incumbent(self) -> None:
        class Build:
            __hash__ = object.__hash__

            def __init__(self) -> None:
                leading = SimpleNamespace(position=PixelInterval.exact(0.0))
                trailing = SimpleNamespace(position=PixelInterval.exact(100.0))
                self.slots = (
                    SimpleNamespace(leading=leading, trailing=trailing),
                )
                self.objectives = candidate_builds.SequenceBuildObjectives(
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
                CommonWidthHypothesis(
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
                self.objectives = candidate_builds.SequenceBuildObjectives(
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
                width_resolution.RecurringBoundaryWidthHypothesis(
                    PixelInterval.exact(100.0),
                    2,
                ),
                width_resolution.RecurringBoundaryWidthHypothesis(
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
                CommonWidthHypothesis(
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

        def edge(position: float) -> EdgeConstraint:
            observation = paths[position]
            return EdgeConstraint(
                position=observation.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        constraints = tuple(
            MeasuredFrameConstraint(
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

        def edge(position: float) -> EdgeConstraint:
            observation = long_paths[position]
            return EdgeConstraint(
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
        hypothesis = DimensionPlacementHypothesis(
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
        inferred = EdgeConstraint(
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
        observed = EdgeConstraint(
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
        constraint = EdgeConstraint(
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

        def edge(position: float) -> EdgeConstraint:
            path = paths[position]
            return EdgeConstraint(
                position=path.position,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=path.provenance,
                path=path,
            )

        constraints = (
            MeasuredFrameConstraint(
                leading=edge(100.0),
                trailing=edge(200.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
                leading=edge(300.0),
                trailing=edge(400.0),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )

        self.assertEqual(measured_width_hypotheses(constraints), ())
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


    def test_disjoint_observed_frame_width_is_not_dimension_compatible(self) -> None:
        def observed_edge(
            minimum: float,
            maximum: float,
            label: str,
        ) -> EdgeConstraint:
            observation = path(
                BoundaryAxis.LONG,
                (minimum + maximum) / 2.0,
                label,
            )
            return EdgeConstraint(
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
        constraint = MeasuredFrameConstraint(
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

        def edge(minimum: float, maximum: float, label: str) -> EdgeConstraint:
            return EdgeConstraint(
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
        ) -> MeasuredFrameConstraint:
            width = PixelInterval(*trailing).minus(PixelInterval(*leading))
            return MeasuredFrameConstraint(
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
        alternatives = candidate_builds.physically_preferred_builds((overcontained, aligned))
        self.assertEqual(alternatives, (overcontained, aligned))


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

        def raw(position: float, interval: PixelInterval) -> EdgeConstraint:
            observation = paths[position]
            return EdgeConstraint(
                position=interval,
                basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=observation.provenance,
                path=observation,
            )

        def separator_edge(side: BoundarySide) -> EdgeConstraint:
            observation = separator_support.observation
            return EdgeConstraint(
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
            MeasuredFrameConstraint(
                leading=raw(0.0, PixelInterval.exact(0.0)),
                trailing=raw(100.0, PixelInterval(95.0, 105.0)),
                width_px=PixelInterval(95.0, 105.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
                leading=raw(105.0, PixelInterval(100.0, 110.0)),
                trailing=separator_edge(BoundarySide.TRAILING),
                width_px=PixelInterval(100.0, 110.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
                leading=separator_edge(BoundarySide.LEADING),
                trailing=raw(320.0, PixelInterval(315.0, 325.0)),
                width_px=PixelInterval(95.0, 105.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
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
                DimensionPlacementHypothesis(
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
                candidate_builds,
                "build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                candidate_builds,
                "physically_preferred_builds",
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
                candidate_builds,
                "build_preserves_visible_content",
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
                candidate_builds,
                "physically_preferred_builds",
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
                candidate_builds,
                "build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                candidate_builds,
                "physically_preferred_builds",
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
                candidate_builds,
                "build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                candidate_builds,
                "physically_preferred_builds",
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
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
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
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
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
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
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
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
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

        def edge(position: float, label: str) -> EdgeConstraint:
            return EdgeConstraint(
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
            MeasuredFrameConstraint(
                leading=edge(400.0, "isolated-1-leading"),
                trailing=edge(500.0, "isolated-1-trailing"),
                width_px=PixelInterval.exact(100.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
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
                candidate_builds,
                "build_preserves_visible_content",
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
                candidate_builds,
                "physically_preferred_builds",
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
                candidate_builds,
                "build_preserves_visible_content",
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
                candidate_builds,
                "physically_preferred_builds",
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
                    and measurements.separator_edge_path_is_supported(edge)
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
