from __future__ import annotations

from copy import deepcopy
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
import tifffile

from x5crop.app_info import REPORT_JSONL_NAME
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.assessment.model import (
    CANDIDATE_GATE_CHECK_CODES,
)
from x5crop.detection.decision.vocabulary import (
    FINAL_REASON_NO_LEGAL_PLACEMENT,
)
from x5crop.report.identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from x5crop.report.validation import validate_current_report_record
from x5crop.run_config import RunConfig
from x5crop.runtime.invocation import PlannedSource
from x5crop.runtime.bootstrap import run_options
from x5crop.runtime.options import RuntimeOptions
from x5crop.runtime.outcome import CompletedInput, FailedInput, FailureStage
from x5crop.runtime.workflow import process_one


def _run_config(
    source: Path,
    output: Path,
    format_id: str = "135",
    requested_count: int | None = 3,
    *,
    debug_analysis: bool = False,
) -> RunConfig:
    configuration = get_detection_configuration(
        format_id,
        requested_count,
    )
    return RunConfig(
        input_path=source,
        output_dir=output,
        format_id=format_id,
        layout_auto=False,
        layout="horizontal",
        count_request=configuration.count_request,
        debug_analysis=debug_analysis,
        jobs=2,
        development_detail=debug_analysis,
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
        requested_count: int | None = 3,
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
        configuration = get_detection_configuration(format_id, requested_count)
        return process_one(
            PlannedSource(1, source, source.stem),
            _run_config(
                source,
                output,
                format_id,
                requested_count,
            ),
            configuration,
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
        self.assertEqual(record["photo_geometry"]["output_slot_count"], 3)
        self.assertEqual(
            record["photo_geometry"]["resolved_output_slots"],
            {"lane_output_slot_counts": [3]},
        )
        self.assertEqual(
            len(record["photo_geometry"]["slot_identities"]),
            3,
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
        self.assertEqual(
            record["output"]["tiff_fidelity"]["validation"],
            "not_created",
        )

    def test_default_count_without_photo_geometry_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.zeros((100, 720), dtype=np.uint16),
                requested_count=None,
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        self.assertEqual(outcome.result.record["decision"]["status"], "needs_review")
        self.assertEqual(outcome.artifacts.frame_outputs, ())

    def test_explicit_count_equal_to_holder_count_has_no_center_authority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.zeros((1000, 2972), dtype=np.uint16),
                format_id="120-67",
                requested_count=2,
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        resolved = outcome.result.record["photo_geometry"]["resolved_slot_count"]
        self.assertEqual(resolved["output_count"], 2)
        self.assertEqual(resolved["holder_full_count"], 2)
        self.assertEqual(
            resolved["authority"],
            "user_explicit_count",
        )
        self.assertNotIn("holder_layout_authority", resolved)
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
        record["output"]["tiff_fidelity"]["validation"] = "pixel_validated"
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
            FINAL_REASON_NO_LEGAL_PLACEMENT,
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
            configuration = get_detection_configuration("135", 3)
            outcome = process_one(
                PlannedSource(1, source, "gray"),
                _run_config(source, output),
                configuration,
                output,
            )
        self.assertIsInstance(outcome, FailedInput)
        assert isinstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.INPUT_PROFILE)

    def test_debug_analysis_and_normal_run_each_detect_fresh(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = (root / "135.tif").resolve()
            tifffile.imwrite(
                source,
                _rgb16(np.zeros((100, 720), dtype=np.uint16)),
                photometric="rgb",
                planarconfig="contig",
            )
            configuration = get_detection_configuration("135", 3)
            planned = PlannedSource(1, source, source.stem)
            analysis_output = root / "analysis"
            analysis_outcome = process_one(
                planned,
                _run_config(
                    source,
                    analysis_output,
                    debug_analysis=True,
                ),
                configuration,
                analysis_output,
            )
            self.assertIsInstance(analysis_outcome, CompletedInput)
            assert isinstance(analysis_outcome, CompletedInput)
            self.assertFalse(
                analysis_outcome.result.record["output"]["finalization"][
                    "frame_export_requested"
                ]
            )
            self.assertIsNone(analysis_outcome.artifacts.review_copy)
            self.assertIsNotNone(analysis_outcome.artifacts.debug_analysis)
            normal_output = root / "normal"
            with mock.patch(
                "x5crop.runtime.workflow.prepare_detection_workspace",
                wraps=__import__(
                    "x5crop.runtime.workflow", fromlist=["prepare_detection_workspace"]
                ).prepare_detection_workspace,
            ) as detector:
                normal_outcome = process_one(
                    planned,
                    _run_config(source, normal_output),
                    configuration,
                    normal_output,
                )
            self.assertTrue(detector.called)
            self.assertIsInstance(normal_outcome, CompletedInput)
            assert isinstance(normal_outcome, CompletedInput)
            self.assertTrue(
                normal_outcome.result.record["output"]["finalization"][
                    "frame_export_requested"
                ]
            )
            self.assertIsNotNone(normal_outcome.artifacts.review_copy)
            self.assertIsNone(normal_outcome.artifacts.debug_analysis)

    def test_production_report_is_compact_and_debug_report_has_development_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = (root / "135.tif").resolve()
            tifffile.imwrite(
                source,
                _rgb16(np.zeros((100, 720), dtype=np.uint16)),
                photometric="rgb",
                planarconfig="contig",
            )
            configuration = get_detection_configuration("135", 3)
            planned = PlannedSource(1, source, source.stem)
            analysis_output = root / "analysis"
            analysis_outcome = process_one(
                planned,
                _run_config(
                    source,
                    analysis_output,
                    debug_analysis=True,
                ),
                configuration,
                analysis_output,
            )
            self.assertIsInstance(analysis_outcome, CompletedInput)
            assert isinstance(analysis_outcome, CompletedInput)
            normal_output = root / "normal"
            outcome = process_one(
                planned,
                _run_config(source, normal_output),
                configuration,
                normal_output,
            )
            self.assertIsInstance(outcome, CompletedInput)
            assert isinstance(outcome, CompletedInput)
            self.assertEqual(analysis_outcome.result.record["detail_level"], "development")
            self.assertIsNotNone(analysis_outcome.result.record["development"])
            self.assertEqual(outcome.result.record["detail_level"], "production")
            self.assertIsNone(outcome.result.record["development"])
            production_geometry = outcome.result.record["photo_geometry"]
            self.assertNotIn(
                "legal_combination_count",
                production_geometry["source_placement_selection"],
            )
            for lane in production_geometry["lanes"]:
                self.assertFalse(
                    {
                        "observation_counts",
                        "complete_chain_count",
                        "cluster_count",
                        "selected_cluster_id",
                    }
                    & set(lane)
                )

    def test_existing_output_is_refused_and_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = (root / "135.tif").resolve()
            tifffile.imwrite(
                source,
                _rgb16(np.zeros((100, 720), dtype=np.uint16)),
                photometric="rgb",
                planarconfig="contig",
            )
            production = root / "MyCrops"
            analysis_options = RuntimeOptions(
                input_path=source,
                output_dir=production,
                format_id="135",
                layout="horizontal",
                requested_count=3,
                debug_analysis=True,
                jobs=1,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_options(analysis_options), 0)
            self.assertTrue((production / REPORT_JSONL_NAME).is_file())
            self.assertTrue(any((production / "_debug_analysis").glob("*.jpg")))
            self.assertFalse(any(production.glob("*.tif")))
            self.assertFalse((production / "needs_review").exists())

            normal_options = RuntimeOptions(
                input_path=source,
                output_dir=production,
                format_id="135",
                layout="horizontal",
                requested_count=3,
                debug_analysis=False,
                jobs=1,
            )
            original_report = (production / REPORT_JSONL_NAME).read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_options(normal_options), 3)
            self.assertEqual(
                (production / REPORT_JSONL_NAME).read_bytes(),
                original_report,
            )


if __name__ == "__main__":
    unittest.main()
