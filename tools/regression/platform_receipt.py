"""Generate a clean-tree receipt from the real macOS or Windows host."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Sequence

from x5crop.runtime.identity import runtime_environment_identity

from .performance import (
    DEFAULT_RECEIPT_PATH,
    build_receipt,
    validate_receipt,
)
from .platform_filesystems import run_platform_filesystem_validation
from .platform_io import (
    cohort_sha256 as platform_cohort_sha256,
    load_platform_sources,
    run_platform_io_validation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_RECEIPT_SCHEMA = "x5crop_platform_receipt_v1"
DEFAULT_PLATFORM_ROOT = PROJECT_ROOT / "build" / "v5-platform"
TARGET_APPLE_SILICON = "apple_silicon_macos"
TARGET_INTEL_MAC = "intel_macos"
TARGET_WINDOWS_X64 = "windows_x64"


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def clean_commit() -> str:
    if _git("status", "--porcelain"):
        raise ValueError("platform receipt requires a clean worktree")
    commit = _git("rev-parse", "HEAD")
    if len(commit) != 40:
        raise ValueError("platform receipt requires one full Git commit")
    return commit


def actual_target() -> str:
    system = platform.system()
    machine = platform.machine().casefold()
    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        return TARGET_APPLE_SILICON
    if system == "Darwin" and machine in {"x86_64", "amd64"}:
        return TARGET_INTEL_MAC
    if system == "Windows" and machine in {"amd64", "x86_64"}:
        return TARGET_WINDOWS_X64
    raise ValueError(f"unsupported receipt host: {system} {platform.machine()}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_verifier(mode: str) -> dict[str, str]:
    bash = shutil.which("bash")
    if bash is None:
        raise ValueError("platform verification requires Git Bash or bash")
    completed = subprocess.run(
        (bash, str(PROJECT_ROOT / "tools/verify"), mode),
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"tools/verify {mode} failed:\n{completed.stdout[-8000:]}"
        )
    return {
        "mode": mode,
        "status": "passed",
        "output_sha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
    }


def _read_only_installer_check() -> dict[str, str]:
    completed = subprocess.run(
        (
            sys.executable,
            str(PROJECT_ROOT / "tools/install/dependency_manager.py"),
            "check",
            "--contract",
            str(PROJECT_ROOT / "tools/install/dependencies.toml"),
            "--quiet",
        ),
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            "read-only dependency/installer capability check failed:\n"
            + completed.stdout[-4000:]
        )
    return {
        "read_only_dependency_check": "passed",
        "destructive_missing_update_uninstall_matrix": "external_disposable_host_only",
        "homebrew_reuse_test": "read_only_only",
    }


def _load_or_build_performance(path: Path, commit: str) -> dict[str, Any]:
    if path.is_file():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_receipt(record, expected_commit=commit)
            return record
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    record = build_receipt()
    validate_receipt(record, expected_commit=commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return record


def build_platform_receipt(
    *,
    expected_commit: str | None,
    output: Path | None,
    performance_receipt: Path,
) -> tuple[Path, dict[str, Any]]:
    commit = clean_commit()
    if expected_commit is not None and commit != expected_commit:
        raise ValueError("current HEAD does not match the expected platform commit")
    target = actual_target()
    verifier_full = _run_verifier("full")
    verifier_audit = _run_verifier("audit")
    performance_record = _load_or_build_performance(performance_receipt, commit)
    platform_io = run_platform_io_validation()
    filesystems = run_platform_filesystem_validation()
    environment = runtime_environment_identity()
    sources = load_platform_sources(verify_files=True)
    destination = (
        output.resolve()
        if output is not None
        else DEFAULT_PLATFORM_ROOT / f"{target}.platform_receipt.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    associated_performance = destination.with_name(
        f"{target}.performance_receipt.json"
    )
    associated_performance.write_text(
        json.dumps(performance_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    record = {
        "receipt_schema": PLATFORM_RECEIPT_SCHEMA,
        "target": target,
        "git_commit": commit,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "environment": environment,
        "verification": {
            "full": verifier_full,
            "non_detection_audit": verifier_audit,
        },
        "platform_cohort_sha256": platform_cohort_sha256(),
        "source_sha256s": [source.source_sha256 for source in sources],
        "platform_io": platform_io,
        "filesystems": filesystems,
        "installer_validation": _read_only_installer_check(),
        "performance_receipt": {
            "file_name": associated_performance.name,
            "sha256": _sha256(associated_performance),
            "receipt_schema": performance_record["receipt_schema"],
            "git_commit": performance_record["git_commit"],
        },
    }
    validate_platform_receipt(record, expected_commit=commit)
    destination.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination, record


def validate_platform_receipt(
    record: object,
    *,
    expected_commit: str,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("platform receipt must be an object")
    expected_keys = {
        "receipt_schema",
        "target",
        "git_commit",
        "platform",
        "environment",
        "verification",
        "platform_cohort_sha256",
        "source_sha256s",
        "platform_io",
        "filesystems",
        "installer_validation",
        "performance_receipt",
    }
    sources = load_platform_sources(verify_files=False)
    target = record.get("target")
    platform_record = record.get("platform", {})
    expected_platform = {
        TARGET_APPLE_SILICON: ("Darwin", {"arm64", "aarch64"}),
        TARGET_INTEL_MAC: ("Darwin", {"x86_64", "amd64"}),
        TARGET_WINDOWS_X64: ("Windows", {"amd64", "x86_64"}),
    }
    if target not in expected_platform:
        raise ValueError("platform receipt target is unknown")
    system, machines = expected_platform[target]
    verification = record.get("verification", {})
    performance = record.get("performance_receipt", {})
    if (
        set(record) != expected_keys
        or record.get("receipt_schema") != PLATFORM_RECEIPT_SCHEMA
        or record.get("git_commit") != expected_commit
        or not isinstance(platform_record, dict)
        or platform_record.get("system") != system
        or str(platform_record.get("machine", "")).casefold() not in machines
        or not isinstance(record.get("environment"), dict)
        or record["environment"].get("platform_system") != system
        or record.get("platform_cohort_sha256") != platform_cohort_sha256()
        or record.get("source_sha256s")
        != [source.source_sha256 for source in sources]
        or not isinstance(verification, dict)
        or set(verification) != {"full", "non_detection_audit"}
        or any(item.get("status") != "passed" for item in verification.values())
        or record.get("platform_io", {}).get("accuracy_verdict") != "not_assessed"
        or record.get("platform_io", {}).get("cohort_sha256")
        != platform_cohort_sha256()
        or record.get("filesystems", {}).get("platform_system") != system
        or record.get("installer_validation", {}).get(
            "read_only_dependency_check"
        )
        != "passed"
        or performance.get("git_commit") != expected_commit
        or not str(performance.get("file_name", "")).endswith(
            ".performance_receipt.json"
        )
        or len(str(performance.get("sha256", ""))) != 64
    ):
        raise ValueError("platform receipt identity is invalid")
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--performance-receipt",
        type=Path,
        default=DEFAULT_RECEIPT_PATH,
    )
    args = parser.parse_args(argv)
    destination, record = build_platform_receipt(
        expected_commit=args.expected_commit,
        output=args.output,
        performance_receipt=args.performance_receipt.resolve(),
    )
    print(f"platform receipt: {record['target']} {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
