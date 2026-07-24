from __future__ import annotations

from dataclasses import fields, replace
import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from x5crop.configuration.candidate import SequenceSolverParameters
from tools.tests.support.frame_sequence import (
    content,
    dimensions,
    geometry,
    scope,
    separator,
    sequence_search_index,
    solve_sequence,
)
from tools.tests.support.physical_gates import candidate_fixture
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.detection.candidate.model import sequence_proof_paths_for_geometry
from x5crop.detection.physical import frame_sequence_candidates as candidate_builds
from x5crop.detection.physical import (
    frame_sequence_candidate_resolution as candidate_resolution,
)
from x5crop.detection.physical import frame_sequence_construction as construction
from x5crop.detection.physical import frame_sequence_common_width as width_resolution
from x5crop.detection.physical import (
    frame_sequence_separator_assignment as separator_assignment,
)
from x5crop.detection.physical import sequence_completion
from x5crop.detection.physical.frame_dimensions import frame_dimension_evidence
from x5crop.detection.physical.frame_sequence_construction import (
    _measured_sequence_build,
)
from x5crop.detection.physical.frame_sequence_solver import (
    solve_frame_sequence,
)
from x5crop.detection.physical.frame_sequence_result import (
    FrameSequenceSolveFailure,
    FrameSequenceSolveResult,
)
from x5crop.detection.physical.frame_sequence_measurements import (
    EdgeConstraint,
    MeasuredFrameConstraint,
)
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameBoundarySource,
    FrameEdgeOcclusionInference,
    GeometryIdentityError,
    SeparatorBandAssignment,
)
from tools.tests.support.photo_edges import shared_short_axis_fixture
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
    ShortAxisMeasurementSpan,
)

_ALL_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)

