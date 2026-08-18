"""Verify fresh-directory publication on supported development platforms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import plistlib
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from x5crop.output.publication import FreshOutputDirectory, FreshOutputError

from .filesystem_identity import OutputSupportLevel, identify_filesystem


FILESYSTEM_RESULT_SCHEMA = "x5crop_platform_filesystem_result_v2"


def _exercise_publication(parent: Path) -> None:
    target = parent / "x5_crop_output"
    with FreshOutputDirectory(target) as publication:
        assert publication.staging is not None
        (publication.staging / "result.txt").write_text("complete", encoding="utf-8")
        publication.publish()
    if (target / "result.txt").read_text(encoding="utf-8") != "complete":
        raise ValueError("fresh output publication was incomplete")
    try:
        with FreshOutputDirectory(target):
            pass
    except FreshOutputError:
        return
    raise ValueError("existing output target was not refused")


def _record(case: str, identity: object) -> dict[str, str]:
    return {
        "case": case,
        "status": "passed",
        "filesystem_kind": identity.filesystem_kind,
        "support_level": identity.support_level.value,
        "reason": identity.reason,
    }


def _unverified_exfat_record() -> dict[str, str]:
    """Keep exFAT visible without pretending this host verified it."""

    return {
        "case": "exfat",
        "status": "unverified",
        "filesystem_kind": "exfat",
        "support_level": OutputSupportLevel.BEST_EFFORT_UNVERIFIED.value,
        "reason": "no independent exFAT volume was supplied on this host",
    }


def _darwin_hfs_case() -> dict[str, str]:
    with TemporaryDirectory(prefix="x5crop-hfs-contract-") as temporary:
        image = Path(temporary) / "x5crop-hfs.dmg"
        subprocess.run(
            ("hdiutil", "create", "-size", "128m", "-fs", "HFS+", "-volname", "X5CropHFSContract", str(image)),
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
        mounts = tuple(
            Path(str(item["mount-point"]))
            for item in plistlib.loads(attached.stdout).get("system-entities", ())
            if "mount-point" in item
        )
        if len(mounts) != 1:
            raise ValueError("HFS+ validation image did not expose one mount")
        mount = mounts[0]
        try:
            identity = identify_filesystem(mount)
            if identity.support_level != OutputSupportLevel.VERIFIED_LOCAL:
                raise ValueError("HFS+ identity is not verified local")
            _exercise_publication(mount)
            return _record("hfs_plus", identity)
        finally:
            subprocess.run(
                ("hdiutil", "detach", str(mount)),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )


def run_platform_filesystem_validation() -> dict[str, Any]:
    system = platform.system()
    if system not in {"Darwin", "Windows"}:
        raise ValueError("platform filesystem receipts require macOS or Windows")
    cases: list[dict[str, str]] = []
    with TemporaryDirectory(prefix="x5crop-filesystem-contract-") as temporary:
        parent = Path(temporary)
        identity = identify_filesystem(parent)
        expected = "apfs" if system == "Darwin" else "ntfs"
        if identity.support_level != OutputSupportLevel.VERIFIED_LOCAL:
            raise ValueError(f"default platform filesystem is not verified {expected}")
        _exercise_publication(parent)
        cases.append(_record(expected, identity))
    if system == "Darwin":
        cases.append(_darwin_hfs_case())
    cases.append(_unverified_exfat_record())
    return {
        "schema": FILESYSTEM_RESULT_SCHEMA,
        "platform_system": system,
        "cases": cases,
    }


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(json.dumps(run_platform_filesystem_validation(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
