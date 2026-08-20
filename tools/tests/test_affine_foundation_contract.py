from __future__ import annotations

from tools.tests.affine_tiff_support import *


class AffineFoundationContractTest(unittest.TestCase):
    def test_continuous_footprint_primitives_are_single_path_and_ccw(
        self,
    ) -> None:
        hull = convex_hull(
            (
                (5.0, 4.0),
                (1.0, 1.0),
                (5.0, 1.0),
                (1.0, 4.0),
                (3.0, 1.0),
                (1.0, 1.0),
            )
        )
        self.assertEqual(
            hull,
            ((1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0)),
        )
        clipped = clip_convex_polygon_to_box(hull, Box(1, 1, 6, 5))
        self.assertEqual(
            clipped,
            ((1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0)),
        )

    def test_pixel_center_rounding_does_not_add_left_or_top_pixel(
        self,
    ) -> None:
        polygon = (
            (100.0, 20.0),
            (110.0, 20.0),
            (110.0, 30.0),
            (100.0, 30.0),
        )
        self.assertEqual(
            mapped_half_open_box(polygon, lambda x, y: (x, y)),
            Box(100, 20, 111, 31),
        )

    def test_continuous_polygon_maps_without_source_aabb_widening(self) -> None:
        transform = AffineCoordinateTransform.expanded_rotation(40, 30, 7.0)
        footprint = (
            (8.0, 15.0),
            (20.0, 7.0),
            (32.0, 15.0),
            (20.0, 23.0),
        )
        direct = mapped_half_open_box(footprint, transform.map_point)
        legacy = mapped_half_open_box(
            ((8.0, 7.0), (32.0, 7.0), (32.0, 23.0), (8.0, 23.0)),
            transform.map_point,
        )
        self.assertLess(direct.width * direct.height, legacy.width * legacy.height)

    def test_expanded_rotation_has_frozen_extent_and_center_contract(self) -> None:
        width = 17
        height = 11
        angle_degrees = 7.0
        transform = AffineCoordinateTransform.expanded_rotation(
            width,
            height,
            angle_degrees,
        )
        angle = math.radians(angle_degrees)
        source_center = ((width - 1) / 2.0, (height - 1) / 2.0)
        corners = (
            (0.0, 0.0),
            (float(width - 1), 0.0),
            (0.0, float(height - 1)),
            (float(width - 1), float(height - 1)),
        )
        rotated = tuple(
            (
                (x - source_center[0]) * math.cos(angle)
                - (y - source_center[1]) * math.sin(angle),
                (x - source_center[0]) * math.sin(angle)
                + (y - source_center[1]) * math.cos(angle),
            )
            for x, y in corners
        )
        expected_width = math.ceil(
            max(x for x, _ in rotated)
            - min(x for x, _ in rotated)
            + 2.0 * AFFINE_OUTPUT_RASTER_GUARD_PX
        )
        expected_height = math.ceil(
            max(y for _, y in rotated)
            - min(y for _, y in rotated)
            + 2.0 * AFFINE_OUTPUT_RASTER_GUARD_PX
        )
        self.assertEqual(transform.output_extent.width, expected_width)
        self.assertEqual(transform.output_extent.height, expected_height)
        mapped_center = transform.map_point(*source_center)
        self.assertAlmostEqual(
            mapped_center[0],
            (expected_width - 1) / 2.0,
        )
        self.assertAlmostEqual(
            mapped_center[1],
            (expected_height - 1) / 2.0,
        )

    def test_affine_round_trip_preserves_source_coordinates(self) -> None:
        transform = AffineCoordinateTransform.expanded_rotation(23, 19, -1.7)
        for source_point in (
            (0.0, 0.0),
            (22.0, 0.0),
            (0.0, 18.0),
            (22.0, 18.0),
            (7.25, 11.75),
        ):
            with self.subTest(source_point=source_point):
                recovered = transform.inverse_map_point(
                    *transform.map_point(*source_point)
                )
                self.assertAlmostEqual(recovered[0], source_point[0], places=12)
                self.assertAlmostEqual(recovered[1], source_point[1], places=12)

    def test_identity_is_exact_slice(self) -> None:
        array = np.arange(12 * 15 * 3, dtype=np.uint16).reshape(12, 15, 3)
        box = Box(3, 2, 11, 9)
        sampled = sample_affine_roi(
            array,
            AffineCoordinateTransform.identity(15, 12),
            box,
            sampling_authority_box=Box(0, 0, 15, 12),
        )
        self.assertTrue(np.array_equal(sampled, array[2:9, 3:11]))

    def test_roi_equals_slice_of_test_owned_full_rotation(self) -> None:
        plane = np.arange(9 * 13, dtype=np.uint16).reshape(9, 13)
        array = np.repeat(plane[..., None], 3, axis=2)
        transform = AffineCoordinateTransform.expanded_rotation(13, 9, 7.0)
        full_box = Box(
            0,
            0,
            transform.output_extent.width,
            transform.output_extent.height,
        )
        full = sample_affine_roi(
            array,
            transform,
            full_box,
            sampling_authority_box=Box(0, 0, 13, 9),
        )
        roi = Box(2, 1, transform.output_extent.width - 2, 7)
        direct = sample_affine_roi(
            array,
            transform,
            roi,
            sampling_authority_box=Box(0, 0, 13, 9),
        )
        self.assertTrue(
            np.array_equal(
                direct,
                full[roi.top : roi.bottom, roi.left : roi.right],
            )
        )

    def test_expanded_canvas_preserves_bilinear_support_at_source_corners(
        self,
    ) -> None:
        array = np.full((13, 21, 3), 1200, dtype=np.uint16)
        transform = AffineCoordinateTransform.expanded_rotation(21, 13, 2.0)
        full = sample_affine_roi(
            array,
            transform,
            Box(
                0,
                0,
                transform.output_extent.width,
                transform.output_extent.height,
            ),
            sampling_authority_box=Box(0, 0, 21, 13),
        )
        for source_corner in (
            (0.0, 0.0),
            (20.0, 0.0),
            (0.0, 12.0),
            (20.0, 12.0),
        ):
            with self.subTest(source_corner=source_corner):
                mapped_x, mapped_y = transform.map_point(*source_corner)
                x0 = max(0, math.floor(mapped_x) - 1)
                x1 = min(full.shape[1], math.ceil(mapped_x) + 2)
                y0 = max(0, math.floor(mapped_y) - 1)
                y1 = min(full.shape[0], math.ceil(mapped_y) + 2)
                self.assertTrue(np.any(full[y0:y1, x0:x1] > 0))
        self.assertEqual(int(full[0, 0, 0]), 0)

    def test_bilinear_taps_outside_lane_use_background_without_edge_clip(
        self,
    ) -> None:
        source = np.zeros((4, 8, 3), dtype=np.uint16)
        source[:, :4] = 20
        source[:, 4:] = 240
        transform = AffineCoordinateTransform(
            matrix=(
                (1.0, 0.0, 0.5),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            source_extent=AffineCoordinateTransform.identity(8, 4).source_extent,
            output_extent=AffineCoordinateTransform.identity(8, 4).output_extent,
        )
        sampled = sample_affine_roi(
            source,
            transform,
            Box(3, 1, 5, 3),
            sampling_authority_box=Box(0, 0, 4, 4),
        )
        self.assertEqual(int(sampled[0, 0, 0]), 20)
        self.assertEqual(int(sampled[0, 1, 0]), 10)
        self.assertNotIn(240, sampled)

    def test_identity_requires_zero_in_every_observed_angle_interval(
        self,
    ) -> None:
        assessment = make_transform_assessment(
            (
                make_angle_observation("line:a", -0.2, 0.1),
                make_angle_observation("line:b", -0.1, 0.3),
            ),
        )
        self.assertEqual(assessment.outcome, "identity")
        self.assertEqual(
            assessment.observed_angle_interval_degrees,
            FiniteInterval(-0.2, 0.3),
        )

    def test_disjoint_observed_angles_make_transform_unavailable(self) -> None:
        assessment = make_transform_assessment(
            (
                make_angle_observation("line:a", -0.2, 0.1),
                make_angle_observation("line:b", 0.2, 0.4),
            ),
        )
        self.assertEqual(assessment.outcome, "unavailable")
        self.assertEqual(
        assessment.named_gap,
            "selected_direction_unavailable",
        )

    def test_nonzero_common_observed_angle_drives_rotation(self) -> None:
        assessment = make_transform_assessment(
            (
                make_angle_observation("line:a", 0.8, 1.2),
                make_angle_observation(
                    "line:b",
                    0.9,
                    1.1,
                    role=BoundaryRole.BOTTOM,
                ),
            ),
        )
        self.assertEqual(assessment.outcome, "shared_rotation")
        self.assertEqual(
            assessment.observed_angle_interval_degrees,
            FiniteInterval(0.8, 1.2),
        )
        assert assessment.applied_source_rotation_degrees is not None
        self.assertLess(assessment.applied_source_rotation_degrees, 0.0)
        assert assessment.transform is not None
        angle = math.radians(1.0)
        first = assessment.transform.map_point(0.0, 20.0)
        second = assessment.transform.map_point(
            50.0,
            20.0 + math.tan(angle) * 50.0,
        )
        self.assertAlmostEqual(first[1], second[1], places=10)

    def test_vertical_strip_uses_canonical_sign_to_remove_raster_tilt(self) -> None:
        observation = make_angle_observation("line:vertical", -1.1, -0.9)
        direction = SharedStripDirectionResolution(
            direction=SharedStripDirection(
                direction_id="test:vertical-selected-direction",
                selected_observation_ids=(observation.observation_id,),
                full_angle_interval_degrees=FiniteInterval(-1.1, -0.9),
                observed_angle_interval_degrees=FiniteInterval(-1.1, -0.9),
                canonical_angle_degrees=-1.0,
            ),
            state=EvidenceState.SUPPORTED,
            named_gap=None,
        )
        assessment = output_transform_assessment(
            direction,
            layout="vertical",
            source_width=100,
            source_height=200,
        )

        self.assertEqual(assessment.outcome, "shared_rotation")
        assert assessment.applied_source_rotation_degrees is not None
        self.assertLess(assessment.applied_source_rotation_degrees, 0.0)
        assert assessment.transform is not None
        angle = math.radians(1.0)
        first = assessment.transform.map_point(0.0, 20.0)
        second = assessment.transform.map_point(
            50.0,
            20.0 + math.tan(angle) * 50.0,
        )
        self.assertAlmostEqual(first[1], second[1], places=10)

    def test_nonorthogonal_start_end_does_not_widen_shared_deskew(
        self,
    ) -> None:
        assessment = make_transform_assessment(
            (
                make_angle_observation("line:top", -0.1, 0.2),
                make_angle_observation(
                    "line:end",
                    2.0,
                    3.0,
                    role=BoundaryRole.END,
                ),
            ),
        )
        self.assertEqual(assessment.outcome, "identity")
        self.assertEqual(
            assessment.observed_angle_interval_degrees,
            FiniteInterval(-0.1, 0.2),
        )


if __name__ == "__main__":
    unittest.main()
