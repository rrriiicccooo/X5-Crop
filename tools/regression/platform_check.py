"""Validate Apple Silicon, Intel macOS, and Windows receipts for one commit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .performance import validate_receipt as validate_performance_receipt
from .file_identity import sha256_file
from .platform_receipt import (
    TARGET_APPLE_SILICON,
    TARGET_INTEL_MAC,
    TARGET_WINDOWS_X64,
    validate_platform_receipt,
)


def check_platform_receipts(
    paths: Sequence[Path],
    *,
    expected_commit: str,
) -> tuple[dict[str, Any], ...]:
    if len(paths) != 3 or len(set(path.resolve() for path in paths)) != 3:
        raise ValueError("platform-check requires exactly three distinct receipts")
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
            or sha256_file(performance_path)
            != performance_identity["sha256"]
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
    if targets != {
        TARGET_APPLE_SILICON,
        TARGET_INTEL_MAC,
        TARGET_WINDOWS_X64,
    }:
        raise ValueError(
            "platform-check requires Apple Silicon, Intel macOS, and Windows x64"
        )
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
