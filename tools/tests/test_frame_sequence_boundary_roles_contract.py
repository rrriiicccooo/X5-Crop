from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.support.frame_sequence import (
    content,
    dimensions,
    geometry,
    path,
    scope,
    separator,
    sequence_search_index,
    solve_sequence,
)
from x5crop.detection.physical import frame_sequence_boundary_roles as boundary_roles
from x5crop.detection.physical.frame_sequence_measurements import (
    EdgeConstraint,
    MeasuredFrameConstraint,
)
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
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameBoundarySource,
    ResolvedFrameBoundary,
)
from tools.tests.support.photo_edges import shared_short_axis_fixture
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    PhysicalSearchFact,
    PixelInterval,
)


_ALL_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)


class FrameSequenceBoundaryRolesContractTest(unittest.TestCase):
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
        plan = shared_short_axis_fixture(search_scope)
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
            plan,
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
            plan,
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
        plan = shared_short_axis_fixture(search_scope)
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

        left, right = boundary_roles.corroborate_adjacent_boundary_pair(
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
        plan = shared_short_axis_fixture(search_scope)
        holder_band = separator(100.0, 300.0, plan, supported=True)

        search_index = sequence_search_index(search_scope, (holder_band,))
        trailing_endpoint = next(
            edge
            for edge, _holder_adjacent in search_index.trailing_candidates
            if edge.separator == holder_band.observation
            and edge.external_side == BoundarySide.TRAILING
        )

        self.assertEqual(trailing_endpoint.state, EvidenceState.UNAVAILABLE)

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

        solved = solve_sequence(
            search_scope=search_scope,
            visible_content=content(
                width=430,
                height=100,
                runs=((0, 100), (110, 210), (220, 320), (330, 430)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
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

        solved = solve_sequence(
            search_scope=search_scope,
            visible_content=content(
                width=470,
                height=100,
                runs=((0, 100), (110, 210), (220, 340), (350, 470)),
            ),
            count=4,
            frame_dimensions=dimensions(1.0, 1.0),
        )

        self.assertIsInstance(solved, FrameSequenceSolveFailure)
        self.assertIn(
            PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
            solved.search_outcome.facts,
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
        solved = solve_sequence(
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

        solved = solve_sequence(
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

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
        supports = (
            separator(110.0, 120.0, plan, supported=True),
            separator(220.0, 230.0, plan, supported=True),
        )

        solved = solve_sequence(
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
        self.assertEqual(solved.common_frame_width.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            solved.common_frame_width.width_px,
            PixelInterval.exact(100.0),
        )
        self.assertIsNotNone(solved.common_frame_width.physical_scale_constraint)

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

        solved = solve_sequence(
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

        solved = solve_sequence(
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
        plan = shared_short_axis_fixture(search_scope)
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


if __name__ == "__main__":
    unittest.main()
