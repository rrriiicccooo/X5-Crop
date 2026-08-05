from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.verification_scope import (
    DOCUMENTATION_SCOPE,
    FULL_SCOPE,
    RUNTIME_SCOPE,
    verification_scope_for_paths,
    verification_scope_for_push,
)


ROOT = Path(__file__).resolve().parents[2]


class VerificationScopeContractTest(unittest.TestCase):
    def test_markdown_only_changes_use_documentation_scope(self) -> None:
        self.assertEqual(
            verification_scope_for_paths(
                ("README.md", "AGENTS.md", "docs/PROJECT_MEMORY.md")
            ),
            DOCUMENTATION_SCOPE,
        )

    def test_runtime_and_performance_inputs_require_runtime_scope(self) -> None:
        for path in (
            "X5_Crop.py",
            "x5crop/detection/pipeline.py",
            "tools/regression/benchmark_adapter.py",
            "tools/regression/benchmark_workload.py",
            "tools/regression/performance.py",
            "tools/regression/profile_fixed_sample.py",
            "tools/regression/cohorts/production_performance.jsonl",
            "pyproject.toml",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    verification_scope_for_paths(("README.md", path)),
                    RUNTIME_SCOPE,
                )

    def test_non_runtime_code_and_configuration_use_full_scope(self) -> None:
        for path in (
            "tools/verify",
            "tools/tests/test_current_only_contract.py",
            ".githooks/pre-push",
            ".github/workflows/verify.yml",
            "LICENSE",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    verification_scope_for_paths(("README.md", path)),
                    FULL_SCOPE,
                )

    def test_empty_or_invalid_path_sets_fail_safe_to_runtime(self) -> None:
        self.assertEqual(verification_scope_for_paths(()), RUNTIME_SCOPE)
        self.assertEqual(
            verification_scope_for_paths(("",)),
            RUNTIME_SCOPE,
        )

    def test_pre_push_refs_classify_the_actual_commit_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*arguments: str) -> str:
                return subprocess.run(
                    ("git", *arguments),
                    cwd=root,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                ).stdout.strip()

            git("init", "-q")
            git("config", "user.name", "X5 Crop Test")
            git("config", "user.email", "test@example.invalid")
            (root / "README.md").write_text("base\n", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "verify").write_text("base\n", encoding="utf-8")
            (root / "x5crop").mkdir()
            (root / "x5crop" / "runtime.py").write_text(
                "base\n", encoding="utf-8"
            )
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")

            (root / "README.md").write_text("docs\n", encoding="utf-8")
            git("commit", "-qam", "docs")
            docs = git("rev-parse", "HEAD")

            refs = root / "refs"
            refs.write_text(
                f"refs/heads/main {docs} refs/heads/main {base}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                verification_scope_for_push(refs, project_root=root),
                DOCUMENTATION_SCOPE,
            )

            (root / "tools" / "verify").write_text("full\n", encoding="utf-8")
            git("commit", "-qam", "full")
            full = git("rev-parse", "HEAD")
            refs.write_text(
                f"refs/heads/main {full} refs/heads/main {docs}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                verification_scope_for_push(refs, project_root=root),
                FULL_SCOPE,
            )

            (root / "x5crop" / "runtime.py").write_text(
                "runtime\n", encoding="utf-8"
            )
            git("commit", "-qam", "runtime")
            runtime = git("rev-parse", "HEAD")
            refs.write_text(
                f"refs/heads/main {runtime} refs/heads/main {full}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                verification_scope_for_push(refs, project_root=root),
                RUNTIME_SCOPE,
            )

    def test_hooks_and_ci_delegate_documentation_scope_once(self) -> None:
        hook = (ROOT / ".githooks/pre-push").read_text(encoding="utf-8")
        verifier = (ROOT / "tools/verify").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('tools/verify pre-push "$refs"', hook)
        self.assertIn(
            "python3 -m tools.verification_scope --refs", verifier
        )
        self.assertEqual(workflow.count('      - "**/*.md"'), 2)


if __name__ == "__main__":
    unittest.main()
