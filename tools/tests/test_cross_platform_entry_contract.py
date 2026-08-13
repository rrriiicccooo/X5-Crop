from __future__ import annotations

from pathlib import Path
import unittest


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
        self.assertIn("fetch-depth: 0", workflow)
        self.assertEqual(workflow.count("tools/verify full"), 1)

    def test_tracked_text_has_one_cross_platform_byte_identity(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertEqual(attributes, "* text=auto eol=lf\n")

    def test_windows_batch_file_is_only_a_git_bash_adapter(self) -> None:
        adapter = (ROOT / "tools/platform/X5_Crop_verify.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("where bash", adapter)
        self.assertIn('bash "%~dp0..\\verify" %*', adapter)
        for duplicated_owner in ("unittest", "compileall", "diagnostic_cohort"):
            self.assertNotIn(duplicated_owner, adapter)

    def test_production_output_has_no_lock_or_journal_runtime(self) -> None:
        self.assertFalse((ROOT / "x5crop/output/transaction.py").exists())
        self.assertFalse((ROOT / "x5crop/output/ownership.py").exists())


if __name__ == "__main__":
    unittest.main()
