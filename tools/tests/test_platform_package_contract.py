from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PlatformPackageContractTests(unittest.TestCase):
    def test_intel_command_is_a_thin_guard_over_the_unique_verifier(self) -> None:
        command = (
            ROOT / "tools/platform/X5_Crop_Intel_validate.command"
        ).read_text(encoding="utf-8")
        self.assertIn('"$(uname -m)" != "x86_64"', command)
        self.assertIn("git status --porcelain", command)
        self.assertIn("git rev-parse HEAD", command)
        self.assertIn(
            'exec bash tools/verify platform --expected-commit "$expected_commit"',
            command,
        )
        for duplicate in ("unittest", "platform_io", "performance.py"):
            self.assertNotIn(duplicate, command)

if __name__ == "__main__":
    unittest.main()
