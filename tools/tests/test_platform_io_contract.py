from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tools.regression.platform_io import (
    COHORT_PATH,
    EXPECTED_SAMPLE_IDS,
    _raw_raster_for_orientation,
    load_platform_sources,
)
from x5crop.output.ownership import read_owned_output, write_owned_output_manifest
from x5crop.output.transaction import (
    OutputTransaction,
    TransactionJournal,
    TransactionPaths,
    TransactionState,
    _write_journal,
)


ROOT = Path(__file__).resolve().parents[2]


def _owned(root: Path, run_id: str) -> None:
    root.mkdir(exist_ok=True)
    (root / "x5_crop_report.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "x5_crop_summary.csv").write_text("status\n", encoding="utf-8")
    write_owned_output_manifest(
        root,
        run_id=run_id,
        run_record={"filesystem": {"support_level": "verified_local"}},
        terminal_records=(
            {
                "input_ordinal": 1,
                "source_name": "source.tif",
                "terminal_status": "needs_review",
            },
        ),
    )


class PlatformIoContractTests(unittest.TestCase):
    def test_platform_cohort_has_six_exact_sha_bound_responsibilities(self) -> None:
        sources = load_platform_sources(verify_files=False)
        self.assertEqual(tuple(item.sample_id for item in sources), EXPECTED_SAMPLE_IDS)
        self.assertEqual(
            {item.sample_id for item in sources if item.role == "io_only"},
            {"S046", "S101"},
        )
        self.assertEqual(
            {item.sample_id for item in sources if item.role == "user_path"},
            {"S027", "S062", "S094", "S098"},
        )
        for source in sources:
            self.assertEqual(len(source.source_sha256), 64)

    def test_orientation_3_and_8_inverse_rasters_restore_canonical_pixels(self) -> None:
        canonical = np.arange(3 * 4 * 3, dtype=np.uint16).reshape(3, 4, 3)
        raw3 = _raw_raster_for_orientation(canonical, 3)
        raw8 = _raw_raster_for_orientation(canonical, 8)
        self.assertEqual(raw3.shape, canonical.shape)
        self.assertEqual(raw8.shape, (4, 3, 3))

    def test_crash_between_renames_recovers_the_complete_old_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            paths = TransactionPaths.for_target(target)
            transaction_id = "e" * 32
            staging = paths.staging(transaction_id)
            previous = paths.previous(transaction_id)
            _owned(target, "old-run")
            _owned(staging, "new-run")
            _write_journal(
                paths.journal,
                TransactionJournal(
                    transaction_id=transaction_id,
                    run_id="new-run",
                    target=str(paths.target),
                    staging=str(staging),
                    previous=str(previous),
                    state=TransactionState.PREPARED,
                ),
            )
            completed = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "tools/tests/transaction_crash_worker.py"),
                    str(target),
                    str(previous),
                ),
                check=False,
            )
            self.assertEqual(completed.returncode, 91)
            self.assertFalse(target.exists())
            with OutputTransaction(target):
                pass
            self.assertEqual(read_owned_output(target).run_id, "old-run")
            self.assertFalse(staging.exists())
            self.assertFalse(previous.exists())
            self.assertFalse(paths.journal.exists())


if __name__ == "__main__":
    unittest.main()