class FrameSequenceSolverContractTest(unittest.TestCase):
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
        plan = shared_short_axis_fixture(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
            )
        )
        solved = solve_sequence(
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

    def test_separator_assignment_carries_global_frame_width_feasibility(
        self,
    ) -> None:
        self.assertIn(
            "frame_width_px",
            {field.name for field in fields(SeparatorBandAssignment)},
        )

    def test_separator_assignment_requires_observed_spacing_conservation(
        self,
    ) -> None:
        geometry_with_separator = candidate_fixture().geometry
        spacing = geometry_with_separator.inter_frame_spacings[0]
        contradictory_spacing = replace(
            spacing,
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("contradictory_separator_spacing"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "geometry hypothesis contradicting an assigned separator",
            ),
        )

        with self.assertRaisesRegex(
            GeometryIdentityError,
            "assigned separator spacing must preserve its observation",
        ):
            replace(
                geometry_with_separator,
                inter_frame_spacings=(contradictory_spacing,),
            )

    def test_separator_assignment_requires_shared_short_axis_measurement(
        self,
    ) -> None:
        geometry_with_separator = candidate_fixture().geometry
        assignment = geometry_with_separator.separator_assignments[0]
        span = assignment.cross_axis_measurement.short_axis_span
        foreign_span = ShortAxisMeasurementSpan(
            top=span.top.plus(PixelInterval.exact(1.0)),
            bottom=span.bottom.plus(PixelInterval.exact(1.0)),
            provenance=span.provenance,
        )
        foreign_assignment = replace(
            assignment,
            cross_axis_measurement=replace(
                assignment.cross_axis_measurement,
                short_axis_span=foreign_span,
            ),
        )

        with self.assertRaisesRegex(
            GeometryIdentityError,
            "assigned separator continuity must use the shared short axis",
        ):
            replace(
                geometry_with_separator,
                separator_assignments=(foreign_assignment,),
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
        plan = shared_short_axis_fixture(search_scope)
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
            dimensions(0.9, 1.0),
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
        plan = shared_short_axis_fixture(search_scope)
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
            construction,
            "_measured_path_builds",
            return_value=((), 0, False),
        ) as measured_builds:
            solved = solve_sequence(
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

    def test_unassigned_gray_path_has_no_physical_measurement_quality(self) -> None:
        gray_path = next(
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
            and str(path.provenance.observation_id).startswith("internal_path:")
        )
        constraint = EdgeConstraint(
            position=gray_path.position,
            basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            state=EvidenceState.UNAVAILABLE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            provenance=gray_path.provenance,
            path=gray_path,
        )

        self.assertEqual(constraint.measurement_quality, 0.0)

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
        plan = shared_short_axis_fixture(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=False),
            separator(210.0, 220.0, plan, supported=False),
            separator(320.0, 330.0, plan, supported=False),
            separator(430.0, 440.0, plan, supported=False),
        )

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (100.0, 110.0),
                (210.0, 220.0),
                (320.0, 330.0),
                (430.0, 440.0),
            )
        )
        solved = solve_sequence(
            search_scope=search_scope,
            visible_content=content(width=660, height=100, runs=((50, 650),)),
            count=6,
            frame_dimensions=dimensions(1.0, 1.0),
            supports=supports,
        )

        self.assertIsInstance(solved, FrameSequenceSolveFailure)
        self.assertIn(
            PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
            solved.search_outcome.facts,
        )

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
        plan = shared_short_axis_fixture(search_scope)
        supports = (
            separator(10.0, 20.0, plan, supported=True),
            separator(470.0, 510.0, plan, supported=True),
            separator(960.0, 1_000.0, plan, supported=True),
            separator(1_450.0, 1_490.0, plan, supported=True),
        )

        with patch.object(
            construction,
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
        plan = shared_short_axis_fixture(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(400.0, 410.0, plan, supported=True),
        )

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
        supports = (
            separator(210.0, 220.0, plan, supported=True),
            separator(400.0, 410.0, plan, supported=True),
        )

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
        supports = (
            separator(0.0, 10.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(400.0, 410.0, plan, supported=True),
        )

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
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

    def test_photo_edge_width_hint_constrains_repeated_unassigned_gray_paths(
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

        solved = solve_sequence(
            search_scope=search_scope,
            visible_content=visible_content,
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(
            tuple(slot.width_px for slot in solved.frame_slots),
            (PixelInterval.exact(100.0),) * 4,
        )
        self.assertEqual(
            solved.frame_width_search_hint.width_px,
            PixelInterval.exact(100.0),
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
        plan = shared_short_axis_fixture(search_scope)

        solved = solve_sequence(
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

        plan = shared_short_axis_fixture(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((100.0, 110.0), (210.0, 220.0), (320.0, 330.0))
        )
        frame_dimensions = dimensions(1.0, 1.0)
        solved = solve_sequence(
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
            geometry(search_scope, supports, frame_dimensions, solved),
            None,
            None,
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
            width=18_800,
            height=2_000,
            leading=0.0,
            trailing=18_800.0,
            top=0.0,
            bottom=2_000.0,
            internal_paths=(15_800.0,),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_fixture(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in (
                (3_000.0, 3_200.0),
                (6_200.0, 6_400.0),
                (9_400.0, 9_600.0),
                (12_600.0, 12_800.0),
            )
        )

        solved = solve_sequence(
            search_scope=search_scope,
            visible_content=content(width=18_800, height=2_000),
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
        self.assertEqual(
            tuple(
                frame_index
                for frame_index, slot in enumerate(solved.frame_slots, start=1)
                if slot.sequence_inferred
            ),
            (6,),
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
        plan = shared_short_axis_fixture(search_scope)
        supports = (
            separator(100.0, 110.0, plan, supported=True),
            separator(210.0, 220.0, plan, supported=True),
            separator(320.0, 330.0, plan, supported=True),
        )
        solved = solve_sequence(
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

    def test_holder_occlusion_is_restricted_to_matching_sequence_endpoint(
        self,
    ) -> None:
        geometry_with_endpoints = candidate_fixture().geometry
        cases = (
            (0, BoundarySide.TRAILING),
            (len(geometry_with_endpoints.frame_slots) - 1, BoundarySide.LEADING),
        )

        for slot_offset, side in cases:
            with self.subTest(slot=slot_offset + 1, side=side.value):
                slot = geometry_with_endpoints.frame_slots[slot_offset]
                holder_boundary = geometry_with_endpoints.holder_safety.boundary(side)
                assert holder_boundary is not None
                visible = (
                    PixelInterval(
                        slot.visible_long_axis.minimum,
                        slot.visible_long_axis.maximum - 10.0,
                    )
                    if side == BoundarySide.TRAILING
                    else PixelInterval(
                        slot.visible_long_axis.minimum + 10.0,
                        slot.visible_long_axis.maximum,
                    )
                )
                wrong_endpoint = replace(
                    slot,
                    visible_long_axis=visible,
                    edge_occlusion=FrameEdgeOcclusionInference(
                        side=side,
                        hidden_width_px=PixelInterval.exact(10.0),
                        holder_boundary_provenance=holder_boundary.provenance,
                    ),
                )
                slots = list(geometry_with_endpoints.frame_slots)
                slots[slot_offset] = wrong_endpoint

                with self.assertRaisesRegex(
                    GeometryIdentityError,
                    "holder occlusion must match the sequence endpoint",
                ):
                    replace(
                        geometry_with_endpoints,
                        frame_slots=tuple(slots),
                    )

    def test_holder_occlusion_requires_positive_hidden_extent(self) -> None:
        provenance = candidate_fixture().geometry.holder_safety.provenance

        with self.assertRaisesRegex(
            ValueError,
            "holder occlusion width must be positive",
        ):
            FrameEdgeOcclusionInference(
                side=BoundarySide.LEADING,
                hidden_width_px=PixelInterval.exact(0.0),
                holder_boundary_provenance=provenance,
            )

    def test_blank_search_does_not_receive_a_preallocated_budget(self) -> None:
        source = inspect.getsource(solve_frame_sequence)

        self.assertNotIn("direct_budget", source)
        self.assertNotIn("blank_budget", source)

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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
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
                construction,
                "sequence_builds_for_count",
                side_effect=sequence_builds,
            ),
            patch.object(
                sequence_completion,
                "direct_nominal_geometry_is_complete",
                return_value=True,
            ),
            patch.object(
                candidate_builds,
                "build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "build_does_not_contradict_common_width",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "build_satisfies_full_endpoint_extent",
                return_value=True,
            ),
            patch.object(
                candidate_resolution,
                "resolve_build_physical_boundaries",
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

    def test_partial_mode_skips_nominal_blank_completion_assessments(self) -> None:
        search_scope = scope(
            width=220,
            height=100,
            leading=0.0,
            trailing=220.0,
            top=0.0,
            bottom=100.0,
            internal_paths=(100.0, 110.0),
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_fixture(search_scope)
        supports = (separator(100.0, 110.0, plan, supported=True),)

        with (
            patch.object(
                sequence_completion,
                "direct_nominal_geometry_is_complete",
                wraps=sequence_completion.direct_nominal_geometry_is_complete,
            ) as direct_complete,
            patch.object(
                sequence_completion,
                "preferred_direct_common_width_is_supported",
                wraps=sequence_completion.preferred_direct_common_width_is_supported,
            ) as common_width_supported,
        ):
            solve_frame_sequence(
                sequence_search_index(search_scope, supports),
                search_scope,
                plan,
                2,
                dimensions(1.0, 1.0),
                content(width=220, height=100),
                100_000,
                strip_mode="partial",
                nominal_count=2,
            )

        direct_complete.assert_not_called()
        common_width_supported.assert_not_called()

    def test_partial_common_width_filter_reuses_build_resolution(self) -> None:
        class CapturedBuilds(Exception):
            pass

        slot = SimpleNamespace(
            sequence_inferred=False,
            visible_long_axis=PixelInterval(10.0, 110.0),
        )
        direct = SimpleNamespace(
            slots=(slot,),
            separator_bindings=(),
            objectives=SimpleNamespace(supported_separator_count=0),
        )
        common_width = SimpleNamespace(state=EvidenceState.UNAVAILABLE)
        search_scope = scope(
            width=220,
            height=100,
            leading=0.0,
            trailing=220.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_ALL_HOLDER_SIDES,
        )
        plan = shared_short_axis_fixture(search_scope)

        def capture(builds):
            raise CapturedBuilds(builds)

        with (
            patch.object(
                construction,
                "sequence_builds_for_count",
                return_value=((direct,), 0, False),
            ),
            patch.object(
                candidate_resolution,
                "resolve_build_physical_boundaries",
                return_value=(direct, common_width),
            ) as resolution,
            patch.object(
                separator_assignment,
                "assign_unique_separator_observations",
                side_effect=lambda build, *_args: build,
            ),
            patch.object(
                candidate_resolution,
                "assign_unique_boundary_path_observations",
                side_effect=lambda build, *_args: build,
            ),
            patch.object(
                candidate_builds,
                "frame_slots_are_strictly_monotonic",
                return_value=True,
            ),
            patch.object(
                candidate_builds,
                "build_preserves_visible_content",
                return_value=True,
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
                    2,
                    dimensions(1.0, 1.0),
                    content(width=220, height=100),
                    100_000,
                    strip_mode="partial",
                    nominal_count=2,
                )

        self.assertEqual(resolution.call_count, 1)

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
        plan = shared_short_axis_fixture(search_scope)

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
            plan,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )
        self.assertIsNotNone(build)
        assert build is not None

        with patch.object(
            construction,
            "sequence_builds_for_count",
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

    def test_full_solver_rejects_visible_slot_geometry_beyond_holder(
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
        plan = shared_short_axis_fixture(search_scope)

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
                leading=edge(0.0, "outside-holder-1-leading"),
                trailing=edge(500.0, "outside-holder-1-trailing"),
                width_px=PixelInterval.exact(500.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
            MeasuredFrameConstraint(
                leading=edge(510.0, "outside-holder-2-leading"),
                trailing=edge(1_010.0, "outside-holder-2-trailing"),
                width_px=PixelInterval.exact(500.0),
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=False,
                trailing_holder_clip_supported=False,
                search_order_residual=0.0,
            ),
        )
        build = _measured_sequence_build(
            constraints,
            plan,
            search_scope.holder_safety.box,
            allow_nominal_slot_sized_gap=False,
        )
        self.assertIsNotNone(build)
        assert build is not None

        with patch.object(
            construction,
            "sequence_builds_for_count",
            return_value=((build,), 1, False),
        ):
            solved = solve_frame_sequence(
                sequence_search_index(search_scope),
                search_scope,
                plan,
                2,
                dimensions(5.0, 1.0),
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
            visible_long_axis=PixelInterval.exact(100.0),
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
        plan = shared_short_axis_fixture(search_scope)

        def capture(builds):
            raise CapturedBuilds(builds)

        with (
            patch.object(
                construction,
                "sequence_builds_for_count",
                side_effect=(
                    ((direct,), 0, False),
                    ((), 0, False),
                ),
            ),
            patch.object(
                sequence_completion,
                "sequence_completed_builds",
                return_value=(sequence_completed,),
            ),
            patch.object(
                sequence_completion,
                "build_supports_resolved_nominal_slots",
                return_value=False,
            ),
            patch.object(
                sequence_completion,
                "direct_nominal_geometry_is_complete",
                return_value=False,
            ),
            patch.object(
                sequence_completion,
                "infer_unique_slot_in_direct_nominal_build",
                side_effect=lambda build, *_args: build,
            ),
            patch.object(
                sequence_completion,
                "preferred_direct_common_width_is_supported",
                return_value=True,
            ),
            patch.object(
                candidate_builds,
                "build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "build_does_not_contradict_common_width",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "build_satisfies_full_endpoint_extent",
                return_value=True,
            ),
            patch.object(
                candidate_resolution,
                "resolve_build_physical_boundaries",
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
            visible_long_axis=PixelInterval.exact(100.0),
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
        plan = shared_short_axis_fixture(search_scope)

        def resolve(build, *_args):
            return (
                resolved_direct if build is direct else resolved_completion,
                common_width,
            )

        def capture(builds):
            raise CapturedBuilds(builds)

        with (
            patch.object(
                construction,
                "sequence_builds_for_count",
                side_effect=(((direct,), 0, False), ((), 0, False)),
            ),
            patch.object(
                sequence_completion,
                "sequence_completed_builds",
                return_value=(sequence_completed,),
            ),
            patch.object(
                sequence_completion,
                "direct_nominal_geometry_is_complete",
                return_value=False,
            ),
            patch.object(
                sequence_completion,
                "infer_unique_slot_in_direct_nominal_build",
                side_effect=lambda build, *_args: build,
            ),
            patch.object(
                sequence_completion,
                "preferred_direct_common_width_is_supported",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "build_supports_resolved_nominal_slots",
                return_value=True,
            ),
            patch.object(
                candidate_builds,
                "build_preserves_visible_content",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "build_does_not_contradict_common_width",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "build_satisfies_full_endpoint_extent",
                return_value=True,
            ),
            patch.object(
                candidate_resolution,
                "resolve_build_physical_boundaries",
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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
        support = separator(100.0, 110.0, plan, supported=True)

        preceding, following = separator_assignment.observed_band_edges(support)

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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
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
        self.assertEqual(
            tuple(
                assignment.observation.provenance.observation_id
                for assignment in solved.separator_assignments
            ),
            (internal_separator.observation.provenance.observation_id,),
        )

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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
        hard_separators = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((110, 120), (220, 230), (330, 340))
        )
        oversized_weak_band = separator(380, 450, plan, supported=False)
        supports = (*hard_separators, oversized_weak_band)

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)

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
        plan = shared_short_axis_fixture(search_scope)
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

        solved = solve_sequence(
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

        solved = solve_sequence(
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

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)

        solved = solve_sequence(
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

        solved = solve_sequence(
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
        solved = solve_sequence(
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

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
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
            plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
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

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
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

    def test_dense_paths_cannot_override_photo_edge_scale_geometry(
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

        solved = solve_sequence(
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
            AssignmentConsensusOutcome.UNCONTESTED,
        )
        self.assertEqual(
            tuple(slot.visible_long_axis for slot in solved.frame_slots),
            tuple(
                PixelInterval(float(start), float(start + 200))
                for start in range(0, 1_000, 200)
            ),
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

        solved = solve_sequence(
            search_scope=search_scope,
            visible_content=visible_content,
            count=12,
            frame_dimensions=dimensions(1.0, 1.0),
            strip_mode="full",
            nominal_count=12,
            maximum_assignment_evaluations=20_000,
        )

        self.assertIsInstance(solved, FrameSequenceSolveFailure)
        assert isinstance(solved, FrameSequenceSolveFailure)
        self.assertIn(
            PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
            solved.search_outcome.facts,
        )
        self.assertFalse(solved.search_outcome.budget_exhausted)
        self.assertLess(solved.assignment_evaluations, 20_000)

    def test_dense_paths_cannot_contest_supported_photo_edge_width(
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
        plan = shared_short_axis_fixture(search_scope)

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
            AssignmentConsensusOutcome.UNCONTESTED,
        )
        self.assertEqual(
            tuple(slot.width_px for slot in solved.frame_slots),
            (PixelInterval.exact(100.0),) * 5,
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
        plan = shared_short_axis_fixture(search_scope)
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
            construction,
            "_dimension_frame_constraints",
            wraps=construction._dimension_frame_constraints,
        ) as dimension_constraints:
            solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
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

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
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
        plan = shared_short_axis_fixture(search_scope)
        supports = tuple(
            separator(start, end, plan, supported=True)
            for start, end in ((100, 110), (210, 220), (320, 330), (430, 440))
        )
        searched_counts: list[int] = []
        original_search = construction.sequence_builds_for_count

        def tracked_search(*args, **kwargs):
            searched_counts.append(args[3])
            return original_search(*args, **kwargs)

        with patch.object(
            construction,
            "sequence_builds_for_count",
            side_effect=tracked_search,
        ):
            solved = solve_sequence(
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

        solved = solve_sequence(
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
