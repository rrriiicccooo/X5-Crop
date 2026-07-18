from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.frame_slot_solver_support import (
    content,
    dimensions,
    path,
    scope,
    separator,
    solve_sequence,
)
from x5crop.detection.physical import (
    frame_sequence_candidate_resolution as candidate_resolution,
)
from x5crop.detection.physical import frame_sequence_candidates as candidate_builds
from x5crop.detection.physical import frame_sequence_common_width as width_resolution
from x5crop.detection.physical import sequence_completion
from x5crop.detection.physical.frame_sequence_solver import FrameSequenceSolveResult
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameBoundarySource,
    FrameContentOccupancy,
    FrameSlot,
    ResolvedFrameBoundary,
)
from x5crop.detection.physical.short_axis import shared_short_axis_plan
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    PixelInterval,
)

_ALL_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)


class FrameSequenceCompletionContractTest(unittest.TestCase):
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

        slots, _ = sequence_completion.apply_edge_occlusion_inference(
            (unproven_edge_slot,),
            (),
            {BoundarySide.TRAILING: holder_boundary},
            solved.common_frame_width,
            "full",
        )

        self.assertIsNone(slots[-1].edge_occlusion)
        self.assertEqual(slots[-1].trailing, unproven_edge_slot.trailing)

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
                sequence_completion,
                "build_supports_resolved_nominal_slots",
                return_value=True,
            ),
        ):
            resolved = sequence_completion.direct_nominal_geometry_is_complete(
                (build,),
                content(width=300, height=100, runs=()),
                {},
                SimpleNamespace(),
                SimpleNamespace(),
            )

        self.assertTrue(resolved)

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
                sequence_completion,
                "build_supports_resolved_nominal_slots",
                side_effect=lambda build, *args: build is complete,
            ),
        ):
            resolved = (
                sequence_completion.direct_nominal_geometry_is_complete(
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
                sequence_completion,
                "build_supports_resolved_nominal_slots",
                return_value=True,
            ),
        ):
            resolved = (
                sequence_completion.direct_nominal_geometry_is_complete(
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
            sequence_completion.build_has_geometry_only_slot(build)
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
                candidate_resolution,
                "resolve_build_physical_boundaries",
                return_value=(build, common_width),
            ),
            patch.object(
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
        ):
            self.assertFalse(
                sequence_completion.build_supports_resolved_nominal_slots(
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
                candidate_resolution,
                "resolve_build_physical_boundaries",
                return_value=(build, common_width),
            ),
            patch.object(
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "_full_sequence_endpoint_slack_is_sub_frame",
                return_value=True,
            ),
        ):
            self.assertFalse(
                sequence_completion.build_supports_resolved_nominal_slots(
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
                candidate_resolution,
                "resolve_build_physical_boundaries",
                return_value=(resolved_build, common_width),
            ),
            patch.object(
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
            patch.object(
                sequence_completion,
                "_full_sequence_endpoint_slack_is_sub_frame",
                return_value=True,
            ),
        ):
            self.assertFalse(
                sequence_completion.build_supports_resolved_nominal_slots(
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
                candidate_resolution,
                "resolve_build_physical_boundaries",
                return_value=(SimpleNamespace(slots=resolved_slots), common_width),
            ),
        ):
            self.assertTrue(
                sequence_completion.build_does_not_contradict_common_width(
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
                candidate_resolution,
                "resolve_build_physical_boundaries",
                return_value=(SimpleNamespace(slots=resolved_slots), common_width),
            ),
            patch.object(
                width_resolution,
                "slots_do_not_contradict_supported_common_width",
                return_value=True,
            ),
        ):
            self.assertFalse(
                sequence_completion.build_does_not_contradict_common_width(
                    build,
                    {},
                    SimpleNamespace(),
                    SimpleNamespace(),
                )
            )
