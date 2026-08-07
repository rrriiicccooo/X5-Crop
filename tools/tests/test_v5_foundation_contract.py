from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from x5crop.io.orientation import (
    canonicalize_orientation,
    orientation_mapping,
)
from x5crop.output.naming import (
    MAX_COMPONENT_UTF16_UNITS,
    PortableNameError,
    is_windows_reserved_name,
    portable_component,
    portable_frame_name,
    transaction_token_for_target,
    utf16_units,
    validate_explicit_output_leaf,
)
from x5crop.output.filesystem import OutputSupportLevel, identify_filesystem
from x5crop.output.ownership import (
    OutputOwnershipError,
    read_owned_output,
    write_owned_output_manifest,
)
from x5crop.output.safe_tree import (
    UnsafeOutputTreeError,
    inventory_tree,
    safe_remove_tree,
)
from x5crop.output.transaction import (
    OutputLock,
    OutputTransaction,
    OutputTransactionError,
    RecoveryRequiredError,
    TransactionJournal,
    TransactionPaths,
    TransactionState,
    _write_journal,
)
from x5crop.runtime.disk_budget import DiskSpaceBudgetError, RunWideDiskBudget


def _make_owned_output(root: Path, run_id: str, source_name: str = "source.tif") -> None:
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
                "source_name": source_name,
                "terminal_status": "approved_auto",
            },
        ),
    )


