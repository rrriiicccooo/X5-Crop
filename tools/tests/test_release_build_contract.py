from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools.release.build import build_release
from tools.release.manifest import RELEASE_PATHS
from tools.release.standalone import (
    build_standalone_bytes,
    build_standalone_text,
    package_names,
    read_sources,
)
from x5crop.app_info import VERSION


class ReleaseBuildContractTest(unittest.TestCase):
    def test_generated_standalone_bytes_ignore_host_newline_translation(
        self,
    ) -> None:
        def windows_write_text(
            path: Path,
            data: str,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> int:
            del errors, newline
            payload = data.replace("\n", "\r\n").encode(encoding or "utf-8")
            return path.write_bytes(payload)

        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "release.zip"
            with patch.object(Path, "write_text", windows_write_text):
                archive = build_release("v5-contract", archive_path)
            with ZipFile(archive) as package:
                standalone = package.read("X5_Crop.py")

        expected = build_standalone_bytes(
            read_sources(),
            package_names(),
        )
        self.assertEqual(standalone, expected)
        self.assertNotIn(b"\r\n", standalone)

    def test_archive_is_unique_current_and_standalone_starts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = build_release("v5-contract", root / "release.zip")
            with ZipFile(archive) as package:
                names = package.namelist()
                self.assertEqual(names, list(RELEASE_PATHS))
                self.assertEqual(len(names), len(set(names)))
                self.assertFalse(
                    any(
                        name.startswith(("x5crop/", "tools/", "tests/"))
                        for name in names
                    )
                )
                self.assertFalse(
                    any("manual_annotation" in name for name in names)
                )
                standalone = package.read("X5_Crop.py").decode("utf-8")
                self.assertEqual(
                    standalone,
                    build_standalone_text(read_sources(), package_names()),
                )
                package.extract("X5_Crop.py", root)
            completed = subprocess.run(
                (sys.executable, str(root / "X5_Crop.py"), "--version"),
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertEqual(completed.stdout.strip(), f"X5_Crop.py {VERSION}")


if __name__ == "__main__":
    unittest.main()
