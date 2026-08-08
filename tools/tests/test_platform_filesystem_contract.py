from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from tools.regression.platform_filesystems import (
    run_platform_filesystem_validation,
    unverified_filesystem_cases,
)
from x5crop.output.filesystem import OutputSupportLevel
from x5crop.output.ownership import write_owned_output_manifest
from x5crop.output.safe_tree import UnsafeOutputTreeError, inventory_tree


class PlatformFilesystemContractTests(unittest.TestCase):
    def test_exfat_and_network_cases_remain_independently_unverified(self) -> None:
        cases = unverified_filesystem_cases()
        self.assertEqual([item["case"] for item in cases], ["exfat", "network_or_cloud"])
        self.assertTrue(all(item["status"] == "unverified" for item in cases))
        self.assertTrue(
            all(
                item["support_level"]
                == OutputSupportLevel.BEST_EFFORT_UNVERIFIED.value
                for item in cases
            )
        )

    @unittest.skipUnless(os.name == "nt", "requires a real Windows filesystem")
    def test_real_windows_junction_is_rejected_without_following_it(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            outside = Path(directory) / "outside"
            root.mkdir()
            outside.mkdir()
            keep = outside / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            junction = root / "junction"
            subprocess.run(
                ("cmd", "/c", "mklink", "/J", str(junction), str(outside)),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                with self.assertRaises(UnsafeOutputTreeError):
                    inventory_tree(root, manifest_name="manifest", role_for_file=str)
                self.assertEqual(keep.read_text(encoding="utf-8"), "keep")
            finally:
                os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "requires real NTFS lock and rename semantics")
    def test_real_windows_lock_rename_retry_and_recovery(self) -> None:
        result = run_platform_filesystem_validation()
        cases = {item["case"]: item for item in result["cases"]}
        self.assertEqual(cases["ntfs"]["status"], "passed")
        self.assertEqual(cases["exfat"]["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
