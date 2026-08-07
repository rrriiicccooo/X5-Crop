"""Classify a push by the strongest verification its changed paths require."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_SCOPE = "documentation"
FULL_SCOPE = "full"
RUNTIME_SCOPE = "runtime"

_RUNTIME_EXACT_PATHS = frozenset(
    {
        "X5_Crop.py",
        "pyproject.toml",
        "requirements.txt",
        "requirements.lock",
        "tools/install/requirements.txt",
        "uv.lock",
        "poetry.lock",
        "tools/regression/performance.py",
        "tools/regression/performance_identity.py",
        "tools/regression/cohorts/production_performance.jsonl",
    }
)


def _normalized_paths(paths: Iterable[str]) -> tuple[str, ...] | None:
    normalized = tuple(dict.fromkeys(path.strip() for path in paths))
    if not normalized:
        return None
    for path in normalized:
        parts = PurePosixPath(path).parts
        if not path or path.startswith("/") or ".." in parts:
            return None
    return normalized


def _is_runtime_path(path: str) -> bool:
    return (
        path in _RUNTIME_EXACT_PATHS
        or path.startswith("x5crop/")
        or (
            path.startswith("requirements")
            and path.endswith((".in", ".txt", ".lock"))
        )
    )


def verification_scope_for_paths(paths: Iterable[str]) -> str:
    """Return documentation, full, or runtime; invalid input fails safe."""

    normalized = _normalized_paths(paths)
    if normalized is None:
        return RUNTIME_SCOPE
    if all(PurePosixPath(path).suffix.lower() == ".md" for path in normalized):
        return DOCUMENTATION_SCOPE
    if any(_is_runtime_path(path) for path in normalized):
        return RUNTIME_SCOPE
    return FULL_SCOPE


def _is_commit(project_root: Path, revision: str) -> bool:
    return subprocess.run(
        ("git", "cat-file", "-e", f"{revision}^{{commit}}"),
        cwd=project_root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _changed_paths(
    project_root: Path,
    remote_revision: str,
    local_revision: str,
) -> tuple[str, ...]:
    completed = subprocess.run(
        (
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
            "-z",
            remote_revision,
            local_revision,
            "--",
        ),
        cwd=project_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return tuple(
        os.fsdecode(path)
        for path in completed.stdout.split(b"\0")
        if path
    )


def verification_scope_for_push(
    refs_path: Path,
    *,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Classify pre-push refs; unknown or new histories require runtime checks."""

    try:
        lines = refs_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return RUNTIME_SCOPE
    if not lines:
        return RUNTIME_SCOPE
    paths: list[str] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            return RUNTIME_SCOPE
        _local_ref, local_revision, _remote_ref, remote_revision = fields
        if not (
            _is_commit(project_root, local_revision)
            and _is_commit(project_root, remote_revision)
        ):
            return RUNTIME_SCOPE
        paths.extend(
            _changed_paths(project_root, remote_revision, local_revision)
        )
    return verification_scope_for_paths(paths)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", type=Path, required=True)
    args = parser.parse_args(argv)
    print(verification_scope_for_push(args.refs.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
