from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from x5crop.export.review import copy_for_review


class ReviewCopyIdentityContractTest(unittest.TestCase):
    def test_existing_identical_review_copy_is_reused(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source" / "input.tif"
            target = root / "review" / "input.tif"
            source.parent.mkdir()
            target.parent.mkdir()
            source.write_bytes(b"same")
            target.write_bytes(b"same")

            self.assertEqual(
                copy_for_review(source, target.parent, overwrite=False),
                target,
            )

    def test_existing_different_review_copy_requires_overwrite(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source" / "input.tif"
            target = root / "review" / "input.tif"
            source.parent.mkdir()
            target.parent.mkdir()
            source.write_bytes(b"current")
            target.write_bytes(b"stale")

            with self.assertRaises(FileExistsError):
                copy_for_review(source, target.parent, overwrite=False)

            self.assertEqual(
                copy_for_review(source, target.parent, overwrite=True),
                target,
            )
            self.assertEqual(target.read_bytes(), b"current")


if __name__ == "__main__":
    unittest.main()
