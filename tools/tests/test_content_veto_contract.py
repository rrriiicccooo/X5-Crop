from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from x5crop.detection.evidence.content_occupancy_model import (
    ContentOccupancyObservation,
    ContentOccupancyObservationSet,
)
from x5crop.detection.photo_geometry.boundary_geometry import (
    outward_boundary_projection,
)
from x5crop.detection.photo_geometry.content_topology import (
    build_content_topology_index,
)
from x5crop.detection.photo_geometry.content_veto import content_veto_assessment
from x5crop.detection.photo_geometry.content_veto_model import ContentVetoReason
from x5crop.detection.photo_geometry.line_observations import SourceCoordinateLine
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    DirectionAuthority,
    PositionSource,
)
from x5crop.detection.photo_geometry.output_model import FrameBoundaryGeometry
from x5crop.detection.photo_geometry.template_model import LocalAdvanceKind
from x5crop.domain import Box, FiniteInterval, ObservationId


def make_observation(box: Box) -> ContentOccupancyObservationSet:
    identity = ObservationId(
        f"content:{box.left}:{box.top}:{box.right}:{box.bottom}"
    )
    observation = ContentOccupancyObservation(
        observation_id=identity,
        lane_id="lane:0",
        source_box=box,
        source_cells=tuple(
            Box(left, top, left + 1, top + 1)
            for left in range(box.left, box.right)
            for top in range(box.top, box.bottom)
        ),
        reliability=0.95,
    )
    return ContentOccupancyObservationSet(
        lane_id="lane:0",
        observations=(observation,),
        long_step_px=1,
        cross_step_px=1,
        long_sample_count=16,
        cross_sample_count=16,
        occupied_cell_count=box.width * box.height,
        long_support_depth_px=1,
        cross_support_depth_px=1,
    )


def make_frame(
    start: float,
    end: float,
    *,
    direction_degrees: FiniteInterval = FiniteInterval.exact(0.0),
):
    def boundary(role: BoundaryRole, position: float) -> FrameBoundaryGeometry:
        cross = role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        return FrameBoundaryGeometry(
            role=role,
            line=SourceCoordinateLine(
                normal_x=0.0 if cross else 1.0,
                normal_y=1.0 if cross else 0.0,
                offset_px=position,
                support_projection_px=FiniteInterval(0.0, 40.0),
                source_axis_long=BoundaryAxis.X,
            ),
            reference_trace_px=15.0,
            canonical_position_px=position,
            full_position_interval_px=FiniteInterval.exact(position),
            full_direction_interval_degrees=direction_degrees,
            position_source=PositionSource.OBSERVED_TRANSITION,
            position_observation_ids=(
                ObservationId(f"boundary:{role.value}:{position}"),
            ),
            named_position_inference=None,
            direction_authority=(
                DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
                if cross
                else DirectionAuthority.BOUNDED_SEQUENCE_EDGE_DIRECTION
            ),
            direction_reference_id="direction:test",
        )

    return SimpleNamespace(
        lane_ordinal=1,
        start=boundary(BoundaryRole.START, start),
        end=boundary(BoundaryRole.END, end),
        top=boundary(BoundaryRole.TOP, 10.0),
        bottom=boundary(BoundaryRole.BOTTOM, 20.0),
    )


def make_content_placement(frames: tuple[object, ...], _relations: tuple[object, ...]):
    return SimpleNamespace(placement_id="placement:content", frames=frames)


class ContentVetoContractTest(unittest.TestCase):
    def test_start_end_and_contact_content_are_neutral(self) -> None:
        outside_observation = make_observation(Box(0, 12, 5, 16))
        outside = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(outside_observation, layout="horizontal"),
        )
        contact_observation = make_observation(Box(18, 12, 22, 16))
        contact = content_veto_assessment(
            make_content_placement(
                (make_frame(10.0, 20.0), make_frame(20.0, 30.0)),
                (LocalAdvanceKind.CONTACT,),
            ),
            build_content_topology_index(contact_observation, layout="horizontal"),
        )
        overlap = content_veto_assessment(
            make_content_placement(
                (make_frame(10.0, 21.0), make_frame(19.0, 30.0)),
                (LocalAdvanceKind.OVERLAP,),
            ),
            build_content_topology_index(contact_observation, layout="horizontal"),
        )
        self.assertFalse(outside.vetoed)
        self.assertFalse(contact.vetoed)
        self.assertFalse(overlap.vetoed)

    def test_only_slot_crop_or_normal_separator_crossing_vetoes(self) -> None:
        slot_observation = make_observation(Box(12, 8, 16, 13))
        slot = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(slot_observation, layout="horizontal"),
        )
        separator_observation = make_observation(Box(16, 12, 24, 16))
        separator = content_veto_assessment(
            make_content_placement(
                (make_frame(10.0, 18.0), make_frame(22.0, 30.0)),
                (LocalAdvanceKind.NOMINAL,),
            ),
            build_content_topology_index(separator_observation, layout="horizontal"),
        )
        self.assertEqual(
            {item.reason for item in slot.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )
        self.assertEqual(
            {item.reason for item in separator.facts},
            {ContentVetoReason.SEPARATOR_CORE_CONTENT_CROSSING},
        )
    def test_edge_intersection_at_slot_corner_is_not_content_veto(self) -> None:
        corner = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(
                make_observation(Box(9, 8, 11, 13)),
                layout="horizontal",
            ),
        )
        self.assertFalse(corner.vetoed)

    def test_content_one_cell_inside_corner_is_still_edge_interior(self) -> None:
        assessment = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(
                make_observation(Box(10, 8, 14, 13)),
                layout="horizontal",
            ),
        )
        self.assertIn(
            ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
            {item.reason for item in assessment.facts},
        )

    def test_large_component_vetoes_where_one_local_span_crosses_edge_interior(
        self,
    ) -> None:
        observation = make_observation(Box(0, 8, 16, 13))
        assessment = content_veto_assessment(
            make_content_placement((make_frame(10.0, 20.0),), ()),
            build_content_topology_index(observation, layout="horizontal"),
        )
        self.assertIn(
            ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
            {item.reason for item in assessment.facts},
        )

    def test_content_veto_uses_the_safe_envelope_discard_edge(self) -> None:
        frame = make_frame(10.0, 20.0)
        frame.top = replace(
            frame.top,
            full_position_interval_px=FiniteInterval(10.0, 12.0),
        )
        assessment = content_veto_assessment(
            make_content_placement((frame,), ()),
            build_content_topology_index(
                make_observation(Box(12, 8, 16, 13)),
                layout="horizontal",
            ),
        )
        self.assertEqual(
            {item.reason for item in assessment.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )

    def test_angled_boundary_projects_at_each_real_content_cell(self) -> None:
        frame = make_frame(
            10.0,
            20.0,
            direction_degrees=FiniteInterval.exact(45.0),
        )
        top = outward_boundary_projection(frame.top).coordinate_interval(
            FiniteInterval(20.0, 22.0)
        )
        start = outward_boundary_projection(frame.start).coordinate_interval(
            FiniteInterval(20.0, 22.0)
        )
        self.assertEqual(top, FiniteInterval(15.0, 17.0))
        self.assertAlmostEqual(start.minimum, 3.0)
        self.assertAlmostEqual(start.maximum, 5.0)


if __name__ == "__main__":
    unittest.main()
