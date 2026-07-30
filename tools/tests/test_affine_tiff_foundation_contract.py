from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

import numpy as np

from x5crop.domain import Box
from x5crop.configuration.model import FrameCountRequest
from x5crop.formats import format_spec
from x5crop.export.crops import write_crops
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.image.transforms import sample_affine_roi
from x5crop.io.model import ImageProfile, TiffExtraTag, TiffMetadata
from x5crop.io.tiff import read_tiff
from x5crop.run_config import RunConfig


def _run_config(source: Path, output: Path, compression: str) -> RunConfig:
    return RunConfig(
        input_path=source,
        output_dir=output,
        format_id="135",
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        count_request=FrameCountRequest.from_user_input(
            format_spec("135"),
            "full",
            None,
        ),
        page=0,
        review_dir=None,
        copy_review_files=False,
        compression=compression,
        debug=False,
        debug_analysis=False,
        diagnostics=False,
        overwrite=False,
        report=False,
        debug_errors=False,
        jobs=2,
    )


class AffineFoundationContractTest(unittest.TestCase):
    def test_identity_is_exact_slice(self) -> None:
        array = np.arange(12 * 15 * 3, dtype=np.uint16).reshape(12, 15, 3)
        box = Box(3, 2, 11, 9)
        sampled = sample_affine_roi(
            array,
            "YXS",
            AffineCoordinateTransform.identity(15, 12),
            box,
            background_value=0,
        )
        self.assertTrue(np.array_equal(sampled, array[2:9, 3:11]))

    def test_roi_equals_slice_of_test_owned_full_rotation(self) -> None:
        array = np.arange(9 * 13, dtype=np.uint16).reshape(9, 13)
        transform = AffineCoordinateTransform.expanded_rotation(13, 9, 7.0)
        full_box = Box(
            0,
            0,
            transform.output_extent.width,
            transform.output_extent.height,
        )
        full = sample_affine_roi(
            array,
            "YX",
            transform,
            full_box,
            background_value=65535,
        )
        roi = Box(2, 1, transform.output_extent.width - 2, 7)
        direct = sample_affine_roi(
            array,
            "YX",
            transform,
            roi,
            background_value=65535,
        )
        self.assertTrue(
            np.array_equal(
                direct,
                full[roi.top : roi.bottom, roi.left : roi.right],
            )
        )

    def test_half_open_mapping_never_clamps(self) -> None:
        identity = AffineCoordinateTransform.identity(20, 10)
        box = Box(2, 3, 8, 9)
        self.assertIs(identity.map_half_open_box_outward(box), box)
        with self.assertRaises(ValueError):
            identity.map_half_open_box_outward(Box(-1, 0, 3, 3))


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
        )
        box = Box(2, 1, 12, 9)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tif"
            cases = (
                ("none", "NONE", "NONE"),
                ("same", "LZW", "LZW"),
            )
            for compression, source_compression, expected_compression in cases:
                with self.subTest(
                    compression=compression,
                    source_compression=source_compression,
                ):
                    output = root / compression
                    output.mkdir()
                    written = write_crops(
                        source,
                        array,
                        replace(
                            source_profile,
                            compression=source_compression,
                        ),
                        (box,),
                        _run_config(source, output, compression),
                        AffineCoordinateTransform.identity(14, 10),
                        output,
                    )
                    self.assertEqual(len(written), 1)
                    actual, profile, warnings = read_tiff(Path(written[0]), 0)
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


if __name__ == "__main__":
    unittest.main()
