from __future__ import annotations

import os
import unittest

from tools.regression.filesystem_identity import OutputSupportLevel
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


if __name__ == "__main__":
    unittest.main()
