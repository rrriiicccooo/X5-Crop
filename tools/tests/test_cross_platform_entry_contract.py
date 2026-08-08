from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from x5crop.output.transaction import OutputLock, TransactionPaths


ROOT = Path(__file__).resolve().parents[2]


class CrossPlatformEntryContractTests(unittest.TestCase):
    def test_ci_runs_one_verifier_across_twelve_platform_python_jobs(self) -> None:
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(
            encoding="utf-8"
        )
        for runner in (
            "ubuntu-24.04",
            "windows-2025",
            "macos-15",
            "macos-15-intel",
        ):
            self.assertIn(f"- {runner}", workflow)
        for version in ("3.12", "3.13", "3.14"):
            self.assertIn(f'- "{version}"', workflow)
        self.assertIn("shell: bash", workflow)
        self.assertEqual(workflow.count("tools/verify full"), 1)

    def test_windows_batch_file_is_only_a_git_bash_adapter(self) -> None:
        adapter = (ROOT / "tools/platform/X5_Crop_verify.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("where bash", adapter)
        self.assertIn('bash "%~dp0..\\verify" %*', adapter)
        for duplicated_owner in ("unittest", "compileall", "diagnostic_cohort"):
            self.assertNotIn(duplicated_owner, adapter)

    def test_custom_outputs_have_independent_lock_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = TransactionPaths.for_target(Path(directory) / "FirstCrops")
            second = TransactionPaths.for_target(Path(directory) / "SecondCrops")
            self.assertNotEqual(first.lock, second.lock)
            with OutputLock(first.lock), OutputLock(second.lock):
                self.assertTrue(first.lock.is_file())
                self.assertTrue(second.lock.is_file())


if __name__ == "__main__":
    unittest.main()
