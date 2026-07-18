from __future__ import annotations

import unittest
from inspect import getsource, signature
from types import SimpleNamespace
from typing import get_type_hints

from x5crop.domain import (
    Box,
    FrameCropEnvelope,
    InterFrameSpacing,
    InterFrameBoundaryReference,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.output.frame_bleed import apply_frame_bleed, frame_bleed_plan
from x5crop.runtime.frame_bleed import _frame_output_bounds, _overlap_requirements
from x5crop.output.model import (
    AxisBleedParameters,
    FrameOverlapRequirement,
    OutputGeometry,
)


def _overlap_requirement(
    boundary: InterFrameBoundaryReference,
    left_frame_index: int,
    right_frame_index: int,
    required_px: int,
    *,
    supported: bool,
) -> FrameOverlapRequirement:
    basis = (
        InterFrameSpacingBasis.CORROBORATED_OVERLAP
        if supported
        else InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
    )
    provenance = MeasurementProvenance(
        (
            MeasurementIdentity.PHOTO_EDGES
            if supported
            else MeasurementIdentity.FRAME_GEOMETRY
        ),
        ObservationId(
            f"synthetic_overlap:{boundary.lane_index}:{boundary.boundary_index}:"
            f"{basis.value}"
        ),
        (MeasurementIdentity.GRAY_WORK,),
        "synthetic inter-photo overlap",
    )
    return FrameOverlapRequirement(
        InterFrameSpacing(
            boundary,
            PixelInterval.exact(float(-required_px)),
            provenance,
            basis,
        ),
        left_frame_index,
        right_frame_index,
    )


class InterFrameOverlapBleedTest(unittest.TestCase):
    def test_standard_output_bounds_use_canvas_not_holder_interpretation(
        self,
    ) -> None:
        canvas = Box(0, 0, 300, 60)
        frame = FrameCropEnvelope(1, Box(10, 0, 100, 60))
        geometry = SimpleNamespace(
            frame_crop_envelopes=(frame,),
            holder_safety=SimpleNamespace(
                box=Box(0, 10, 300, 50),
                containment_fallback=SimpleNamespace(box=canvas),
            ),
        )
        selection = SimpleNamespace(
            selected=SimpleNamespace(geometry=geometry),
        )

        self.assertEqual(_frame_output_bounds(selection), (canvas,))

    def test_overlap_requirement_preserves_typed_spacing_fact(self) -> None:
        fields = FrameOverlapRequirement.__dataclass_fields__
        hints = get_type_hints(FrameOverlapRequirement)

        self.assertIn("spacing", fields)
        self.assertNotIn("physically_supported", fields)
        self.assertNotIn("provenance", fields)
        self.assertNotIn("required_px", fields)
        self.assertIs(hints["spacing"], InterFrameSpacing)

    def test_inter_photo_spacing_kind_is_typed(self) -> None:
        requirement = _overlap_requirement(
            InterFrameBoundaryReference(None, 1),
            0,
            1,
            12,
            supported=True,
        )

        self.assertIs(requirement.spacing.kind, InterFrameSpacingKind.OVERLAP)

    def test_runtime_overlap_protection_consumes_assessed_boundary_evidence(self) -> None:
        source = getsource(_overlap_requirements)
        self.assertIn("internal_frame_boundary_preservation", source)
        self.assertNotIn("geometry.inter_photo_spacings", source)

    def test_frame_bleed_layout_is_explicit(self) -> None:
        self.assertIs(
            signature(frame_bleed_plan).parameters["layout"].default,
            signature(frame_bleed_plan).empty,
        )
        with self.assertRaises(ValueError):
            frame_bleed_plan(
                frames=(Box(0, 0, 100, 60),),
                frame_output_bounds=(Box(0, 0, 100, 60),),
                overlap_requirements=(),
                user_bleed=AxisBleedParameters(0, 0),
                layout="diagonal",
            )

    def test_overlap_protection_only_expands_adjacent_frame_sides(self) -> None:
        frames = (
            Box(0, 0, 100, 60),
            Box(100, 0, 200, 60),
            Box(200, 0, 300, 60),
        )
        output_bounds = (Box(0, 0, 300, 60),) * 3
        plan = frame_bleed_plan(
            frames=frames,
            frame_output_bounds=output_bounds,
            overlap_requirements=(
                _overlap_requirement(
                    InterFrameBoundaryReference(None, 1),
                    0,
                    1,
                    30,
                    supported=True,
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
            (InterFrameBoundaryReference(None, 1),),
        )

    def test_geometry_overlap_hypothesis_cannot_create_output_protection(self) -> None:
        plan = frame_bleed_plan(
            frames=(Box(0, 0, 100, 60), Box(100, 0, 200, 60)),
            frame_output_bounds=(
                Box(0, 0, 200, 60),
                Box(0, 0, 200, 60),
            ),
            overlap_requirements=(
                _overlap_requirement(
                    InterFrameBoundaryReference(None, 1),
                    0,
                    1,
                    40,
                    supported=False,
                ),
            ),
            user_bleed=AxisBleedParameters(5, 2),
            layout="horizontal",
        )

        self.assertFalse(plan.feasible)
        self.assertEqual(
            plan.unresolved_overlap_boundaries,
            (InterFrameBoundaryReference(None, 1),),
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
        output_bounds = (
            Box(0, 0, 200, 60),
            Box(0, 0, 200, 60),
            Box(0, 60, 200, 120),
            Box(0, 60, 200, 120),
        )
        boundaries = (
            InterFrameBoundaryReference(1, 1),
            InterFrameBoundaryReference(2, 1),
        )
        plan = frame_bleed_plan(
            frames=frames,
            frame_output_bounds=output_bounds,
            overlap_requirements=tuple(
                _overlap_requirement(
                    boundary,
                    lane_index * 2,
                    lane_index * 2 + 1,
                    20,
                    supported=False,
                )
                for lane_index, boundary in enumerate(boundaries)
            ),
            user_bleed=AxisBleedParameters(5, 2),
            layout="horizontal",
        )

        self.assertEqual(plan.unresolved_overlap_boundaries, boundaries)

    def test_frame_bleed_is_clamped_to_each_output_bound(self) -> None:
        geometry = OutputGeometry(
            (
                FrameCropEnvelope(1, Box(0, 0, 100, 60)),
                FrameCropEnvelope(2, Box(100, 0, 200, 60)),
                FrameCropEnvelope(3, Box(200, 0, 300, 60)),
            ),
            (
                Box(0, 0, 100, 60),
                Box(100, 0, 200, 60),
                Box(200, 0, 300, 60),
            ),
        )
        plan = frame_bleed_plan(
            frames=geometry.final_boxes,
            frame_output_bounds=(Box(0, 0, 300, 60),) * 3,
            overlap_requirements=(
                _overlap_requirement(
                    InterFrameBoundaryReference(None, 1),
                    0,
                    1,
                    30,
                    supported=True,
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

        self.assertEqual(expanded.frame_crop_envelopes, geometry.frame_crop_envelopes)
        self.assertEqual(expanded.final_boxes[0], Box(0, 0, 130, 60))
        self.assertEqual(expanded.final_boxes[1], Box(70, 0, 205, 60))
        self.assertEqual(expanded.final_boxes[2], Box(195, 0, 300, 60))

    def test_user_bleed_expands_beyond_the_physical_crop_envelope(self) -> None:
        geometry = OutputGeometry(
            (
                FrameCropEnvelope(1, Box(10, 5, 100, 55)),
                FrameCropEnvelope(2, Box(100, 5, 200, 55)),
                FrameCropEnvelope(3, Box(200, 5, 290, 55)),
            ),
            (
                Box(10, 5, 100, 55),
                Box(100, 5, 200, 55),
                Box(200, 5, 290, 55),
            ),
        )
        holder = Box(0, 0, 300, 60)
        plan = frame_bleed_plan(
            frames=geometry.final_boxes,
            frame_output_bounds=(holder,) * 3,
            overlap_requirements=(),
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

        self.assertEqual(expanded.final_boxes[0], Box(5, 3, 105, 57))
        self.assertEqual(expanded.final_boxes[2], Box(195, 3, 295, 57))
        self.assertEqual(expanded.frame_crop_envelopes, geometry.frame_crop_envelopes)

if __name__ == "__main__":
    unittest.main()
