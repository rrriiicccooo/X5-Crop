from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.regression.platform_check import check_platform_receipts
from tools.regression.platform_io import cohort_sha256, load_platform_sources
from tools.regression.performance import PERFORMANCE_RECEIPT_SCHEMA
from tools.regression.platform_receipt import (
    PLATFORM_RECEIPT_SCHEMA,
    TARGET_APPLE_SILICON,
    TARGET_WINDOWS_X64,
    _run_verifier,
    validate_platform_receipt,
)


COMMIT = "1" * 40


def _receipt(target: str, performance_name: str, performance_sha: str) -> dict:
    system = "Darwin" if target == TARGET_APPLE_SILICON else "Windows"
    machine = "arm64" if target == TARGET_APPLE_SILICON else "AMD64"
    local_cases = (
        [
            {
                "case": "apfs",
                "status": "passed",
                "filesystem_kind": "apfs",
                "support_level": "verified_local",
                "reason": "verified",
            },
            {
                "case": "hfs_plus",
                "status": "passed",
                "filesystem_kind": "hfs",
                "support_level": "verified_local",
                "reason": "verified",
            },
        ]
        if target == TARGET_APPLE_SILICON
        else [
            {
                "case": "ntfs",
                "status": "passed",
                "filesystem_kind": "ntfs",
                "support_level": "verified_local",
                "reason": "verified",
            }
        ]
    )
    local_cases.append(
        {
            "case": "exfat",
            "status": "unverified",
            "filesystem_kind": "exfat",
            "support_level": "best_effort_unverified",
            "reason": "no receipt",
        }
    )
    environment = {"platform_system": system, "identity": target}
    return {
        "receipt_schema": PLATFORM_RECEIPT_SCHEMA,
        "target": target,
        "git_commit": COMMIT,
        "platform": {
            "system": system,
            "machine": machine,
            "release": "test",
            "version": "test",
        },
        "environment": environment,
        "verification": {
            "full": {"status": "passed"},
        },
        "platform_cohort_sha256": cohort_sha256(),
        "source_sha256s": [
            source.source_sha256
            for source in load_platform_sources(verify_files=False)
        ],
        "platform_io": {
            "cohort_sha256": cohort_sha256(),
            "accuracy_verdict": "not_assessed",
        },
        "filesystems": {"platform_system": system, "cases": local_cases},
        "installer_validation": {"read_only_dependency_check": "passed"},
        "performance_receipt": {
            "file_name": performance_name,
            "sha256": performance_sha,
            "receipt_schema": PERFORMANCE_RECEIPT_SCHEMA,
            "git_commit": COMMIT,
        },
    }


class PlatformReceiptContractTests(unittest.TestCase):
    def test_verifier_receipt_hashes_the_completed_output(self) -> None:
        output = "full verifier passed\n"
        with (
            mock.patch(
                "tools.regression.platform_receipt.shutil.which",
                return_value="/bin/bash",
            ),
            mock.patch(
                "tools.regression.platform_receipt.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout=output),
            ),
        ):
            receipt = _run_verifier("full")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(
            receipt["output_sha256"],
            hashlib.sha256(output.encode("utf-8")).hexdigest(),
        )

    def test_receipt_target_is_derived_and_not_a_cli_argument(self) -> None:
        source = Path("tools/regression/platform_receipt.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("platform.system()", source)
        self.assertIn("platform.machine()", source)
        self.assertNotIn('add_argument("--target"', source)

    def test_platform_check_requires_one_real_target_of_each_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for target in (TARGET_APPLE_SILICON, TARGET_WINDOWS_X64):
                performance = root / f"{target}.performance_receipt.json"
                performance.write_text(
                    json.dumps(
                        {
                            "environment": {
                                "platform_system": (
                                    "Darwin"
                                    if target == TARGET_APPLE_SILICON
                                    else "Windows"
                                ),
                                "identity": target,
                            },
                            "receipt_schema": PERFORMANCE_RECEIPT_SCHEMA,
                        }
                    ),
                    encoding="utf-8",
                )
                digest = hashlib.sha256(performance.read_bytes()).hexdigest()
                receipt_path = root / f"{target}.platform_receipt.json"
                receipt_path.write_text(
                    json.dumps(_receipt(target, performance.name, digest)),
                    encoding="utf-8",
                )
                records.append(receipt_path)
            with mock.patch(
                "tools.regression.platform_check.validate_performance_receipt"
            ) as validate_performance:
                result = check_platform_receipts(records, expected_commit=COMMIT)
            self.assertEqual(len(result), 2)
            self.assertEqual(validate_performance.call_count, 2)

            duplicate = [records[0], root / "duplicate.json"]
            duplicate[1].write_text(records[0].read_text(), encoding="utf-8")
            with mock.patch(
                "tools.regression.platform_check.validate_performance_receipt"
            ):
                with self.assertRaisesRegex(ValueError, "Apple Silicon and Windows"):
                    check_platform_receipts(duplicate, expected_commit=COMMIT)

    def test_platform_validator_rejects_a_forged_machine(self) -> None:
        record = _receipt(TARGET_WINDOWS_X64, "windows.performance_receipt.json", "a" * 64)
        record["platform"]["machine"] = "arm64"
        with self.assertRaisesRegex(ValueError, "identity is invalid"):
            validate_platform_receipt(record, expected_commit=COMMIT)

    def test_platform_validator_rejects_a_missing_exfat_fact(self) -> None:
        record = _receipt(
            TARGET_APPLE_SILICON,
            "apple.performance_receipt.json",
            "a" * 64,
        )
        record["filesystems"]["cases"] = [
            item
            for item in record["filesystems"]["cases"]
            if item["case"] != "exfat"
        ]
        with self.assertRaisesRegex(ValueError, "identity is invalid"):
            validate_platform_receipt(record, expected_commit=COMMIT)


if __name__ == "__main__":
    unittest.main()
