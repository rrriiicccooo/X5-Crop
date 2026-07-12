from __future__ import annotations

import unittest

import numpy as np

from x5crop.image.transforms import (
    photometric_background_value,
    rotate_array_expand,
)


class ImageTransformSampleDomainTest(unittest.TestCase):
    def test_float_rotation_preserves_values_outside_unit_range(self) -> None:
        image = np.asarray([[2.0, 4.0], [6.0, 8.0]], dtype=np.float32)
        rotated = rotate_array_expand(
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

    def test_signed_rotation_preserves_negative_samples(self) -> None:
        image = np.full((20, 20), -100, dtype=np.int16)
        image[9:11, 9:11] = 100
        rotated = rotate_array_expand(
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
        rotated = rotate_array_expand(
            image,
            15.0,
            "YX",
            background_value=background,
        )
        self.assertEqual(background, 0)
        self.assertEqual(int(rotated[0, 0]), 0)


if __name__ == "__main__":
    unittest.main()
