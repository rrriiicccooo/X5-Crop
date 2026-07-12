from __future__ import annotations

import unittest
from inspect import signature

from x5crop.domain import (
    Box,
    CropEnvelope,
    FrameBoundaryReference,
)
from x5crop.output.frame_bleed import apply_frame_bleed, frame_bleed_plan
from x5crop.output.model import (
    AxisBleedParameters,
    FrameOverlapRequirement,
    OutputGeometry,
)


class InterFrameOverlapBleedTest(unittest.TestCase):
    def test_frame_bleed_layout_is_explicit(self) -> None:
        self.assertIs(
            signature(frame_bleed_plan).parameters["layout"].default,
            signature(frame_bleed_plan).empty,
        )

    def test_overlap_protection_only_expands_adjacent_frame_sides(self) -> None:
        frames = (
            Box(0, 0, 100, 60),
            Box(100, 0, 200, 60),
            Box(200, 0, 300, 60),
        )
        envelopes = (CropEnvelope(Box(0, 0, 300, 60)),) * 3
        plan = frame_bleed_plan(
            frames=frames,
            frame_crop_envelopes=envelopes,
            overlap_requirements=(
                FrameOverlapRequirement(
                    boundary=FrameBoundaryReference(None, 1),
                    left_frame_index=0,
                    right_frame_index=1,
                    required_px=30,
                    physically_supported=True,
                    provenance="content_overlap_measurement",
                ),
            ),
            user_bleed=AxisBleedParameters(5, 2),
            layout="horizontal",
        )

        self.assertTrue(plan.feasible)
        self.assertEqual(
            tuple(
                (side.leading_px, side.trailing_px, side.short_axis_px)
                for side in plan.frame_sides
            ),
            ((5, 30, 2), (30, 5, 2), (5, 5, 2)),
        )
        self.assertEqual(
            tuple(item.boundary for item in plan.overlap_protection),
            (FrameBoundaryReference(None, 1),),
        )

    def test_geometry_overlap_hypothesis_cannot_create_output_protection(self) -> None:
        plan = frame_bleed_plan(
            frames=(Box(0, 0, 100, 60), Box(100, 0, 200, 60)),
            frame_crop_envelopes=(
                CropEnvelope(Box(0, 0, 200, 60)),
                CropEnvelope(Box(0, 0, 200, 60)),
            ),
            overlap_requirements=(
                FrameOverlapRequirement(
                    boundary=FrameBoundaryReference(None, 1),
                    left_frame_index=0,
                    right_frame_index=1,
                    required_px=40,
                    physically_supported=False,
                    provenance="geometry_spacing_hypothesis",
                ),
            ),
            user_bleed=AxisBleedParameters(5, 2),
            layout="horizontal",
        )

        self.assertFalse(plan.feasible)
        self.assertEqual(
            plan.unresolved_overlap_boundaries,
            (FrameBoundaryReference(None, 1),),
        )
        self.assertEqual(
            tuple(
                (side.leading_px, side.trailing_px)
                for side in plan.frame_sides
            ),
            ((5, 5), (5, 5)),
        )

    def test_unresolved_boundaries_keep_their_lane_identity(self) -> None:
        frames = (
            Box(0, 0, 100, 60),
            Box(100, 0, 200, 60),
            Box(0, 60, 100, 120),
            Box(100, 60, 200, 120),
        )
        envelopes = (
            CropEnvelope(Box(0, 0, 200, 60)),
            CropEnvelope(Box(0, 0, 200, 60)),
            CropEnvelope(Box(0, 60, 200, 120)),
            CropEnvelope(Box(0, 60, 200, 120)),
        )
        boundaries = (
            FrameBoundaryReference(1, 1),
            FrameBoundaryReference(2, 1),
        )
        plan = frame_bleed_plan(
            frames=frames,
            frame_crop_envelopes=envelopes,
            overlap_requirements=tuple(
                FrameOverlapRequirement(
                    boundary=boundary,
                    left_frame_index=lane_index * 2,
                    right_frame_index=lane_index * 2 + 1,
                    required_px=20,
                    physically_supported=False,
                    provenance="geometry_spacing_hypothesis",
                )
                for lane_index, boundary in enumerate(boundaries)
            ),
            user_bleed=AxisBleedParameters(5, 2),
            layout="horizontal",
        )

        self.assertEqual(plan.unresolved_overlap_boundaries, boundaries)

    def test_frame_bleed_is_clamped_to_each_crop_envelope(self) -> None:
        geometry = OutputGeometry(
            CropEnvelope(Box(0, 0, 300, 60)),
            (
                Box(0, 0, 100, 60),
                Box(100, 0, 200, 60),
                Box(200, 0, 300, 60),
            ),
        )
        plan = frame_bleed_plan(
            frames=geometry.frames,
            frame_crop_envelopes=(geometry.crop_envelope,) * 3,
            overlap_requirements=(
                FrameOverlapRequirement(
                    FrameBoundaryReference(None, 1),
                    0,
                    1,
                    30,
                    True,
                    "observed_overlap",
                ),
            ),
            user_bleed=AxisBleedParameters(5, 2),
            layout="horizontal",
        )

        expanded = apply_frame_bleed(
            geometry,
            plan,
            layout="horizontal",
            image_width=300,
            image_height=60,
        )

        self.assertEqual(expanded.crop_envelope, geometry.crop_envelope)
        self.assertEqual(expanded.frames[0], Box(0, 0, 130, 60))
        self.assertEqual(expanded.frames[1], Box(70, 0, 205, 60))
        self.assertEqual(expanded.frames[2], Box(195, 0, 300, 60))

    def test_overlap_requirement_uses_physical_support_not_observation_alias(self) -> None:
        fields = FrameOverlapRequirement.__dataclass_fields__
        self.assertIn("physically_supported", fields)
        self.assertNotIn("independently_observed", fields)


if __name__ == "__main__":
    unittest.main()
