from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock
import os

from x5crop.output.ownership import read_owned_output, write_owned_output_manifest
from x5crop.output.transaction import (
    OutputTransaction,
    RecoveryRequiredError,
    TransactionPaths,
)
from x5crop.run_status import RunTerminalOutcome
from x5crop.runtime.app import PublicationDisposition, publication_disposition
from x5crop.runtime.invocation import PlannedSource
from x5crop.runtime.manifest import SourceTerminalRecord
from x5crop.runtime.outcome import (
    FailedInput,
    FailureStage,
    RuntimeArtifacts,
    RuntimeMetrics,
)


def _source(ordinal: int) -> PlannedSource:
    return PlannedSource(
        ordinal,
        (Path.cwd() / f"source-{ordinal}.tif").resolve(),
        f"source-{ordinal}",
    )


def _failed(source: PlannedSource) -> FailedInput:
    return FailedInput(
        source=source.path,
        failure_stage=FailureStage.IMAGE_READ,
        error_code="TiffError",
        error_message="invalid TIFF",
        artifacts=RuntimeArtifacts.empty(),
        traceback_text=None,
        metrics=RuntimeMetrics.unavailable(),
    )


class _CompletedSentinel:
    pass


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


class RuntimeTerminalContractTests(unittest.TestCase):
    def test_runtime_error_is_not_a_decision_status(self) -> None:
        self.assertEqual(
            {item.value for item in RunTerminalOutcome},
            {"approved_auto", "needs_review", "runtime_error"},
        )
        record = SourceTerminalRecord(
            1,
            "bad.tif",
            "bad",
            10,
            20,
            RunTerminalOutcome.RUNTIME_ERROR,
            FailureStage.IMAGE_READ,
            "TiffError",
            "invalid TIFF",
            RuntimeArtifacts.empty(),
        )
        self.assertEqual(record.terminal_status, RunTerminalOutcome.RUNTIME_ERROR)
        from x5crop.detection.decision.vocabulary import FINAL_REVIEW_REASONS

        self.assertNotIn("runtime_error", FINAL_REVIEW_REASONS)

    def test_needs_review_only_and_mixed_runs_publish(self) -> None:
        first, second = _source(1), _source(2)
        completed = _CompletedSentinel()
        self.assertEqual(
            publication_disposition((first,), ((first, completed),)),
            PublicationDisposition.PUBLISH,
        )
        self.assertEqual(
            publication_disposition(
                (first, second),
                ((first, _failed(first)), (second, completed)),
            ),
            PublicationDisposition.PUBLISH,
        )

    def test_all_runtime_errors_keep_prior_output(self) -> None:
        first, second = _source(1), _source(2)
        self.assertEqual(
            publication_disposition(
                (first, second),
                ((first, _failed(first)), (second, _failed(second))),
            ),
            PublicationDisposition.KEEP_PRIOR_OUTPUT,
        )

    def test_incomplete_or_reordered_terminals_are_invocation_fatal(self) -> None:
        first, second = _source(1), _source(2)
        for outcomes in (
            ((first, _failed(first)),),
            ((second, _failed(second)), (first, _failed(first))),
            ((first, _failed(first)), (first, _failed(first))),
        ):
            with self.subTest(outcomes=outcomes):
                with self.assertRaisesRegex(ValueError, "exactly one ordered"):
                    publication_disposition((first, second), outcomes)

    def test_publish_failure_preserves_target_staging_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            _owned(target, "old-run")
            paths = TransactionPaths.for_target(target)
            with OutputTransaction(target) as transaction:
                transaction_id, staging = transaction.create_staging("new-run")
                _owned(staging, "new-run")
                with mock.patch(
                    "x5crop.output.transaction._rename",
                    side_effect=PermissionError("locked"),
                ):
                    with self.assertRaises(RecoveryRequiredError):
                        transaction.publish(transaction_id, staging, "new-run")
            self.assertEqual(read_owned_output(target).run_id, "old-run")
            self.assertTrue(staging.exists())
            self.assertTrue(paths.journal.exists())

    def test_publish_and_rollback_failure_preserve_every_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            _owned(target, "old-run")
            paths = TransactionPaths.for_target(target)
            with OutputTransaction(target) as transaction:
                transaction_id, staging = transaction.create_staging("new-run")
                previous = paths.previous(transaction_id)
                _owned(staging, "new-run")
                calls = 0

                def fail_after_old_move(source: Path, destination: Path) -> None:
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        os.rename(source, destination)
                        return
                    raise PermissionError("locked")

                with mock.patch(
                    "x5crop.output.transaction._rename",
                    side_effect=fail_after_old_move,
                ):
                    with self.assertRaises(RecoveryRequiredError):
                        transaction.publish(transaction_id, staging, "new-run")
            self.assertFalse(target.exists())
            self.assertTrue(staging.exists())
            self.assertTrue(previous.exists())
            self.assertTrue(paths.journal.exists())

    def test_corrupt_journal_and_multiple_candidates_are_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            paths = TransactionPaths.for_target(target)
            first = paths.staging("1" * 32)
            second = paths.staging("2" * 32)
            _owned(target, "old-run")
            _owned(first, "new-one")
            _owned(second, "new-two")
            paths.journal.write_text("{not-json\n", encoding="utf-8")
            with self.assertRaises(RecoveryRequiredError):
                with OutputTransaction(target):
                    pass
            self.assertTrue(target.exists())
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertTrue(paths.journal.exists())


if __name__ == "__main__":
    unittest.main()
