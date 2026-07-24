from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = PROJECT_ROOT / "tools/verify"


class RepositoryVerifierContractTest(unittest.TestCase):
    def test_hooks_and_ci_delegate_to_one_verifier(self) -> None:
        pre_commit = (PROJECT_ROOT / ".githooks/pre-commit").read_text(encoding="utf-8")
        pre_push = (PROJECT_ROOT / ".githooks/pre-push").read_text(encoding="utf-8")
        workflow = (PROJECT_ROOT / ".github/workflows/verify.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(pre_commit, "#!/bin/sh\nexec tools/verify staged\n")
        self.assertIn("git lfs pre-push", pre_push)
        self.assertIn("tools/verify pre-push", pre_push)
        self.assertIn("run: tools/verify full", workflow)
        self.assertFalse((PROJECT_ROOT / "tools/git_checks.sh").exists())

    def test_staged_verifier_rejects_local_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=repository,
                check=True,
            )
            local_file = repository / "Test/local.txt"
            local_file.parent.mkdir()
            local_file.write_text("local fixture", encoding="utf-8")
            subprocess.run(
                ["git", "add", "Test/local.txt"],
                cwd=repository,
                check=True,
            )

            result = subprocess.run(
                [str(VERIFIER), "staged"],
                cwd=repository,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Refusing generated or local file: Test/local.txt", result.stderr)

    def test_output_folder_name_is_current_everywhere_mechanical(self) -> None:
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        uninstallers = "\n".join(
            (PROJECT_ROOT / path).read_text(encoding="utf-8")
            for path in (
                "install/X5_Crop_Mac_uninstall.command",
                "install/X5_Crop_win_uninstall.bat",
            )
        )

        self.assertNotIn("split_output", gitignore)
        self.assertNotIn("split_output", uninstallers)
        self.assertIn("x5_crop_output", gitignore)
        self.assertIn("x5_crop_output", uninstallers)
        self.assertIn("\n/release/\n", gitignore)
        self.assertNotIn("\nrelease/\n", gitignore)

    def test_tools_layout_has_only_current_owners(self) -> None:
        self.assertTrue((PROJECT_ROOT / "tools/verify").is_file())
        self.assertTrue((PROJECT_ROOT / "tools/git/install_hooks.sh").is_file())
        self.assertTrue((PROJECT_ROOT / "tools/release/build.py").is_file())
        self.assertTrue((PROJECT_ROOT / "tools/release/manifest.py").is_file())
        self.assertTrue((PROJECT_ROOT / "tools/release/standalone.py").is_file())
        self.assertEqual(
            {
                path.name
                for path in (PROJECT_ROOT / "tools/regression").glob("*.py")
            },
            {"__init__.py", "compare.py"},
        )
        for removed in (
            "tools/build_release.py",
            "tools/build_standalone.py",
            "tools/release_manifest.py",
            "tools/install_git_hooks.sh",
            "tools/regression/frame_slot_reference.py",
            "tools/regression/sample_expectations.py",
            "tools/regression/sample_identity.py",
            "tools/regression/sample_validation.py",
        ):
            self.assertFalse((PROJECT_ROOT / removed).exists(), removed)

    def test_project_memory_is_the_only_current_handoff(self) -> None:
        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        memory = (PROJECT_ROOT / "PROJECT_MEMORY.md").read_text(encoding="utf-8")

        self.assertIn("PROJECT_MEMORY.md` is the sole cross-session handoff", agents)
        self.assertIn("sole cross-session checkpoint", memory)
        self.assertIn("Current Objective / 当前目标", memory)
        self.assertIn("Manual Review Reset / 人工审阅归零", memory)
        self.assertIn("cross_region_photo_edge_geometry", memory)

        for parallel_handoff in (
            "SESSION_HANDOFF.md",
            "NEXT_ACTIONS.md",
            "DECISIONS.md",
        ):
            self.assertFalse((PROJECT_ROOT / parallel_handoff).exists())

        for retired_state in (
            "7fd6fc1",
            "--deskew off",
            "Test/test 2",
            "pass_required",
            "sample_expectations.jsonl",
            "frame_slot_references.jsonl",
            "user_confirmed_supported",
            "manual_deskew_baseline.jsonl",
        ):
            self.assertNotIn(retired_state, memory)


if __name__ == "__main__":
    unittest.main()
