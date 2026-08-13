from __future__ import annotations

from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
