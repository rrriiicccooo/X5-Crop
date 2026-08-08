"""Validate one Apple Silicon and one Windows receipt for the same commit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .performance import validate_receipt as validate_performance_receipt
from .platform_receipt import (
    TARGET_APPLE_SILICON,
    TARGET_WINDOWS_X64,
    validate_platform_receipt,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_map(receipt: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        str(item["case"]): item
        for item in receipt["filesystems"]["cases"]
    }


def check_platform_receipts(
    paths: Sequence[Path],
    *,
    expected_commit: str,
) -> tuple[dict[str, Any], ...]:
    if len(paths) != 2 or len(set(path.resolve() for path in paths)) != 2:
        raise ValueError("platform-check requires exactly two distinct receipts")
    receipts: list[dict[str, Any]] = []
    for path in paths:
        record = validate_platform_receipt(
            json.loads(path.read_text(encoding="utf-8")),
            expected_commit=expected_commit,
        )
        performance_identity = record["performance_receipt"]
        performance_path = path.parent / performance_identity["file_name"]
        if (
            not performance_path.is_file()
            or _sha256(performance_path) != performance_identity["sha256"]
        ):
            raise ValueError("associated performance receipt content is unavailable")
        performance = json.loads(performance_path.read_text(encoding="utf-8"))
        validate_performance_receipt(performance, expected_commit=expected_commit)
        if (
            performance.get("receipt_schema")
            != performance_identity.get("receipt_schema")
            or performance.get("environment") != record.get("environment")
        ):
            raise ValueError("platform and performance environments differ")
        receipts.append(record)
    targets = {record["target"] for record in receipts}
    if targets != {TARGET_APPLE_SILICON, TARGET_WINDOWS_X64}:
        raise ValueError("platform-check requires Apple Silicon and Windows x64")
    for record in receipts:
        cases = _case_map(record)
        required = (
            ("apfs", "hfs_plus", "exfat")
            if record["target"] == TARGET_APPLE_SILICON
            else ("ntfs", "exfat")
        )
        if any(case not in cases for case in required):
            raise ValueError("platform receipt omits an independent filesystem case")
        verified = required[:-1]
        if any(
            cases[case]["status"] != "passed"
            or cases[case]["support_level"] != "verified_local"
            for case in verified
        ):
            raise ValueError("verified local filesystem case did not pass")
        if (
            cases["exfat"]["status"] != "unverified"
            or cases["exfat"]["support_level"] != "best_effort_unverified"
        ):
            raise ValueError("exFAT status was silently upgraded")
    return tuple(receipts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("receipts", nargs="+", type=Path)
    args = parser.parse_args(argv)
    receipts = check_platform_receipts(
        tuple(path.resolve() for path in args.receipts),
        expected_commit=args.expected_commit,
    )
    print(
        "platform receipts valid: "
        + ", ".join(sorted(record["target"] for record in receipts))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
