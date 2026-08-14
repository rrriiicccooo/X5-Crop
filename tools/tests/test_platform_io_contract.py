from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.regression.platform_io import (
    EXPECTED_SAMPLE_IDS,
    raw_raster_for_orientation,
    load_platform_sources,
)
from x5crop.output.publication import FreshOutputDirectory, FreshOutputError


class PlatformIoContractTests(unittest.TestCase):
    def test_platform_cohort_has_six_sha_bound_responsibilities(self) -> None:
        sources = load_platform_sources(verify_files=False)
        self.assertEqual(tuple(item.sample_id for item in sources), EXPECTED_SAMPLE_IDS)
        self.assertEqual({item.role for item in sources}, {"io_only", "user_path"})
        self.assertTrue(all(len(item.source_sha256) == 64 for item in sources))

    def test_orientation_3_and_8_inverse_rasters_restore_domain(self) -> None:
        canonical = np.arange(3 * 4 * 3, dtype=np.uint16).reshape(3, 4, 3)
        self.assertEqual(raw_raster_for_orientation(canonical, 3).shape, canonical.shape)
        self.assertEqual(raw_raster_for_orientation(canonical, 8).shape, (4, 3, 3))

    def test_orientation_integration_is_not_bound_to_one_sample(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "tools/regression/platform_io.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("S027-derived-orientation", source)
        self.assertNotIn("S027 must remain approved", source)

    def test_platform_publication_refuses_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            with FreshOutputDirectory(target) as publication:
                assert publication.staging is not None
                (publication.staging / "result").write_text("ok", encoding="utf-8")
                publication.publish()
            with self.assertRaises(FreshOutputError):
                with FreshOutputDirectory(target):
                    pass


if __name__ == "__main__":
    unittest.main()
