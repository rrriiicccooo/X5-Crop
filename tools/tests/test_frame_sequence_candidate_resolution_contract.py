from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.frame_slot_solver_support import (
    content,
    dimensions,
    path,
    scope,
    separator,
    solve_sequence,
)
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.physical import (
    frame_sequence_candidate_resolution as candidate_resolution,
)
from x5crop.detection.physical.frame_sequence_solver import FrameSequenceSolveResult
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameBoundarySource,
    ResolvedFrameBoundary,
)
from x5crop.detection.physical.short_axis import shared_short_axis_plan
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)

_ALL_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)


class FrameSequenceCandidateResolutionContractTest(unittest.TestCase):
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

        resolved = candidate_resolution.resolve_dimension_boundaries_from_common_width(
            slots,
            broad_common_width,
            {},
        )

        self.assertEqual(resolved, slots)

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
        solved = solve_sequence(
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

        resolved = candidate_resolution.resolve_dimension_boundaries_from_common_width(
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
        solved = solve_sequence(
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

        narrowed = candidate_resolution.resolve_dimension_boundaries_from_common_width(
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
        solved = solve_sequence(
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

        resolved = candidate_resolution.resolve_dimension_boundaries_from_common_width(
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
        solved = solve_sequence(
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

        resolved = candidate_resolution.resolve_dimension_boundaries_from_common_width(
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
        solved = solve_sequence(
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

        resolved = candidate_resolution.resolve_dimension_boundaries_from_common_width(
            (source_slot, contradictory_slot),
            solved.common_frame_width,
            {},
        )

        self.assertEqual(resolved[1].leading, incompatible)
