from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest

from x5crop.output.publication import FreshOutputDirectory, FreshOutputError
from x5crop.run_status import RunTerminalOutcome


class RuntimeTerminalContractTests(unittest.TestCase):
    def test_runtime_error_is_not_a_decision_status(self) -> None:
        self.assertEqual(
            {item.value for item in RunTerminalOutcome},
            {"approved_auto", "needs_review", "runtime_error"},
        )
        from x5crop.detection.decision.vocabulary import FINAL_REVIEW_REASONS

        self.assertNotIn("runtime_error", FINAL_REVIEW_REASONS)

    def test_fresh_output_is_hidden_until_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "x5_crop_output"
            with FreshOutputDirectory(target) as publication:
                assert publication.staging is not None
                (publication.staging / "report.jsonl").write_text(
                    "{}\n", encoding="utf-8"
                )
                self.assertFalse(target.exists())
                publication.publish()
            self.assertEqual(
                (target / "report.jsonl").read_text(encoding="utf-8"),
                "{}\n",
            )

    def test_failure_removes_only_current_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            keep = parent / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            staging: Path | None = None
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with FreshOutputDirectory(parent / "output") as publication:
                    staging = publication.staging
                    raise RuntimeError("synthetic")
            assert staging is not None
            self.assertFalse(staging.exists())
            self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

    def test_existing_target_is_refused_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            target.mkdir()
            keep = target / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            with self.assertRaises(FreshOutputError):
                with FreshOutputDirectory(target):
                    pass
            self.assertEqual(keep.read_text(encoding="utf-8"), "keep")


    def test_publication_refuses_a_target_created_at_atomic_boundary(self) -> None:
        from unittest.mock import patch
        from x5crop.output.publication import _rename_without_replacing

        kinds = ("directory", "file") if os.name == "nt" else ("directory", "file", "symlink")
        for kind in kinds:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory)
                target = parent / "output"
                keep = parent / "keep.txt"
                keep.write_text("keep", encoding="utf-8")
                created_identity = []

                def competing_create(source, destination):
                    if kind == "directory":
                        target.mkdir()
                    elif kind == "file":
                        target.write_text("other output", encoding="utf-8")
                    else:
                        target.symlink_to(keep)
                    created_identity.append(target.lstat().st_ino)
                    _rename_without_replacing(source, destination)

                with self.assertRaises(FreshOutputError):
                    with FreshOutputDirectory(target) as publication:
                        staging = publication.staging
                        assert staging is not None
                        (staging / "result.txt").write_text("new", encoding="utf-8")
                        with patch("x5crop.output.publication._rename_without_replacing", competing_create):
                            publication.publish()
                self.assertEqual(target.lstat().st_ino, created_identity[0])
                self.assertFalse(staging.exists())
                self.assertEqual(keep.read_text(encoding="utf-8"), "keep")
                if kind == "directory":
                    self.assertEqual(list(target.iterdir()), [])
                elif kind == "file":
                    self.assertEqual(target.read_text(encoding="utf-8"), "other output")
                else:
                    self.assertTrue(target.is_symlink())

    def test_cancel_then_retry_publishes_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            with self.assertRaises(KeyboardInterrupt):
                with FreshOutputDirectory(target) as publication:
                    staging = publication.staging
                    raise KeyboardInterrupt
            assert staging is not None
            self.assertFalse(staging.exists())
            self.assertFalse(target.exists())
            with FreshOutputDirectory(target) as publication:
                assert publication.staging is not None
                (publication.staging / "result.txt").write_text("complete", encoding="utf-8")
                publication.publish()
                with self.assertRaises(FreshOutputError):
                    publication.publish()
            self.assertEqual((target / "result.txt").read_text(encoding="utf-8"), "complete")

    def test_native_publish_failure_cleans_only_owned_staging(self) -> None:
        import errno
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            keep = Path(directory) / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            with self.assertRaises(FreshOutputError):
                with FreshOutputDirectory(target) as publication:
                    staging = publication.staging
                    with patch("x5crop.output.publication._rename_without_replacing",
                               side_effect=OSError(errno.ENOSPC, "no space")):
                        publication.publish()
            assert staging is not None
            self.assertFalse(staging.exists())
            self.assertFalse(target.exists())
            self.assertEqual(keep.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
