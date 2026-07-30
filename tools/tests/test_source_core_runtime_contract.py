from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import tifffile

from tools.regression.golden_baseline import (
    COMPARISON_SCHEMA,
    compare_baseline_record_to_report,
)
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
    core_facts_sha256,
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
    strip_mode: str = "full",
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
        debug=False,
        debug_analysis=False,
        diagnostics=False,
        overwrite=False,
        report=False,
        debug_errors=True,
        jobs=2,
    )


def _full_135_pixels(height: int = 100, width: int = 720) -> np.ndarray:
    rng = np.random.default_rng(9)
    pixels = rng.integers(20, 230, size=(height, width), dtype=np.uint8)
    for boundary in (9, 121, 127, 239, 245, 357, 363, 475, 481, 593, 599, 711):
        pixels[:, max(0, boundary - 1) : min(width, boundary + 1)] = (
            0 if boundary % 2 else 255
        )
    return pixels


class BoundedSafeCropRuntimeContractTest(unittest.TestCase):
    def _process_pixels(
        self,
        root: Path,
        pixels: np.ndarray,
        format_id: str,
        strip_mode: str = "full",
        requested_count: int | None = None,
    ):
        root.mkdir(parents=True, exist_ok=True)
        source = root / f"{format_id}.tif"
        tifffile.imwrite(source, pixels, photometric="minisblack")
        configuration_bundle = DetectionConfigurationBundle.for_format_mode(
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
            configuration_bundle,
        )

    def test_full_runtime_approves_writes_and_reports_current_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                _full_135_pixels(),
                "135",
            )
            self.assertIsInstance(outcome, CompletedInput)
            assert isinstance(outcome, CompletedInput)
            record = outcome.result.record
            self.assertEqual(record["schema_id"], REPORT_SCHEMA_ID)
            self.assertEqual(record["schema_revision"], REPORT_SCHEMA_REVISION)
            self.assertEqual(record["decision"]["status"], "approved_auto")
            self.assertEqual(record["grid_selection"]["output_slot_count"], 6)
            self.assertEqual(
                record["grid_selection"]["resolved_output_slots"],
                {"lane_output_slot_counts": [6]},
            )
            self.assertEqual(
                record["grid_selection"][
                    "selected_scan_canvas_profile_id"
                ],
                "135_standard",
            )
            self.assertEqual(
                len(record["grid_selection"]["slot_identities"]),
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

    def test_core_hash_excludes_measurement_durations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                _full_135_pixels(),
                "135",
            )
        assert isinstance(outcome, CompletedInput)
        mutated = deepcopy(outcome.result.record)
        lane = mutated["measurement"]["lanes"][0]
        lane["content"]["statistics"]["deterministic_seconds"] += 1000.0
        lane["separator"]["statistics"]["deterministic_seconds"] += 1000.0
        self.assertEqual(
            outcome.result.record["core_facts_sha256"],
            core_facts_sha256(mutated),
        )

    def test_comparator_checks_only_outward_source_containment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                _full_135_pixels(),
                "135",
            )
        assert isinstance(outcome, CompletedInput)
        report = outcome.result.record
        boxes = report["output"]["finalization"]["final_boxes"]
        baseline = {
            "baseline_schema": "x5crop_user_confirmed_golden_baseline_v1",
            "status": "user_confirmed",
            "sample_id": "synthetic",
            "source_sha256": report["analysis_identity"]["source"][
                "content_sha256"
            ],
            "frames": [
                {
                    "confirmed_integer_boundary_polygon": [
                        [box["left"] + 1, box["top"] + 1],
                        [box["right"] - 1, box["top"] + 1],
                        [box["right"] - 1, box["bottom"] - 1],
                        [box["left"] + 1, box["bottom"] - 1],
                    ]
                }
                for box in boxes
            ],
        }
        comparison = compare_baseline_record_to_report(baseline, report)
        self.assertEqual(comparison["comparison_schema"], COMPARISON_SCHEMA)
        self.assertEqual(comparison["comparison_status"], "compared")
        self.assertTrue(comparison["all_confirmed_content_contained"])
        self.assertNotIn("iou", str(comparison).lower())

    def test_scan_canvas_contradiction_is_review_not_terminal_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.arange(10000, dtype=np.uint8).reshape(100, 100),
                "135",
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

    def test_output_failure_remains_terminal_failed_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch(
                "x5crop.runtime.workflow.write_crops",
                side_effect=OSError("synthetic write failure"),
            ):
                outcome = self._process_pixels(
                    root,
                    _full_135_pixels(),
                    "135",
                )
        self.assertIsInstance(outcome, FailedInput)
        assert isinstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.OUTPUT)
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        self.assertIn("synthetic write failure", outcome.error_message)

    def test_diagnostics_preserves_decision_but_does_not_write_frames(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "diagnostics.tif"
            tifffile.imwrite(source, _full_135_pixels())
            bundle = DetectionConfigurationBundle.for_format_mode(
                "135",
                "full",
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
        self.assertEqual(record["grid_selection"]["output_slot_count"], 6)
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

    def test_input_read_failure_remains_terminal_failed_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch(
                "x5crop.runtime.workflow.read_tiff",
                side_effect=OSError("synthetic read failure"),
            ):
                outcome = self._process_pixels(
                    root,
                    _full_135_pixels(),
                    "135",
                )
        self.assertIsInstance(outcome, FailedInput)
        assert isinstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.IMAGE_READ)
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        self.assertIn("synthetic read failure", outcome.error_message)

    def test_tiff_readback_failure_is_not_converted_to_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch(
                "x5crop.io.tiff.validate_written_tiff",
                side_effect=OSError("synthetic readback failure"),
            ):
                outcome = self._process_pixels(
                    root,
                    _full_135_pixels(),
                    "135",
                )
        self.assertIsInstance(outcome, FailedInput)
        assert isinstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.OUTPUT)
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        self.assertIn("synthetic readback failure", outcome.error_message)

    def test_dual_lane_output_is_lane_then_lane_local_ordinal(self) -> None:
        rng = np.random.default_rng(17)
        pixels = rng.integers(0, 256, size=(200, 732), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                pixels,
                "135-dual",
            )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        record = outcome.result.record
        self.assertEqual(record["decision"]["status"], "approved_auto")
        self.assertEqual(record["grid_selection"]["output_slot_count"], 12)
        self.assertEqual(
            record["grid_selection"]["resolved_output_slots"],
            {"lane_output_slot_counts": [6, 6]},
        )
        self.assertEqual(
            record["grid_selection"]["slot_identities"],
            [
                {
                    "global_output_ordinal": global_ordinal,
                    "lane_id": f"lane:{lane_index}",
                    "lane_ordinal": lane_ordinal,
                }
                for global_ordinal, (lane_index, lane_ordinal) in enumerate(
                    (
                        (lane_index, lane_ordinal)
                        for lane_index in range(2)
                        for lane_ordinal in range(1, 7)
                    ),
                    start=1,
                )
            ],
        )
        boxes = record["output"]["finalization"]["final_boxes"]
        self.assertEqual(len(boxes), 12)
        self.assertTrue(all(box["bottom"] <= 100 for box in boxes[:6]))
        self.assertTrue(all(box["top"] >= 100 for box in boxes[6:]))

    def test_short_120_canvas_capacity_filters_count_after_match(self) -> None:
        rng = np.random.default_rng(23)
        pixels = rng.integers(0, 256, size=(200, 594), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = self._process_pixels(
                root / "partial",
                pixels,
                "120-67",
                "partial",
            )
            full = self._process_pixels(
                root / "full",
                pixels,
                "120-67",
                "full",
            )
        self.assertIsInstance(partial, CompletedInput)
        self.assertIsInstance(full, CompletedInput)
        assert isinstance(partial, CompletedInput)
        assert isinstance(full, CompletedInput)
        self.assertEqual(
            partial.result.record["decision"]["status"],
            "approved_auto",
        )
        self.assertEqual(
            partial.result.record["grid_selection"]["output_slot_count"],
            2,
        )
        self.assertEqual(
            partial.result.record["grid_selection"][
                "selected_scan_canvas_profile_id"
            ],
            "120_wide_188_5",
        )
        self.assertEqual(
            full.result.record["decision"]["status"],
            "needs_review",
        )

    def test_final_detection_rejects_post_decision_box_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                _full_135_pixels(),
                "135",
            )
        assert isinstance(outcome, CompletedInput)
        # The record freezes this fact, and FinalDetection validates count/box
        # cardinality at construction.
        finalization = outcome.result.record["output"]["finalization"]
        self.assertFalse(finalization["post_decision_mutation"])
        self.assertEqual(
            len(finalization["final_boxes"]),
            finalization["output_slot_count"],
        )
        self.assertEqual(
            len(finalization["slot_identities"]),
            finalization["output_slot_count"],
        )


if __name__ == "__main__":
    unittest.main()