class OrientationFoundationContractTests(unittest.TestCase):
    def test_all_orientation_tags_bake_the_expected_visual_raster(self) -> None:
        raw = np.asarray([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
        expected = {
            1: [[1, 2, 3], [4, 5, 6]],
            2: [[3, 2, 1], [6, 5, 4]],
            3: [[6, 5, 4], [3, 2, 1]],
            4: [[4, 5, 6], [1, 2, 3]],
            5: [[1, 4], [2, 5], [3, 6]],
            6: [[4, 1], [5, 2], [6, 3]],
            7: [[6, 3], [5, 2], [4, 1]],
            8: [[3, 6], [2, 5], [1, 4]],
        }
        for tag, visual in expected.items():
            with self.subTest(orientation=tag):
                canonical, mapping = canonicalize_orientation(raw, "YX", tag)
                self.assertEqual(canonical.tolist(), visual)
                self.assertTrue(canonical.flags.c_contiguous)
                for y in range(raw.shape[0]):
                    for x in range(raw.shape[1]):
                        cx, cy = mapping.map_raw_point(float(x), float(y))
                        rx, ry = mapping.map_canonical_point(cx, cy)
                        self.assertEqual((rx, ry), (float(x), float(y)))
                        self.assertEqual(canonical[int(cy), int(cx)], raw[y, x])

    def test_invalid_orientation_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            orientation_mapping(9, 10, 20)


class PortableOutputNameContractTests(unittest.TestCase):
    def test_windows_reserved_names_include_console_aliases(self) -> None:
        for value in (
            "CON",
            "NUL.txt",
            "CONIN$",
            "CONOUT$.tif",
            "COM1.jpg",
            "COM¹.jpg",
            "LPT9",
            "LPT³.dat",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_windows_reserved_name(value))

    def test_python_313_windows_reserved_rules_cross_check_frozen_table(
        self,
    ) -> None:
        if os.name != "nt" or not hasattr(os.path, "isreserved"):
            self.skipTest("requires Windows Python 3.13+")
        for value in (
            "CON",
            "NUL.txt",
            "CONIN$",
            "CONOUT$.tif",
            "COM1.jpg",
            "COM¹.jpg",
            "LPT9",
            "LPT³.dat",
            "bad<name.tif",
            "trailing. ",
        ):
            with self.subTest(value=value):
                self.assertTrue(os.path.isreserved(value))
                with self.assertRaises(PortableNameError):
                    validate_explicit_output_leaf(value)

    def test_generated_names_are_portable_and_bounded(self) -> None:
        name = portable_frame_name(
            "CON:<bad>?" + "照片" * 100 + ".tif",
            input_ordinal=7,
            slot_index=2,
        )
        self.assertLessEqual(utf16_units(name.value), MAX_COMPONENT_UTF16_UNITS)
        self.assertTrue(name.value.endswith("_02.tif"))
        self.assertIn("~0007-", name.value)
        self.assertNotIn(":", name.value)
        self.assertNotIn("?", name.value)

    def test_explicit_output_leaf_is_never_silently_rewritten(self) -> None:
        with self.assertRaises(PortableNameError):
            validate_explicit_output_leaf("NUL")
        with self.assertRaises(PortableNameError):
            validate_explicit_output_leaf("trailing. ")

    def test_transaction_token_uses_only_short_name_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ("长" * 80)
            token = transaction_token_for_target(target)
        self.assertLessEqual(utf16_units(token), 64)
        self.assertRegex(token, r"~[0-9a-f]{8}$")

    def test_casefold_collision_is_detectable_before_decode(self) -> None:
        first = portable_component("Photo", input_ordinal=1, suffix="_01.tif")
        second = portable_component("photo", input_ordinal=2, suffix="_01.tif")
        self.assertEqual(first.collision_key, second.collision_key)


class SafeTreeAndTransactionContractTests(unittest.TestCase):
    def test_darwin_local_temporary_directory_is_identified_as_apfs(self) -> None:
        if __import__("platform").system().lower() != "darwin":
            self.skipTest("Darwin filesystem identity contract")
        with tempfile.TemporaryDirectory() as directory:
            identity = identify_filesystem(Path(directory))
        self.assertEqual(identity.filesystem_kind, "apfs")
        self.assertEqual(identity.support_level, OutputSupportLevel.VERIFIED_LOCAL)

    def test_inventory_excludes_manifest_and_directory_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "owned"
            _make_owned_output(root, "run-a")
            owned = read_owned_output(root)
        self.assertFalse(
            any(item.relative_path == "x5_crop_run_manifest.jsonl" for item in owned.inventory)
        )
        self.assertTrue(all(item.size is None for item in owned.inventory if item.kind == "directory"))

    def test_safe_tree_refuses_symlinks_without_following_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tree"
            outside = Path(directory) / "outside.txt"
            root.mkdir()
            outside.write_text("keep", encoding="utf-8")
            try:
                (root / "link").symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaises(UnsafeOutputTreeError):
                inventory_tree(
                    root,
                    manifest_name="manifest.jsonl",
                    role_for_file=lambda path: "test",
                )
            with self.assertRaises(UnsafeOutputTreeError):
                safe_remove_tree(root)
            self.assertEqual(outside.read_text(encoding="utf-8"), "keep")

    def test_target_specific_lock_is_nonblocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / ".MyCrops.lock"
            with OutputLock(lock_path):
                with self.assertRaises(OutputTransactionError):
                    with OutputLock(lock_path):
                        pass

    def test_publish_replaces_only_a_current_owned_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            _make_owned_output(target, "old-run")
            with OutputTransaction(target) as transaction:
                transaction_id, staging = transaction.create_staging("new-run")
                _make_owned_output(staging, "new-run", "new-source.tif")
                transaction.publish(transaction_id, staging, "new-run")
            owned = read_owned_output(target)
            self.assertEqual(owned.run_id, "new-run")
            self.assertFalse(tuple(Path(directory).glob(".x5_crop_output.old-*")))
            self.assertFalse(tuple(Path(directory).glob(".x5_crop_output.new-*")))

    def test_building_process_crash_discards_only_identified_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            _make_owned_output(target, "old-run")
            transaction = OutputTransaction(target)
            transaction.__enter__()
            _transaction_id, staging = transaction.create_staging("new-run")
            (staging / "partial.tif").write_bytes(b"partial")
            transaction.__exit__(None, None, None)

            with OutputTransaction(target):
                pass

            self.assertEqual(read_owned_output(target).run_id, "old-run")
            self.assertFalse(staging.exists())
            self.assertFalse(TransactionPaths.for_target(target).journal.exists())

    def test_unknown_user_file_stops_replacement_and_preserves_old_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            target.mkdir()
            user_file = target / "do-not-delete.txt"
            user_file.write_text("user", encoding="utf-8")
            with OutputTransaction(target) as transaction:
                transaction_id, staging = transaction.create_staging("new-run")
                _make_owned_output(staging, "new-run")
                with self.assertRaises(OutputOwnershipError):
                    transaction.publish(transaction_id, staging, "new-run")
            self.assertEqual(user_file.read_text(encoding="utf-8"), "user")

    def test_recovery_restores_old_output_between_the_two_renames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            paths = TransactionPaths.for_target(target)
            transaction_id = "a" * 32
            staging = paths.staging(transaction_id)
            previous = paths.previous(transaction_id)
            _make_owned_output(staging, "new-run")
            _make_owned_output(previous, "old-run")
            _write_journal(
                paths.journal,
                TransactionJournal(
                    transaction_id=transaction_id,
                    run_id="new-run",
                    target=str(paths.target),
                    staging=str(staging),
                    previous=str(previous),
                    state=TransactionState.OLD_MOVED,
                ),
            )
            with OutputTransaction(target):
                pass
            self.assertEqual(read_owned_output(target).run_id, "old-run")
            self.assertFalse(staging.exists())
            self.assertFalse(paths.journal.exists())

    def test_recovery_covers_old_rename_before_journal_state_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            paths = TransactionPaths.for_target(target)
            transaction_id = "c" * 32
            staging = paths.staging(transaction_id)
            previous = paths.previous(transaction_id)
            _make_owned_output(staging, "new-run")
            _make_owned_output(previous, "old-run")
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
            with OutputTransaction(target):
                pass
            self.assertEqual(read_owned_output(target).run_id, "old-run")
            self.assertFalse(staging.exists())
            self.assertFalse(previous.exists())

    def test_recovery_covers_new_rename_before_journal_state_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            paths = TransactionPaths.for_target(target)
            transaction_id = "d" * 32
            previous = paths.previous(transaction_id)
            _make_owned_output(target, "new-run")
            _make_owned_output(previous, "old-run")
            _write_journal(
                paths.journal,
                TransactionJournal(
                    transaction_id=transaction_id,
                    run_id="new-run",
                    target=str(paths.target),
                    staging=str(paths.staging(transaction_id)),
                    previous=str(previous),
                    state=TransactionState.OLD_MOVED,
                ),
            )
            with OutputTransaction(target):
                pass
            self.assertEqual(read_owned_output(target).run_id, "new-run")
            self.assertFalse(previous.exists())
            self.assertFalse(paths.journal.exists())

    def test_ambiguous_state_preserves_every_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            paths = TransactionPaths.for_target(target)
            transaction_id = "b" * 32
            staging = paths.staging(transaction_id)
            previous = paths.previous(transaction_id)
            _make_owned_output(target, "unexpected-run")
            _make_owned_output(staging, "new-run")
            _make_owned_output(previous, "old-run")
            _write_journal(
                paths.journal,
                TransactionJournal(
                    transaction_id=transaction_id,
                    run_id="new-run",
                    target=str(paths.target),
                    staging=str(staging),
                    previous=str(previous),
                    state=TransactionState.OLD_MOVED,
                ),
            )
            with self.assertRaises(RecoveryRequiredError):
                with OutputTransaction(target):
                    pass
            self.assertTrue(target.exists())
            self.assertTrue(staging.exists())
            self.assertTrue(previous.exists())
            self.assertTrue(paths.journal.exists())

    def test_windows_junction_predicate_is_part_of_safe_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tree"
            root.mkdir()
            (root / "child").mkdir()
            with mock.patch("x5crop.output.safe_tree.os.name", "nt"), mock.patch.object(
                Path,
                "is_junction",
                return_value=True,
                create=True,
            ):
                with self.assertRaises(UnsafeOutputTreeError):
                    inventory_tree(
                        root,
                        manifest_name="manifest.jsonl",
                        role_for_file=lambda path: "test",
                    )


class RunWideDiskBudgetContractTests(unittest.TestCase):
    def test_scheduler_reserves_once_and_serializes_worker_claims(self) -> None:
        budget = RunWideDiskBudget(available_bytes=1000, required_bytes=800)
        budget.claim(300)
        budget.claim(500)
        self.assertEqual(budget.remaining_bytes, 0)
        with self.assertRaises(DiskSpaceBudgetError):
            budget.claim(1)
        budget.release(400)
        self.assertEqual(budget.remaining_bytes, 400)

    def test_run_reservation_fails_before_workers_start(self) -> None:
        with self.assertRaises(DiskSpaceBudgetError):
            RunWideDiskBudget(available_bytes=799, required_bytes=800)


if __name__ == "__main__":
    unittest.main()
