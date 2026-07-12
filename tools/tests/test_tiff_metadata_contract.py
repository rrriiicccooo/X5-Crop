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
)


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


if __name__ == "__main__":
    unittest.main()
