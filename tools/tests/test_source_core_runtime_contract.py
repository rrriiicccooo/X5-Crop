from __future__ import annotations

from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from tools.regression.golden_baseline import (
    COMPARISON_SCHEMA,
    compare_baseline_record_to_report,
)
from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.detection.decision.vocabulary import (
    FINAL_REASON_FRAME_GRID_AUTHORITY_UNAVAILABLE,
    FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
    FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_UNAVAILABLE,
)
from x5crop.report.identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    core_facts_sha256,
)
from x5crop.run_config import RunConfig
from x5crop.runtime.outcome import CompletedInput
from x5crop.runtime.workflow import process_one


def _run_config(source: Path, output: Path, format_id: str = "135") -> RunConfig:
    return RunConfig(
        input_path=source,
        output_dir=output,
        format_id=format_id,
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        requested_count=None,
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


class SourceCoreRuntimeContractTest(unittest.TestCase):
    def _process(self, root: Path) -> CompletedInput:
        source = root / "source.tif"
        rng = np.random.default_rng(9)
        pixels = rng.integers(0, 256, size=(100, 720), dtype=np.uint8)
        tifffile.imwrite(source, pixels, photometric="minisblack")
        outcome = process_one(
            source,
            _run_config(source, root / "output"),
            DetectionConfigurationBundle.for_format_mode("135", "full"),
        )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        return outcome

    def _process_pixels(
        self,
        root: Path,
        pixels: np.ndarray,
        format_id: str,
    ) -> CompletedInput:
        source = root / f"{format_id}.tif"
        tifffile.imwrite(source, pixels, photometric="minisblack")
        outcome = process_one(
            source,
            _run_config(source, root / "output", format_id),
            DetectionConfigurationBundle.for_format_mode(format_id, "full"),
        )
        self.assertIsInstance(outcome, CompletedInput)
        assert isinstance(outcome, CompletedInput)
        return outcome

    def test_grid_unavailable_is_owned_by_decision_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process(Path(temporary))
        record = outcome.result.record

        self.assertEqual(record["schema_id"], REPORT_SCHEMA_ID)
        self.assertEqual(record["schema_revision"], REPORT_SCHEMA_REVISION)
        self.assertEqual(record["decision"]["status"], "needs_review")
        self.assertEqual(
            record["decision"]["final_review_reasons"],
            [FINAL_REASON_FRAME_GRID_AUTHORITY_UNAVAILABLE],
        )
        self.assertTrue(
            all(
                check["final_review_reason"] is None
                for check in record["candidate_gate"]["checks"]
            )
        )
        self.assertEqual(
            record["source_core"]["frame_grid"]["outcome"],
            "no_independent_phase_authority",
        )
        self.assertEqual(
            record["source_core"]["photo_containment"]["outcome"],
            "not_applicable_frame_grid_unavailable",
        )
        self.assertEqual(
            record["source_core"]["visual_deskew_outcome"],
            "not_applicable_core_unavailable",
        )
        self.assertFalse(record["output"]["finalization"]["frame_export_eligible"])
        self.assertEqual(record["output"]["finalization"]["final_boxes"], [])
        self.assertEqual(record["output"]["output_files"], [])
        self.assertEqual(outcome.artifacts.frame_outputs, ())
        content = record["source_core"]["lanes"][0]["content"]
        self.assertLessEqual(len(content["component_examples"]), 64)
        self.assertEqual(
            content["component_examples_truncated"],
            content["component_count"] > 64,
        )
        for component in content["component_examples"]:
            self.assertNotIn("intensity_active_cells", component)
            self.assertNotIn("texture_active_cells", component)
            self.assertGreater(component["positive_cells"], 0)

    def test_core_hash_excludes_measurement_wall_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process(Path(temporary))
        mutated = deepcopy(outcome.result.record)
        mutated["source_core"]["lanes"][0]["content"]["statistics"][
            "deterministic_seconds"
        ] += 1000.0
        self.assertEqual(
            outcome.result.record["core_facts_sha256"],
            core_facts_sha256(mutated),
        )

    def test_comparator_is_post_detection_unavailable_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process(Path(temporary))
        report = outcome.result.record
        source_sha = report["analysis_identity"]["source"]["content_sha256"]
        comparison = compare_baseline_record_to_report(
            {
                "baseline_schema": "x5crop_user_confirmed_golden_baseline_v1",
                "status": "user_confirmed",
                "sample_id": "synthetic",
                "source_sha256": source_sha,
            },
            report,
        )
        self.assertEqual(comparison["comparison_schema"], COMPARISON_SCHEMA)
        self.assertEqual(
            comparison["comparison_status"],
            "production_geometry_unavailable",
        )
        self.assertEqual(comparison["edge_metrics"], [])
        self.assertNotIn("resolved-safe", str(comparison))

    def test_scan_canvas_failure_adds_independent_typed_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                np.arange(10000, dtype=np.uint8).reshape(100, 100),
                "135",
            )
        self.assertEqual(
            outcome.result.record["decision"]["final_review_reasons"],
            [
                FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
                FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_UNAVAILABLE,
                FINAL_REASON_FRAME_GRID_AUTHORITY_UNAVAILABLE,
            ],
        )

    def test_dual_lane_uses_exact_center_domains_and_remains_review(self) -> None:
        rng = np.random.default_rng(17)
        pixels = rng.integers(0, 256, size=(200, 720), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as temporary:
            outcome = self._process_pixels(
                Path(temporary),
                pixels,
                "135-dual",
            )
        record = outcome.result.record
        lanes = record["source_core"]["lanes"]
        self.assertEqual(len(lanes), 2)
        self.assertEqual(
            [lane["domain"]["work_box"] for lane in lanes],
            [
                {"left": 0, "top": 0, "right": 720, "bottom": 100},
                {"left": 0, "top": 100, "right": 720, "bottom": 200},
            ],
        )
        self.assertEqual(record["decision"]["status"], "needs_review")
        self.assertEqual(record["output"]["output_files"], [])


if __name__ == "__main__":
    unittest.main()
