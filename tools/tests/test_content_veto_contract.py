from __future__ import annotations

from types import SimpleNamespace
import unittest

from x5crop.detection.evidence.content_occupancy_model import (
    ContentOccupancyObservation,
    ContentOccupancyObservationSet,
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
    PositionSource,
)
from x5crop.detection.photo_geometry.output_model import FrameBoundaryGeometry
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
            local_outward_departure_px=0.0,
            position_source=PositionSource.OBSERVED_TRANSITION,
            position_observation_ids=(
                ObservationId(f"boundary:{role.value}:{position}"),
            ),
            named_position_inference=None,
        )

    return SimpleNamespace(
        lane_ordinal=1,
        start=boundary(BoundaryRole.START, start),
        end=boundary(BoundaryRole.END, end),
        top=boundary(BoundaryRole.TOP, 10.0),
        bottom=boundary(BoundaryRole.BOTTOM, 20.0),
    )


def make_content_placement(frames: tuple[object, ...], _relations: tuple[object, ...]):
    return SimpleNamespace(
        placement_id="placement:content",
        output_slot_count=len(frames),
        width_axis=BoundaryAxis.X,
        frames=frames,
    )


def required_footprints(
    frames: tuple[object, ...],
    *,
    sequence_bleed: float = 0.0,
    cross_bleed: float = 0.0,
):
    return tuple(
        (
            (
                frame.start.canonical_position_px - sequence_bleed,
                frame.top.canonical_position_px - cross_bleed,
            ),
            (
                frame.end.canonical_position_px + sequence_bleed,
                frame.top.canonical_position_px - cross_bleed,
            ),
            (
                frame.end.canonical_position_px + sequence_bleed,
                frame.bottom.canonical_position_px + cross_bleed,
            ),
            (
                frame.start.canonical_position_px - sequence_bleed,
                frame.bottom.canonical_position_px + cross_bleed,
            ),
        )
        for frame in frames
    )


def assess(
    frames: tuple[object, ...],
    observation: ContentOccupancyObservationSet,
    *,
    sequence_bleed: float = 0.0,
    cross_bleed: float = 0.0,
):
    placement = make_content_placement(frames, ())
    return content_veto_assessment(
        placement,
        required_footprints(
            frames,
            sequence_bleed=sequence_bleed,
            cross_bleed=cross_bleed,
        ),
        build_content_topology_index(observation, layout="horizontal"),
    )


class ContentVetoContractTest(unittest.TestCase):
    def test_start_end_and_contact_content_are_neutral(self) -> None:
        outside_observation = make_observation(Box(0, 12, 5, 16))
        outside = assess(
            (make_frame(10.0, 20.0),),
            outside_observation,
        )
        contact_observation = make_observation(Box(18, 12, 22, 16))
        contact = assess(
            (make_frame(10.0, 20.0), make_frame(20.0, 30.0)),
            contact_observation,
        )
        overlap = assess(
            (make_frame(10.0, 21.0), make_frame(19.0, 30.0)),
            contact_observation,
        )
        self.assertFalse(outside.vetoed)
        self.assertFalse(contact.vetoed)
        self.assertFalse(overlap.vetoed)

    def test_only_slot_crop_or_normal_separator_crossing_vetoes(self) -> None:
        slot_observation = make_observation(Box(12, 8, 16, 13))
        slot = assess(
            (make_frame(10.0, 20.0),),
            slot_observation,
        )
        separator_observation = make_observation(Box(16, 12, 24, 16))
        separator = assess(
            (make_frame(10.0, 18.0), make_frame(22.0, 30.0)),
            separator_observation,
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
        corner = assess(
            (make_frame(10.0, 20.0),),
            make_observation(Box(9, 8, 11, 13)),
        )
        self.assertFalse(corner.vetoed)

    def test_content_one_cell_inside_corner_is_still_edge_interior(self) -> None:
        assessment = assess(
            (make_frame(10.0, 20.0),),
            make_observation(Box(10, 8, 14, 13)),
        )
        self.assertIn(
            ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
            {item.reason for item in assessment.facts},
        )

    def test_large_component_vetoes_where_one_local_span_crosses_edge_interior(
        self,
    ) -> None:
        observation = make_observation(Box(0, 8, 16, 13))
        assessment = assess(
            (make_frame(10.0, 20.0),),
            observation,
        )
        self.assertIn(
            ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
            {item.reason for item in assessment.facts},
        )

    def test_content_inside_final_bleed_is_not_vetoed(self) -> None:
        observation = make_observation(Box(12, 8, 16, 14))
        self.assertTrue(
            assess((make_frame(10.0, 20.0),), observation).vetoed
        )
        assessment = assess(
            (make_frame(10.0, 20.0),),
            observation,
            cross_bleed=2.0,
        )
        self.assertFalse(assessment.vetoed)

    def test_content_beyond_final_bleed_is_vetoed(self) -> None:
        assessment = assess(
            (make_frame(10.0, 20.0),),
            make_observation(Box(12, 6, 16, 12)),
            cross_bleed=2.0,
        )
        self.assertEqual(
            {item.reason for item in assessment.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )

    def test_outer_content_is_judged_against_final_sequence_bleed(self) -> None:
        observation = make_observation(Box(18, 12, 24, 16))
        without_bleed = assess((make_frame(10.0, 20.0),), observation)
        with_bleed = assess(
            (make_frame(10.0, 20.0),),
            observation,
            sequence_bleed=4.0,
        )

        self.assertEqual(
            {item.reason for item in without_bleed.facts},
            {ContentVetoReason.OUTER_SLOT_CONTENT_OMITTED},
        )
        self.assertFalse(with_bleed.vetoed)

    def test_sloped_edge_uses_the_exact_final_polygon(self) -> None:
        placement = make_content_placement((make_frame(10.0, 20.0),), ())
        footprint = (
            (10.0, 10.0),
            (20.0, 14.0),
            (20.0, 20.0),
            (10.0, 20.0),
        )
        assessment = content_veto_assessment(
            placement,
            (footprint,),
            build_content_topology_index(
                make_observation(Box(16, 11, 19, 16)),
                layout="horizontal",
            ),
        )

        self.assertEqual(
            {item.reason for item in assessment.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )


if __name__ == "__main__":
    unittest.main()
