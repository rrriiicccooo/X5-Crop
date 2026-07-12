from __future__ import annotations

import unittest

from x5crop.domain import AxisBleedParameters, Box, CropEnvelope
from x5crop.output.frame_bleed import apply_frame_bleed, frame_bleed_plan
from x5crop.output.model import (
    FrameOverlapRequirement,
    OutputGeometry,
)


class InterFrameOverlapBleedTest(unittest.TestCase):
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
                    boundary_index=1,
                    left_frame_index=0,
                    right_frame_index=1,
                    required_px=30,
                    independently_observed=True,
                    provenance="content_overlap_measurement",
                ),
            ),
            user_bleed=AxisBleedParameters(5, 2),
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
            tuple(item.boundary_index for item in plan.overlap_protection),
            (1,),
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
                    boundary_index=1,
                    left_frame_index=0,
                    right_frame_index=1,
                    required_px=40,
                    independently_observed=False,
                    provenance="geometry_spacing_hypothesis",
                ),
            ),
            user_bleed=AxisBleedParameters(5, 2),
        )

        self.assertFalse(plan.feasible)
        self.assertEqual(plan.unresolved_overlap_boundaries, (1,))
        self.assertEqual(
            tuple(
                (side.leading_px, side.trailing_px)
                for side in plan.frame_sides
            ),
            ((5, 5), (5, 5)),
        )

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
                FrameOverlapRequirement(1, 0, 1, 30, True, "observed_overlap"),
            ),
            user_bleed=AxisBleedParameters(5, 2),
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


if __name__ == "__main__":
    unittest.main()
