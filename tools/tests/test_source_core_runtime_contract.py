from __future__ import annotations

from copy import deepcopy
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
from x5crop.report.identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from x5crop.report.validation import validate_current_report_record
from x5crop.run_config import RunConfig
from x5crop.runtime.invocation import PlannedSource
from x5crop.runtime.outcome import CompletedInput, FailedInput, FailureStage
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
        debug_analysis=False,
        allow_best_effort_output=False,
        jobs=2,
    )


def _rgb16(pixels: np.ndarray) -> np.ndarray:
    normalized = np.asarray(pixels, dtype=np.uint16)
    return np.repeat(normalized[..., np.newaxis], 3, axis=2)


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
        source = (root / f"{format_id}.tif").resolve()
        tifffile.imwrite(
            source,
            _rgb16(pixels),
            photometric="rgb",
            planarconfig="contig",
        )
        output = root / "output"
        bundle = DetectionConfigurationBundle.for_format_mode(
            format_id,
            strip_mode,
            requested_count,
        )
        return process_one(
            PlannedSource(1, source, source.stem),
            _run_config(
                source,
                output,
                format_id,
                strip_mode,
                requested_count,
            ),
            bundle,
            output,
        )

    def test_zero_anchor_capacity_is_review_in_v5_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.zeros((100, 720), dtype=np.uint16),
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = outcome.result.record
        self.assertEqual(record["schema_id"], REPORT_SCHEMA_ID)
        self.assertEqual(record["schema_revision"], REPORT_SCHEMA_REVISION)
        self.assertEqual(record["decision"]["status"], "needs_review")
        self.assertEqual(record["photo_geometry"]["output_slot_count"], 6)
        self.assertEqual(
            record["photo_geometry"]["resolved_output_slots"],
            {"lane_output_slot_counts": [6]},
        )
        self.assertEqual(
            len(record["photo_geometry"]["slot_identities"]),
            6,
        )
        self.assertEqual(outcome.artifacts.frame_outputs, ())
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
        self.assertFalse(finalization["frame_export_eligible"])
        self.assertFalse(finalization["frame_export_performed"])
        self.assertEqual(finalization["official_tiff_count"], 0)
        self.assertEqual(finalization["resolved_output_geometries"], [])
        self.assertFalse(
            record["output"]["tiff_fidelity"]["write_readback_validated"]
        )

    def test_fixed_full_without_photo_geometry_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.zeros((100, 720), dtype=np.uint16),
                strip_mode="full",
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        self.assertEqual(outcome.result.record["decision"]["status"], "needs_review")
        self.assertEqual(outcome.artifacts.frame_outputs, ())

    def test_current_report_rejects_false_tiff_readback_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.zeros((100, 720), dtype=np.uint16),
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = deepcopy(outcome.result.record)
        record["output"]["tiff_fidelity"]["success_receipt"] = "validated"
        with self.assertRaises(ValueError):
            validate_current_report_record(record)

    def test_scan_canvas_contradiction_is_review_not_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.arange(10_000, dtype=np.uint16).reshape(100, 100),
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = outcome.result.record
        self.assertEqual(record["decision"]["status"], "needs_review")
        self.assertIn(
            FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
            record["decision"]["final_review_reasons"],
        )

    def test_input_read_failure_remains_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch(
                "x5crop.runtime.workflow.read_tiff",
                side_effect=OSError("synthetic read failure"),
            ):
                outcome = self._process_pixels(
                    root,
                    np.zeros((100, 720), dtype=np.uint16),
                )
        self.assertIsInstance(outcome, FailedInput)
        assert isinstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.IMAGE_READ)
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        self.assertIn("synthetic read failure", outcome.error_message)

    def test_non_v5_tiff_domain_is_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = (root / "gray.tif").resolve()
            tifffile.imwrite(source, np.zeros((100, 720), dtype=np.uint8))
            output = root / "output"
            bundle = DetectionConfigurationBundle.for_format_mode(
                "135", "partial"
            )
            outcome = process_one(
                PlannedSource(1, source, "gray"),
                _run_config(source, output),
                bundle,
                output,
            )
        self.assertIsInstance(outcome, FailedInput)
        assert isinstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.INPUT_PROFILE)


if __name__ == "__main__":
    unittest.main()
