"""Run real host filesystem, lock, rename, and recovery checks for receipts."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Any, Sequence

from x5crop.output.filesystem import OutputSupportLevel, identify_filesystem
from x5crop.output.ownership import read_owned_output, write_owned_output_manifest
from x5crop.output.safe_tree import UnsafeOutputTreeError, inventory_tree
from x5crop.output.transaction import (
    OutputLock,
    OutputTransaction,
    RecoveryRequiredError,
    TransactionPaths,
)


FILESYSTEM_RESULT_SCHEMA = "x5crop_platform_filesystem_result_v1"


def _owned(root: Path, run_id: str) -> None:
    root.mkdir(exist_ok=True)
    (root / "x5_crop_report.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "x5_crop_summary.csv").write_text("status\n", encoding="utf-8")
    (root / "source_01.tif").write_bytes(b"synthetic-tiff")
    write_owned_output_manifest(
        root,
        run_id=run_id,
        run_record={"filesystem": {"support_level": "verified_local"}},
        terminal_records=(
            {
                "input_ordinal": 1,
                "source_name": "source.tif",
                "terminal_status": "approved_auto",
            },
        ),
    )


def _exercise_publication(parent: Path) -> None:
    target = parent / "x5_crop_output"
    _owned(target, "old-run")
    with OutputTransaction(target) as transaction:
        transaction_id, staging = transaction.create_staging("new-run")
        _owned(staging, "new-run")
        transaction.publish(transaction_id, staging, "new-run")
    if read_owned_output(target).run_id != "new-run":
        raise ValueError("filesystem publication did not expose the complete new output")


def _exercise_lock_isolation(parent: Path) -> None:
    first = TransactionPaths.for_target(parent / "FirstCrops")
    second = TransactionPaths.for_target(parent / "SecondCrops")
    with OutputLock(first.lock), OutputLock(second.lock):
        if first.lock == second.lock:
            raise ValueError("custom outputs share one lock")


def _case_record(case: str, identity, status: str = "passed") -> dict[str, str]:
    return {
        "case": case,
        "status": status,
        "filesystem_kind": identity.filesystem_kind,
        "support_level": identity.support_level.value,
        "reason": identity.reason,
    }


def unverified_filesystem_cases() -> tuple[dict[str, str], ...]:
    return (
        {
            "case": "exfat",
            "status": "unverified",
            "filesystem_kind": "exfat",
            "support_level": OutputSupportLevel.BEST_EFFORT_UNVERIFIED.value,
            "reason": "no dedicated exFAT platform receipt",
        },
        {
            "case": "network_or_cloud",
            "status": "unverified",
            "filesystem_kind": "smb_nas_cloud",
            "support_level": OutputSupportLevel.BEST_EFFORT_UNVERIFIED.value,
            "reason": "network and synchronization semantics are not verified",
        },
    )


def _darwin_hfs_case() -> dict[str, str]:
    with TemporaryDirectory(prefix="x5crop-hfs-contract-") as temporary:
        image = Path(temporary) / "x5crop-hfs.dmg"
        subprocess.run(
            (
                "hdiutil",
                "create",
                "-size",
                "128m",
                "-fs",
                "HFS+",
                "-volname",
                "X5CropHFSContract",
                str(image),
            ),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        attached = subprocess.run(
            ("hdiutil", "attach", "-nobrowse", "-plist", str(image)),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        plist = plistlib.loads(attached.stdout)
        mounts = tuple(
            Path(str(entity["mount-point"]))
            for entity in plist.get("system-entities", ())
            if "mount-point" in entity
        )
        if len(mounts) != 1:
            raise ValueError("HFS+ validation image did not expose one mount")
        mount = mounts[0]
        try:
            identity = identify_filesystem(mount)
            if (
                identity.filesystem_kind not in {"hfs", "hfs+"}
                or identity.support_level != OutputSupportLevel.VERIFIED_LOCAL
            ):
                raise ValueError("HFS+ identity is not a verified local case")
            _exercise_lock_isolation(mount)
            _exercise_publication(mount)
            return _case_record("hfs_plus", identity)
        finally:
            subprocess.run(
                ("hdiutil", "detach", str(mount)),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )


def _windows_link_cases(parent: Path) -> None:
    root = parent / "safe-tree"
    outside = parent / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    symlink = root / "symlink"
    os.symlink(outside, symlink, target_is_directory=True)
    try:
        try:
            inventory_tree(root, manifest_name="manifest", role_for_file=str)
        except UnsafeOutputTreeError:
            pass
        else:
            raise ValueError("Windows symlink was not rejected")
    finally:
        symlink.unlink()
    junction = root / "junction"
    subprocess.run(
        ("cmd", "/c", "mklink", "/J", str(junction), str(outside)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        try:
            inventory_tree(root, manifest_name="manifest", role_for_file=str)
        except UnsafeOutputTreeError:
            pass
        else:
            raise ValueError("Windows junction/reparse point was not rejected")
    finally:
        os.rmdir(junction)


def _hold_windows_file(path: Path, ready: Path, stop: Path) -> int:
    from ctypes import wintypes

    generic_read = 0x80000000
    share_read_write = 0x00000001 | 0x00000002
    open_existing = 3
    handle = ctypes.windll.kernel32.CreateFileW(
        wintypes.LPCWSTR(str(path)),
        generic_read,
        share_read_write,
        None,
        open_existing,
        0,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        raise ctypes.WinError()
    try:
        ready.write_text("ready", encoding="utf-8")
        while not stop.exists():
            time.sleep(0.05)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    return 0


def _windows_occupied_case(parent: Path) -> None:
    target = parent / "occupied-output"
    _owned(target, "old-run")
    ready = parent / "lock-ready"
    stop = parent / "lock-stop"
    child = subprocess.Popen(
        (
            sys.executable,
            "-m",
            "tools.regression.platform_filesystems",
            "--hold-windows-file",
            str(target / "source_01.tif"),
            str(ready),
            str(stop),
        )
    )
    deadline = time.monotonic() + 10.0
    while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if not ready.exists():
        child.terminate()
        raise ValueError("Windows lock worker did not become ready")
    paths = TransactionPaths.for_target(target)
    try:
        with OutputTransaction(target) as transaction:
            transaction_id, staging = transaction.create_staging("new-run")
            _owned(staging, "new-run")
            try:
                transaction.publish(transaction_id, staging, "new-run")
            except RecoveryRequiredError:
                pass
            else:
                raise ValueError("occupied Windows TIFF did not block directory rename")
        if not target.exists() or not staging.exists() or not paths.journal.exists():
            raise ValueError("occupied-file failure did not preserve transaction data")
    finally:
        stop.write_text("stop", encoding="utf-8")
        child.wait(timeout=10)
    with OutputTransaction(target):
        pass
    if read_owned_output(target).run_id != "old-run":
        raise ValueError("occupied-file recovery did not retain the old output")


def run_platform_filesystem_validation() -> dict[str, Any]:
    system = platform.system()
    if system not in {"Darwin", "Windows"}:
        raise ValueError("platform filesystem receipts require macOS or Windows")
    cases: list[dict[str, str]] = []
    with TemporaryDirectory(prefix="x5crop-filesystem-contract-") as temporary:
        parent = Path(temporary)
        identity = identify_filesystem(parent)
        expected = "apfs" if system == "Darwin" else "ntfs"
        if (
            identity.filesystem_kind != expected
            or identity.support_level != OutputSupportLevel.VERIFIED_LOCAL
        ):
            raise ValueError(f"default platform filesystem is not verified {expected}")
        _exercise_lock_isolation(parent)
        _exercise_publication(parent)
        cases.append(_case_record(expected, identity))
        if system == "Windows":
            _windows_link_cases(parent)
            _windows_occupied_case(parent)
    if system == "Darwin":
        cases.append(_darwin_hfs_case())
    cases.extend(unverified_filesystem_cases())
    return {
        "schema": FILESYSTEM_RESULT_SCHEMA,
        "platform_system": system,
        "cases": cases,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold-windows-file", nargs=3, metavar=("PATH", "READY", "STOP"))
    args = parser.parse_args(argv)
    if args.hold_windows_file is not None:
        path, ready, stop = (Path(value) for value in args.hold_windows_file)
        return _hold_windows_file(path, ready, stop)
    result = run_platform_filesystem_validation()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
