from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.frame_slot_solver_support import (
    content,
    dimensions,
    scope,
    solve_sequence,
)
from x5crop.detection.physical import frame_sequence_result as sequence_result
from x5crop.detection.physical.frame_sequence_result import FrameSequenceSolveResult
from x5crop.domain import (
    BoundarySide,
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


class FrameSequenceResultContractTest(unittest.TestCase):
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

        constraints = sequence_result.indexed_anchor_distance_constraints(
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

        constraints = sequence_result.indexed_anchor_distance_constraints(
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
            sequence_result,
            "indexed_anchor_distance_constraints",
            return_value=(),
        ):
            solved = solve_sequence(
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
