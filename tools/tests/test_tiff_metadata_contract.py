from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import tifffile

from x5crop.io.model import TiffMetadata
from x5crop.io.tiff import (
    read_tiff,
    tiff_write_kwargs,
    validate_written_tiff,
    write_validated_tiff,
)
from x5crop.image.transforms import rotate_array_expand


class TiffMetadataContractTest(unittest.TestCase):
    def test_transferable_metadata_survives_crop_round_trip(self) -> None:
        pixels = np.arange(48, dtype=np.uint16).reshape(6, 8)
        xmp = b"<x:xmpmeta>synthetic</x:xmpmeta>"
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.tif"
            output = Path(directory) / "crop.tif"
            tifffile.imwrite(
                source,
                pixels,
                description="original description",
                datetime="2026:07:12 12:34:56",
                metadata=None,
                extratags=(
                    (315, "s", 0, "X5 Crop Tester", False),
                    (700, "B", len(xmp), xmp, False),
                ),
            )

            array, profile, warnings = read_tiff(source, 0)
            self.assertEqual(warnings, [])
            self.assertIsInstance(profile.metadata, TiffMetadata)
            cropped = np.ascontiguousarray(array[1:5, 2:7])
            tifffile.imwrite(
                output,
                cropped,
                **tiff_write_kwargs(profile, "none"),
            )
            validate_written_tiff(output, cropped, profile, "none")

            with tifffile.TiffFile(output) as tif:
                tags = tif.pages[0].tags
                self.assertEqual(tags[270].value, "original description")
                self.assertEqual(tags[306].value, "2026:07:12 12:34:56")
                self.assertEqual(tags[315].value, "X5 Crop Tester")
                self.assertEqual(bytes(tags[700].value), xmp)

    def test_rotation_preserves_tiff_sample_and_profile_contract(self) -> None:
        pixels = np.arange(8 * 12 * 3, dtype=np.uint16).reshape(8, 12, 3)
        icc = b"synthetic-icc-profile"
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source_rgb.tif"
            output = Path(directory) / "rotated_rgb.tif"
            tifffile.imwrite(
                source,
                pixels,
                photometric="rgb",
                compression="deflate",
                resolution=(300.0, 300.0),
                resolutionunit="INCH",
                iccprofile=icc,
                description="rotation metadata contract",
                software="X5 Crop Test",
                metadata=None,
            )

            array, profile, warnings = read_tiff(source, 0)
            self.assertEqual(warnings, [])
            rotated, _ = rotate_array_expand(
                array,
                11.0,
                profile.axes,
                background_value=np.iinfo(array.dtype).max,
            )
            write_validated_tiff(output, rotated, profile, "same")

            written, written_profile, written_warnings = read_tiff(output, 0)
            self.assertEqual(written_warnings, [])
            self.assertTrue(np.array_equal(written, rotated))
            self.assertEqual(written.dtype, pixels.dtype)
            self.assertEqual(written.shape[-1], 3)
            self.assertEqual(written_profile.bits_per_sample, profile.bits_per_sample)
            self.assertEqual(written_profile.planar_config, profile.planar_config)
            self.assertEqual(written_profile.photometric, profile.photometric)
            self.assertEqual(written_profile.compression, profile.compression)
            self.assertEqual(written_profile.resolution, profile.resolution)
            self.assertEqual(written_profile.resolution_unit, profile.resolution_unit)
            self.assertEqual(written_profile.icc_profile, profile.icc_profile)
            self.assertEqual(written_profile.metadata, profile.metadata)


if __name__ == "__main__":
    unittest.main()
