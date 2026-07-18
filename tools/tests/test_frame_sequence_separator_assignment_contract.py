from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.frame_slot_solver_support import path, scope, separator
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.physical import frame_sequence_candidates as candidate_builds
from x5crop.detection.physical import frame_sequence_measurements as measurements
from x5crop.detection.physical import (
    frame_sequence_separator_assignment as separator_assignment,
)
from x5crop.detection.physical import frame_sequence_construction as construction
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
    SeparatorBandCrossAxisSupport,
)


_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)


class FrameSequenceSeparatorAssignmentContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.search_scope = scope(
            width=400,
            height=100,
            leading=0.0,
            trailing=400.0,
            top=0.0,
            bottom=100.0,
            holder_sides=_HOLDER_SIDES,
        )
        self.short_axis = shared_short_axis_plan(self.search_scope)

    def test_one_sided_path_is_a_boundary_anchor_not_a_hard_separator(
        self,
    ) -> None:
        support = separator(
            190.0,
            210.0,
            self.short_axis,
            leading_supported=True,
            trailing_supported=False,
            band_supported=True,
        )

        leading, trailing = construction._separator_edge_candidates(
            (support,),
            self.search_scope,
        )
        internal_leading = tuple(
            edge for edge, _ in leading if edge.external_side is None
        )
        internal_trailing = tuple(
            edge for edge, _ in trailing if edge.external_side is None
        )

        self.assertEqual(internal_leading, ())
        self.assertEqual(len(internal_trailing), 1)
        self.assertEqual(
            internal_trailing[0].position,
            support.observation.leading_edge,
        )
        self.assertEqual(internal_trailing[0].state, EvidenceState.UNAVAILABLE)

        def inferred(position: float, name: str) -> measurements.EdgeConstraint:
            return measurements.EdgeConstraint(
                position=PixelInterval.exact(position),
                basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
                state=EvidenceState.UNAVAILABLE,
                geometry_state=BoundaryGeometryState.RESOLVED,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(name),
                    (MeasurementIdentity.FRAME_DIMENSIONS,),
                    "synthetic candidate boundary",
                ),
            )

        following_leading = separator_assignment.observed_band_edges(support)[1]
        promoted = separator_assignment.candidate_specific_separator_edge_roles(
            (
                measurements.MeasuredFrameConstraint(
                    inferred(0.0, "first-leading"),
                    internal_trailing[0],
                    PixelInterval.exact(190.0),
                    True,
                    False,
                    False,
                    0.0,
                ),
                measurements.MeasuredFrameConstraint(
                    following_leading,
                    inferred(400.0, "second-trailing"),
                    PixelInterval.exact(190.0),
                    True,
                    False,
                    False,
                    0.0,
                ),
            ),
        )
        self.assertEqual(
            promoted[0].trailing.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            promoted[1].leading.state,
            EvidenceState.UNAVAILABLE,
        )
        resolved, _ = candidate_builds.resolve_edge_constraint(
            1,
            BoundarySide.TRAILING,
            promoted[0].trailing,
        )
        self.assertTrue(resolved.independently_observed)
        self.assertEqual(
            construction.interior_separator_supports(
                (support,),
                self.search_scope,
            ),
            (),
        )

    def test_two_sided_path_remains_a_complete_separator(self) -> None:
        support = separator(
            190.0,
            210.0,
            self.short_axis,
            supported=True,
        )

        leading, trailing = construction._separator_edge_candidates(
            (support,),
            self.search_scope,
        )

        self.assertEqual(
            len(tuple(edge for edge, _ in leading if edge.external_side is None)),
            1,
        )
        self.assertEqual(
            len(tuple(edge for edge, _ in trailing if edge.external_side is None)),
            1,
        )
        self.assertEqual(
            construction.interior_separator_supports(
                (support,),
                self.search_scope,
            ),
            (support,),
        )

    def test_band_path_without_measured_edges_is_search_only(self) -> None:
        support = separator(
            190.0,
            210.0,
            self.short_axis,
            leading_supported=False,
            trailing_supported=False,
            band_supported=True,
        )

        leading, trailing = construction._separator_edge_candidates(
            (support,),
            self.search_scope,
        )
        geometry_leading, geometry_trailing = (
            construction._separator_geometry_edge_candidates(
                (support,),
                self.search_scope,
            )
        )

        self.assertEqual(
            tuple(edge for edge, _ in leading if edge.external_side is None),
            (),
        )
        self.assertEqual(
            tuple(edge for edge, _ in trailing if edge.external_side is None),
            (),
        )
        self.assertTrue(geometry_leading)
        self.assertTrue(geometry_trailing)
        self.assertEqual(
            construction.interior_separator_supports(
                (support,),
                self.search_scope,
            ),
            (),
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

        resolved = separator_assignment.assign_unique_separator_observations(
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

        resolved = separator_assignment.assign_unique_separator_observations(
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


if __name__ == "__main__":
    unittest.main()
