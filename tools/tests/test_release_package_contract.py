from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.release.build import build_release
from tools.release.manifest import RELEASE_PATHS


EXPECTED_RELEASE_PATHS = (
    "X5_Crop.py",
    "X5_Crop_Mac.command",
    "X5_Crop_win.bat",
    "README.txt",
    "快速启动_Quick_Start.txt",
    "install/X5_Crop_Mac_install.command",
    "install/X5_Crop_win_install.bat",
    "install/X5_Crop_Mac_uninstall.command",
    "install/X5_Crop_win_uninstall.bat",
)


class ReleasePackageContractTest(unittest.TestCase):
    def test_manifest_is_the_exact_user_package(self) -> None:
        self.assertEqual(RELEASE_PATHS, EXPECTED_RELEASE_PATHS)

    def test_builder_emits_only_manifest_entries_with_release_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = build_release(
                "v0.0.0-contract",
                Path(temporary) / "X5-Crop-v0.0.0-contract.zip",
            )
            with ZipFile(archive) as package:
                self.assertEqual(tuple(package.namelist()), EXPECTED_RELEASE_PATHS)
                standalone = package.read("X5_Crop.py").decode("utf-8")
                self.assertIn("_X5_EMBEDDED_SOURCES", standalone)
                self.assertTrue(
                    package.getinfo("快速启动_Quick_Start.txt").flag_bits & 0x800
                )
                for path in (
                    "X5_Crop.py",
                    "X5_Crop_Mac.command",
                    "install/X5_Crop_Mac_install.command",
                    "install/X5_Crop_Mac_uninstall.command",
                ):
                    with self.subTest(path=path):
                        mode = package.getinfo(path).external_attr >> 16
                        self.assertTrue(mode & 0o111)


if __name__ == "__main__":
    unittest.main()
