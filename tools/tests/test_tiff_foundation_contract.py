from __future__ import annotations

from tools.tests.affine_tiff_support import *


class TiffFoundationContractTest(unittest.TestCase):
    def test_identity_export_preserves_pixels_and_profile(self) -> None:
        array = np.arange(10 * 14 * 3, dtype=np.uint16).reshape(10, 14, 3)
        source_profile = ImageProfile(
            shape=array.shape,
            dtype=str(array.dtype),
            axes="YXS",
            photometric="RGB",
            compression="NONE",
            sample_format=None,
            bits_per_sample=(16, 16, 16),
            samples_per_pixel=3,
            planar_config="CONTIG",
            resolution=(300.0, 240.0),
            resolution_unit=2,
            icc_profile=b"x5crop-test-icc",
            metadata=TiffMetadata(
                description="source-core metadata",
                datetime="2026:07:29 12:00:00",
                software="X5 Crop contract",
                extra_tags=(
                    TiffExtraTag(
                        code=269,
                        dtype="s",
                        count=0,
                        value="source-document",
                    ),
                ),
            ),
            orientation=orientation_mapping(
                1,
                array.shape[1],
                array.shape[0],
            ),
        )
        box = Box(2, 1, 12, 9)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (("LZW", "LZW"), ("NONE", "NONE"))
            for source_compression, expected_compression in cases:
                with self.subTest(
                    source_compression=source_compression,
                ):
                    output = root / source_compression
                    output.mkdir()
                    written = write_crops(
                        "source",
                        1,
                        array,
                        replace(
                            source_profile,
                            compression=source_compression,
                        ),
                        (box,),
                        (Box(0, 0, 14, 10),),
                        (AffineCoordinateTransform.identity(14, 10),),
                        output,
                    )
                    self.assertEqual(len(written), 1)
                    actual, profile, warnings = read_tiff(Path(written[0]))
                    self.assertEqual(warnings, [])
                    self.assertTrue(np.array_equal(actual, array[1:9, 2:12]))
                    self.assertEqual(profile.dtype, "uint16")
                    self.assertEqual(profile.axes, "YXS")
                    self.assertEqual(profile.photometric, "RGB")
                    self.assertEqual(
                        profile.compression.upper(),
                        expected_compression,
                    )
                    self.assertEqual(profile.resolution, (300.0, 240.0))
                    self.assertEqual(profile.icc_profile, b"x5crop-test-icc")
                    self.assertEqual(
                        profile.metadata.description,
                        "source-core metadata",
                    )
                    self.assertEqual(
                        profile.metadata.software,
                        "X5 Crop contract",
                    )
                    self.assertEqual(
                        profile.metadata.datetime,
                        "2026:07:29 12:00:00",
                    )
                    self.assertEqual(
                        profile.metadata.extra_tags,
                        source_profile.metadata.extra_tags,
                    )

    def test_rotated_polygon_envelope_preserves_tiff_profile_and_black_corners(
        self,
    ) -> None:
        array = (
            np.arange(30 * 40 * 3, dtype=np.uint16).reshape(30, 40, 3)
            + 1000
        )
        profile = ImageProfile(
            shape=array.shape,
            dtype="uint16",
            axes="YXS",
            photometric="RGB",
            compression="NONE",
            sample_format=None,
            bits_per_sample=(16, 16, 16),
            samples_per_pixel=3,
            planar_config="CONTIG",
            resolution=(400.0, 400.0),
            resolution_unit=2,
            icc_profile=b"x5crop-rotated-icc",
            metadata=TiffMetadata(
                description="rotated polygon output",
                datetime="2026:08:21 12:00:00",
                software="X5 Crop contract",
                extra_tags=(),
            ),
            orientation=orientation_mapping(1, 40, 30),
        )
        transform = AffineCoordinateTransform.expanded_rotation(40, 30, -2.0)
        polygon = ((4.0, 3.0), (35.0, 3.0), (35.0, 26.0), (4.0, 26.0))
        box = mapped_half_open_box(polygon, transform.map_point)

        with tempfile.TemporaryDirectory() as temporary:
            written = write_crops(
                "rotated",
                1,
                array,
                profile,
                (box,),
                (Box(4, 3, 36, 27),),
                (transform,),
                Path(temporary),
            )
            actual, actual_profile, warnings = read_tiff(Path(written[0]))

        self.assertEqual(warnings, [])
        self.assertEqual(actual.shape, (box.height, box.width, 3))
        self.assertEqual(actual.dtype, np.dtype("uint16"))
        self.assertTrue(np.any(actual == 0))
        self.assertTrue(np.any(actual > 0))
        self.assertEqual(actual_profile.photometric, "RGB")
        self.assertEqual(actual_profile.resolution, (400.0, 400.0))
        self.assertEqual(actual_profile.icc_profile, b"x5crop-rotated-icc")
        self.assertEqual(
            actual_profile.metadata.description,
            "rotated polygon output",
        )
        self.assertEqual(actual_profile.orientation.original_tag, 1)


if __name__ == "__main__":
    unittest.main()
