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
        self.assertTrue(sampled.flags.c_contiguous)

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

    def test_chunk_reuse_preserves_frozen_uint16_sampling(self) -> None:
        from scipy.ndimage import map_coordinates

        rng = np.random.default_rng(20260820)
        source = rng.integers(
            0,
            np.iinfo(np.uint16).max + 1,
            size=(281, 337, 3),
            dtype=np.uint16,
        )
        transform = AffineCoordinateTransform.expanded_rotation(
            source.shape[1],
            source.shape[0],
            1.7,
        )
        box = Box(11, 9, 330, 279)
        authority_box = Box(7, 5, 331, 277)
        expected = np.full(
            (box.height, box.width, 3),
            0,
            dtype=np.uint16,
        )
        inverse = transform.inverse_matrix
        authority = source[
            authority_box.top : authority_box.bottom,
            authority_box.left : authority_box.right,
        ]
        expanded_x = np.arange(box.left, box.right, dtype=np.float64)[
            None, :
        ]
        for output_row in range(0, box.height, 256):
            row_end = min(box.height, output_row + 256)
            expanded_y = np.arange(
                box.top + output_row,
                box.top + row_end,
                dtype=np.float64,
            )[:, None]
            source_x = (
                inverse[0][0] * expanded_x
                + inverse[0][1] * expanded_y
                + inverse[0][2]
            )
            source_y = (
                inverse[1][0] * expanded_x
                + inverse[1][1] * expanded_y
                + inverse[1][2]
            )
            coordinates = np.asarray(
                (
                    source_y - authority_box.top,
                    source_x - authority_box.left,
                ),
                dtype=np.float64,
            )
            values = np.empty(source_x.shape, dtype=np.float64)
            for channel in range(3):
                map_coordinates(
                    authority[..., channel],
                    coordinates,
                    order=1,
                    mode="grid-constant",
                    cval=0.0,
                    prefilter=False,
                    output=values,
                )
                np.clip(
                    values,
                    0,
                    np.iinfo(np.uint16).max,
                    out=values,
                )
                expected[output_row:row_end, :, channel] = values.astype(
                    np.uint16
                )

        actual = sample_affine_roi(
            source,
            transform,
            box,
            sampling_authority_box=authority_box,
        )
        self.assertTrue(np.array_equal(actual, expected))

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

    def test_nonzero_cosmetic_observation_drives_rotation(self) -> None:
        assessment = assess_output_deskew(
            make_deskew_observation(0.2),
            layout="horizontal",
            source_width=1000,
            source_height=400,
        )
        self.assertTrue(assessment.deskew_applied)
        self.assertLess(assessment.applied_source_rotation_degrees, 0.0)
        angle = math.radians(0.2)
        first = assessment.transform.map_point(0.0, 20.0)
        second = assessment.transform.map_point(
            50.0,
            20.0 + math.tan(angle) * 50.0,
        )
        self.assertAlmostEqual(first[1], second[1], places=10)

    def test_vertical_strip_uses_canonical_sign_to_remove_raster_tilt(self) -> None:
        assessment = assess_output_deskew(
            make_deskew_observation(-0.2, fit_angle_degrees=0.2),
            layout="vertical",
            source_width=100,
            source_height=1000,
        )

        self.assertTrue(assessment.deskew_applied)
        self.assertLess(assessment.applied_source_rotation_degrees, 0.0)
        angle = math.radians(0.2)
        first = assessment.transform.map_point(0.0, 20.0)
        second = assessment.transform.map_point(
            50.0,
            20.0 + math.tan(angle) * 50.0,
        )
        self.assertAlmostEqual(first[1], second[1], places=10)

if __name__ == "__main__":
    unittest.main()
