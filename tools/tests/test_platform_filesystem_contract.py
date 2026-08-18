from __future__ import annotations

import os
import unittest
from unittest import mock

from tools.regression.filesystem_identity import (
    FilesystemIdentity,
    OutputSupportLevel,
)
from tools.regression.platform_filesystems import run_platform_filesystem_validation


class PlatformFilesystemContractTests(unittest.TestCase):
    def test_filesystem_identity_is_tools_only(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        self.assertFalse((root / "x5crop/output/filesystem.py").exists())
        self.assertTrue((root / "tools/regression/filesystem_identity.py").is_file())

    @unittest.skipUnless(os.name == "nt", "requires real NTFS publication")
    def test_real_windows_fresh_publication(self) -> None:
        cases = {
            item["case"]: item
            for item in run_platform_filesystem_validation()["cases"]
        }
        self.assertEqual(cases["ntfs"]["status"], "passed")
        self.assertEqual(
            cases["ntfs"]["support_level"],
            OutputSupportLevel.VERIFIED_LOCAL.value,
        )

    def test_receipt_keeps_exfat_explicitly_unverified(self) -> None:
        identity = FilesystemIdentity(
            "darwin",
            "apfs",
            OutputSupportLevel.VERIFIED_LOCAL,
            "verified local filesystem",
        )
        hfs = {
            "case": "hfs_plus",
            "status": "passed",
            "filesystem_kind": "hfs",
            "support_level": "verified_local",
            "reason": "verified local filesystem",
        }
        with (
            mock.patch(
                "tools.regression.platform_filesystems.platform.system",
                return_value="Darwin",
            ),
            mock.patch(
                "tools.regression.platform_filesystems.identify_filesystem",
                return_value=identity,
            ),
            mock.patch(
                "tools.regression.platform_filesystems._exercise_publication"
            ),
            mock.patch(
                "tools.regression.platform_filesystems._darwin_hfs_case",
                return_value=hfs,
            ),
        ):
            cases = {
                item["case"]: item
                for item in run_platform_filesystem_validation()["cases"]
            }
        self.assertEqual(set(cases), {"apfs", "hfs_plus", "exfat"})
        self.assertEqual(cases["exfat"]["status"], "unverified")
        self.assertEqual(
            cases["exfat"]["support_level"],
            OutputSupportLevel.BEST_EFFORT_UNVERIFIED.value,
        )


if __name__ == "__main__":
    unittest.main()
