from __future__ import annotations

import unittest

import numpy as np

from x5crop.domain import WorkspaceExtent
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.image.transforms import (
    photometric_background_value,
    rotate_array_expand,
)


class ImageTransformSampleDomainTest(unittest.TestCase):
    def test_affine_coordinate_transform_rejects_singular_mapping(self) -> None:
        with self.assertRaises(ValueError):
            AffineCoordinateTransform(
                matrix=(
                    (1.0, 2.0, 0.0),
                    (2.0, 4.0, 0.0),
                    (0.0, 0.0, 1.0),
                ),
                source_extent=WorkspaceExtent(10, 10),
                output_extent=WorkspaceExtent(10, 10),
            )

    def test_float_rotation_preserves_values_outside_unit_range(self) -> None:
        image = np.asarray([[2.0, 4.0], [6.0, 8.0]], dtype=np.float32)
        rotated, transform = rotate_array_expand(
            image,
            15.0,
            "YX",
            background_value=photometric_background_value(
                image,
                "MINISBLACK",
            ),
        )
        self.assertEqual(rotated.dtype, image.dtype)
        self.assertGreater(float(rotated.max()), 1.0)
        self.assertEqual(transform.source_extent.width, 2)
        self.assertGreaterEqual(transform.output_extent.width, 2)

    def test_signed_rotation_preserves_negative_samples(self) -> None:
        image = np.full((20, 20), -100, dtype=np.int16)
        image[9:11, 9:11] = 100
        rotated, _ = rotate_array_expand(
            image,
            15.0,
            "YX",
            background_value=photometric_background_value(
                image,
                "MINISBLACK",
            ),
        )
        self.assertLess(int(rotated.min()), 0)

    def test_miniswhite_rotation_uses_minimum_sample_as_background(self) -> None:
        image = np.asarray([[100, 200], [300, 400]], dtype=np.uint16)
        background = photometric_background_value(image, "MINISWHITE")
        rotated, _ = rotate_array_expand(
            image,
            15.0,
            "YX",
            background_value=background,
        )
        self.assertEqual(background, 0)
        self.assertEqual(int(rotated[0, 0]), 0)

    def test_expanded_rotation_maps_every_source_corner_inside_output(self) -> None:
        for angle in (-27.0, 27.0):
            with self.subTest(angle=angle):
                transform = AffineCoordinateTransform.expanded_rotation(
                    7,
                    5,
                    angle,
                )
                corners = tuple(
                    transform.map_point(x, y)
                    for x, y in (
                        (0.0, 0.0),
                        (6.0, 0.0),
                        (0.0, 4.0),
                        (6.0, 4.0),
                    )
                )
                self.assertTrue(
                    all(
                        0.0 <= x <= transform.output_extent.width - 1
                        and 0.0 <= y <= transform.output_extent.height - 1
                        for x, y in corners
                    )
                )
                self.assertEqual(
                    transform.map_point(3.0, 2.0),
                    (
                        (transform.output_extent.width - 1) / 2.0,
                        (transform.output_extent.height - 1) / 2.0,
                    ),
                )

    def test_rotation_preserves_interleaved_and_planar_channel_structure(self) -> None:
        interleaved = np.arange(5 * 7 * 3, dtype=np.uint16).reshape(5, 7, 3)
        planar = np.moveaxis(interleaved, -1, 0)
        rotated_interleaved, interleaved_transform = rotate_array_expand(
            interleaved,
            17.0,
            "YXS",
            background_value=65535,
        )
        rotated_planar, planar_transform = rotate_array_expand(
            planar,
            17.0,
            "SYX",
            background_value=65535,
        )

        self.assertEqual(rotated_interleaved.dtype, interleaved.dtype)
        self.assertEqual(rotated_planar.dtype, planar.dtype)
        self.assertEqual(rotated_interleaved.shape[-1], 3)
        self.assertEqual(rotated_planar.shape[0], 3)
        self.assertEqual(interleaved_transform, planar_transform)
        self.assertTrue(
            np.array_equal(
                rotated_interleaved,
                np.moveaxis(rotated_planar, 0, -1),
            )
        )


if __name__ == "__main__":
    unittest.main()
