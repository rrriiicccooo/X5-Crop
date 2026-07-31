from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
import tifffile

from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.assessment.model import (
    CANDIDATE_GATE_CHECK_CODES,
)
from x5crop.detection.decision.vocabulary import (
    FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
)
from x5crop.report.identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
)
from x5crop.run_config import RunConfig
from x5crop.runtime.outcome import (
    CompletedInput,
    FailedInput,
    FailureStage,
)
from x5crop.runtime.workflow import process_one


def _run_config(
    source: Path,
    output: Path,
    format_id: str = "135",
    strip_mode: str = "partial",
    requested_count: int | None = None,
) -> RunConfig:
    configuration = get_detection_configuration(
        format_id,
        strip_mode,
        requested_count,
    )
    return RunConfig(
        input_path=source,
        output_dir=output,
        format_id=format_id,
        layout_auto=False,
        layout="horizontal",
        strip_mode=strip_mode,
        count_request=configuration.count_request,
        page=0,
        review_dir=None,
        copy_review_files=False,
        compression="same",
        debug_analysis=False,
        diagnostics=False,
        overwrite=False,
        report=False,
        debug_errors=True,
        jobs=2,
    )


class SourceCoordinateRuntimeContractTest(unittest.TestCase):
    def _process_pixels(
        self,
        root: Path,
        pixels: np.ndarray,
        format_id: str = "135",
        strip_mode: str = "partial",
        requested_count: int | None = None,
    ):
        root.mkdir(parents=True, exist_ok=True)
        source = root / f"{format_id}.tif"
        tifffile.imwrite(source, pixels, photometric="minisblack")
        bundle = DetectionConfigurationBundle.for_format_mode(
            format_id,
            strip_mode,
            requested_count,
        )
        return process_one(
            source,
            _run_config(
                source,
                root / "output",
                format_id,
                strip_mode,
                requested_count,
            ),
            bundle,
        )

    def test_blank_capacity_runtime_approves_writes_and_reports_current_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.zeros((100, 720), dtype=np.uint8),
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = outcome.result.record
        self.assertEqual(record["schema_id"], REPORT_SCHEMA_ID)
        self.assertEqual(record["schema_revision"], REPORT_SCHEMA_REVISION)
        self.assertEqual(record["decision"]["status"], "approved_auto")
        self.assertEqual(record["photo_geometry"]["output_slot_count"], 6)
        self.assertEqual(
            record["photo_geometry"]["resolved_output_slots"],
            {"lane_output_slot_counts": [6]},
        )
        self.assertEqual(
            record["photo_geometry"]["selected_scan_canvas_profile_id"],
            "135_standard",
        )
        self.assertEqual(
            len(record["photo_geometry"]["slot_identities"]),
            6,
        )
        self.assertEqual(len(outcome.artifacts.frame_outputs), 6)
        self.assertEqual(
            tuple(
                item["code"]
                for item in record["candidate_gate"]["checks"]
            ),
            CANDIDATE_GATE_CHECK_CODES,
        )
        self.assertTrue(
            all(
                item["final_review_reason"] is None
                for item in record["candidate_gate"]["checks"]
            )
        )
        finalization = record["output"]["finalization"]
        self.assertTrue(finalization["frame_export_performed"])
        self.assertEqual(finalization["official_tiff_count"], 6)
        self.assertTrue(
            all(
                geometry["provenance"] == "grid_inferred_blank"
                for geometry in finalization[
                    "resolved_output_geometries"
                ]
            )
        )
        self.assertTrue(
            record["output"]["tiff_fidelity"][
                "write_readback_validated"
            ]
        )
        self.assertEqual(
            record["output"]["tiff_fidelity"][
                "source_sample_count_per_roi"
            ],
            1,
        )

    def test_fixed_full_without_photo_geometry_is_review_and_exports_nothing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.zeros((100, 720), dtype=np.uint8),
                strip_mode="full",
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = outcome.result.record
        self.assertEqual(record["decision"]["status"], "needs_review")
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        self.assertFalse(
            record["output"]["finalization"]["official_tiff_expected"]
        )
        self.assertEqual(
            record["output"]["finalization"]["official_tiff_count"],
            0,
        )

    def test_diagnostics_preserves_decision_but_writes_no_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "diagnostics.tif"
            tifffile.imwrite(source, np.zeros((100, 720), dtype=np.uint8))
            bundle = DetectionConfigurationBundle.for_format_mode(
                "135",
                "partial",
            )
            outcome = process_one(
                source,
                replace(
                    _run_config(source, root / "output"),
                    diagnostics=True,
                ),
                bundle,
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = outcome.result.record
        self.assertEqual(record["decision"]["status"], "approved_auto")
        self.assertEqual(record["photo_geometry"]["output_slot_count"], 6)
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        finalization = record["output"]["finalization"]
        self.assertTrue(finalization["frame_export_eligible"])
        self.assertFalse(finalization["frame_export_requested"])
        self.assertFalse(finalization["frame_export_performed"])
        self.assertEqual(finalization["reason"], "diagnostics_read_only")
        self.assertEqual(
            record["output"]["tiff_fidelity"]["success_receipt"],
            "not_requested_diagnostics",
        )

    def test_scan_canvas_contradiction_is_review_not_terminal_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.arange(10000, dtype=np.uint8).reshape(100, 100),
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = outcome.result.record
        self.assertEqual(record["decision"]["status"], "needs_review")
        self.assertIn(
            FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
            record["decision"]["final_review_reasons"],
        )
        self.assertEqual(record["output"]["output_files"], [])

    def test_output_and_readback_failures_remain_terminal(self) -> None:
        for target, message in (
            ("x5crop.runtime.workflow.write_crops", "write failure"),
            (
                "x5crop.io.tiff.validate_written_tiff",
                "readback failure",
            ),
        ):
            with self.subTest(target=target):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    with mock.patch(
                        target,
                        side_effect=OSError(message),
                    ):
                        outcome = self._process_pixels(
                            root,
                            np.zeros((100, 720), dtype=np.uint8),
                        )
                self.assertIsInstance(outcome, FailedInput)
                assert isinstance(outcome, FailedInput)
                self.assertEqual(outcome.failure_stage, FailureStage.OUTPUT)
                self.assertEqual(outcome.artifacts.frame_outputs, ())
                self.assertIn(message, outcome.error_message)

    def test_input_read_failure_remains_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch(
                "x5crop.runtime.workflow.read_tiff",
                side_effect=OSError("synthetic read failure"),
            ):
                outcome = self._process_pixels(
                    root,
                    np.zeros((100, 720), dtype=np.uint8),
                )
        self.assertIsInstance(outcome, FailedInput)
        assert isinstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.IMAGE_READ)
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        self.assertIn("synthetic read failure", outcome.error_message)


if __name__ == "__main__":
    unittest.main()
