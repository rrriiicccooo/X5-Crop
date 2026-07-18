from __future__ import annotations

import unittest

from tools.tests.frame_slot_solver_support import scope, separator
from x5crop.detection.physical import frame_sequence_measurements as measurements
from x5crop.detection.physical import frame_sequence_solver as solver
from x5crop.detection.physical.model import (
    BoundaryGeometryState,
    FrameBoundarySource,
)
from x5crop.detection.physical.short_axis import shared_short_axis_plan
from x5crop.domain import (
    BoundarySide,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)


_HOLDER_SIDES = (
    BoundarySide.LEADING,
    BoundarySide.TRAILING,
    BoundarySide.TOP,
    BoundarySide.BOTTOM,
)


class SeparatorEdgePathSolverContractTest(unittest.TestCase):
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

        leading, trailing = solver._separator_edge_candidates(
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

        following_leading = solver._observed_band_edges(support)[1]
        promoted = solver._candidate_specific_separator_edge_roles(
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
        resolved, _ = solver._resolution(
            1,
            BoundarySide.TRAILING,
            promoted[0].trailing,
        )
        self.assertTrue(resolved.independently_observed)
        self.assertEqual(
            solver._interior_separator_supports(
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

        leading, trailing = solver._separator_edge_candidates(
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
            solver._interior_separator_supports(
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

        leading, trailing = solver._separator_edge_candidates(
            (support,),
            self.search_scope,
        )
        geometry_leading, geometry_trailing = (
            solver._separator_geometry_edge_candidates(
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
            solver._interior_separator_supports(
                (support,),
                self.search_scope,
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
