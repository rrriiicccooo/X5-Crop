from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import (
    detection_workspace_fixture,
    final_detection_fixture,
)
from tools.tests.physical_gate_support import (
    decide_candidate,
    frame_bleed_fixture,
    selection_fixture,
)
from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.registry import get_detection_configuration
from x5crop.debug.status import debug_status_parts
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.run_config import RunConfig
from x5crop.run_status import RunTerminalOutcome
from x5crop.runtime.app import run_runtime
from x5crop.runtime.invocation import RuntimeInvocation
from x5crop.runtime.manifest import (
    RunManifestRecord,
    append_run_manifest,
)
from x5crop.runtime.outcome import (
    CompletedInput,
    FailedInput,
    FailureStage,
    RuntimeArtifacts,
    RuntimeMetrics,
)
from x5crop.runtime.workflow import process_one


def _config(*, output_dir: Path) -> RunConfig:
    return RunConfig(
        input_path=Path("input.tif"),
        output_dir=output_dir,
        format_id="135",
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        requested_count=None,
        page=0,
        bleed_x=20,
        bleed_y=10,
        review_dir=None,
        copy_review_files=False,
        export_review=False,
        compression="same",
        debug=False,
        debug_analysis=False,
        dry_run=True,
        diagnostics=False,
        overwrite=False,
        report=True,
        debug_errors=False,
        jobs=1,
    )


def _profile() -> ImageProfile:
    return ImageProfile(
        shape=(100, 200),
        dtype="uint8",
        axes="YX",
        photometric="MINISBLACK",
        compression="NONE",
        sample_format=None,
        bits_per_sample=8,
        samples_per_pixel=1,
        planar_config=None,
        resolution=None,
        resolution_unit=None,
        icc_profile=None,
        metadata=TiffMetadata(None, None, None, ()),
    )


def _metrics() -> RuntimeMetrics:
    return RuntimeMetrics(1.0, 0.5, 3, 21, 4, 6)


class RuntimeManifestContractTest(unittest.TestCase):
    def test_outcomes_own_one_typed_runtime_artifact_record(self) -> None:
        self.assertEqual(
            set(RuntimeArtifacts.__dataclass_fields__),
            {"frame_outputs", "review_copy", "debug_analysis"},
        )
        self.assertIn("artifacts", CompletedInput.__dataclass_fields__)
        self.assertIn("artifacts", FailedInput.__dataclass_fields__)
        self.assertNotIn("output_files", FailedInput.__dataclass_fields__)
        self.assertNotIn("debug_analysis", FailedInput.__dataclass_fields__)

    def test_parent_manifest_never_reverse_reads_report_artifacts(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "x5crop/runtime/app.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('result.record["output"]["output_files"]', source)

    def test_manifest_owns_runtime_performance_metrics(self) -> None:
        self.assertIn("metrics", RunManifestRecord.__dataclass_fields__)

    def test_completed_manifest_requires_complete_runtime_metrics(self) -> None:
        with self.assertRaises(ValueError):
            RunManifestRecord(
                source="input.tif",
                terminal_outcome=RunTerminalOutcome.COMPLETED,
                failure_stage=None,
                error_code=None,
                error_message=None,
                report_written=True,
                artifacts=RuntimeArtifacts.empty(),
                metrics=RuntimeMetrics.unavailable(),
            )

    def test_detection_duration_cannot_exceed_input_processing_duration(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeMetrics(0.5, 1.0, 1, 1, 0, 0)

    def test_manifest_has_one_canonical_terminal_record_shape(self) -> None:
        record = RunManifestRecord(
            source="input.tif",
            terminal_outcome=RunTerminalOutcome.RUNTIME_ERROR,
            failure_stage=FailureStage.DETECTION,
            error_code="ValueError",
            error_message="measurement failed",
            report_written=False,
            artifacts=RuntimeArtifacts.empty(),
            metrics=_metrics(),
        )

        self.assertEqual(
            record.as_record(),
            {
                "source": "input.tif",
                "terminal_outcome": "runtime_error",
                "failure_stage": "detection",
                "error_code": "ValueError",
                "error_message": "measurement failed",
                "report_written": False,
                "artifacts": {
                    "frame_outputs": [],
                    "review_copy": None,
                    "debug_analysis": None,
                },
                "metrics": {
                    "processing_seconds": 1.0,
                    "detection_seconds": 0.5,
                    "assessed_candidates": 3,
                    "assignment_evaluations": 21,
                    "measurement_cache_hits": 4,
                    "measurement_cache_misses": 6,
                },
            },
        )

    def test_parent_app_writes_exactly_one_manifest_record_per_input(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = _config(output_dir=output_dir)
            source = Path("input.tif")
            invocation = RuntimeInvocation(
                config,
                (source,),
                DetectionConfigurationBundle.for_format_mode("135", "full"),
            )
            result = SimpleNamespace(
                record={
                    "decision": {"status": "approved_auto"},
                    "output": {"warnings": [], "output_files": ["frame.tif"]},
                }
            )
            completed = CompletedInput(
                result=result,
                artifacts=RuntimeArtifacts(("frame.tif",), None, "debug.jpg"),
                metrics=_metrics(),
            )
            with (
                patch("x5crop.runtime.app.process_one", return_value=completed),
                patch(
                    "x5crop.runtime.app.write_report_outputs_for_result",
                    return_value=True,
                ),
                patch("x5crop.runtime.app.append_run_manifest") as append_manifest,
                patch("builtins.print"),
            ):
                self.assertEqual(run_runtime(invocation), 0)

        append_manifest.assert_called_once()
        manifest = append_manifest.call_args.args[2]
        self.assertEqual(manifest.terminal_outcome, RunTerminalOutcome.COMPLETED)
        self.assertTrue(manifest.report_written)
        self.assertEqual(manifest.artifacts.frame_outputs, ("frame.tif",))
        self.assertEqual(manifest.artifacts.debug_analysis, "debug.jpg")
        self.assertEqual(manifest.metrics, _metrics())

    def test_failed_input_still_writes_one_terminal_manifest_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = _config(output_dir=output_dir)
            source = Path("input.tif")
            invocation = RuntimeInvocation(
                config,
                (source,),
                DetectionConfigurationBundle.for_format_mode("135", "full"),
            )
            failed = FailedInput(
                source=source,
                failure_stage=FailureStage.DETECTION,
                error_code="ValueError",
                error_message="measurement failed",
                artifacts=RuntimeArtifacts.empty(),
                traceback_text=None,
                metrics=_metrics(),
            )
            with (
                patch("x5crop.runtime.app.process_one", return_value=failed),
                patch("x5crop.runtime.app.append_run_manifest") as append_manifest,
                patch("builtins.print"),
            ):
                self.assertEqual(run_runtime(invocation), 1)

        append_manifest.assert_called_once()
        manifest = append_manifest.call_args.args[2]
        self.assertEqual(manifest.terminal_outcome, RunTerminalOutcome.RUNTIME_ERROR)
        self.assertEqual(manifest.failure_stage, FailureStage.DETECTION)
        self.assertFalse(manifest.report_written)

    def test_runtime_error_debug_status_does_not_change_decision(self) -> None:
        detection = final_detection_fixture()
        style = get_detection_configuration("135", "full").diagnostics.style

        status, detail, _ = debug_status_parts(
            detection,
            style,
            RunTerminalOutcome.RUNTIME_ERROR,
        )

        self.assertEqual(status, "RUNTIME ERROR")
        self.assertIn("terminal_outcome: runtime_error", detail)
        self.assertEqual(detection.decision.status, "approved_auto")

    def test_manifest_writer_appends_one_json_object_per_call(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = _config(output_dir=output_dir)
            record = RunManifestRecord(
                source="input.tif",
                terminal_outcome=RunTerminalOutcome.COMPLETED,
                failure_stage=None,
                error_code=None,
                error_message=None,
                report_written=True,
                artifacts=RuntimeArtifacts(("frame.tif",), None, None),
                metrics=_metrics(),
            )

            path = append_run_manifest(Path("input.tif"), config, record)
            append_run_manifest(Path("input.tif"), config, record)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), record.as_record())

    def test_report_validation_failure_rewrites_existing_debug_as_runtime_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = _config(output_dir=Path(temp_dir))
            source = Path("input.tif")
            profile = _profile()
            pixels = np.zeros((100, 200), dtype=np.uint8)
            selection = selection_fixture()
            bleed = frame_bleed_fixture()
            final_detection = final_detection_fixture()
            workspace = detection_workspace_fixture(
                width=pixels.shape[1],
                height=pixels.shape[0],
            )
            with (
                patch(
                    "x5crop.runtime.workflow.read_tiff_profile",
                    return_value=(profile, []),
                ),
                patch(
                    "x5crop.runtime.workflow.make_analysis_identity",
                    return_value={},
                ),
                patch(
                    "x5crop.runtime.workflow.read_tiff",
                    return_value=(pixels, profile, []),
                ),
                patch(
                    "x5crop.runtime.workflow.prepare_detection_workspace",
                    return_value=workspace,
                ),
                patch(
                    "x5crop.runtime.workflow.choose_detection",
                    return_value=selection,
                ),
                patch(
                    "x5crop.runtime.workflow.frame_bleed_plan_for_selection",
                    return_value=bleed,
                ),
                patch(
                    "x5crop.runtime.workflow.apply_decision_gate",
                    return_value=decide_candidate(),
                ),
                patch(
                    "x5crop.runtime.workflow.finalization_plan_for_selection",
                    return_value=final_detection.finalization_plan,
                ),
                patch(
                    "x5crop.runtime.workflow.finalize_detection",
                    return_value=final_detection,
                ),
                patch(
                    "x5crop.runtime.workflow.copy_for_review_if_needed",
                    return_value="review/input.tif",
                ),
                patch(
                    "x5crop.runtime.workflow.write_crops_if_allowed",
                    return_value=["output/frame.tif"],
                ),
                patch(
                    "x5crop.runtime.workflow.write_debug_outputs",
                    side_effect=("debug.jpg", "debug.jpg"),
                ) as write_debug,
                patch(
                    "x5crop.runtime.workflow.result_from_detection",
                    side_effect=ValueError("invalid report"),
                ),
            ):
                outcome = process_one(
                    source,
                    config,
                    DetectionConfigurationBundle.for_format_mode("135", "full"),
                )

        self.assertIsInstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.REPORT_VALIDATION)
        self.assertEqual(outcome.artifacts.debug_analysis, "debug.jpg")
        self.assertEqual(outcome.artifacts.review_copy, "review/input.tif")
        self.assertEqual(outcome.artifacts.frame_outputs, ("output/frame.tif",))
        self.assertEqual(write_debug.call_count, 2)
        self.assertEqual(
            write_debug.call_args_list[0].args[-1],
            RunTerminalOutcome.COMPLETED,
        )
        self.assertEqual(
            write_debug.call_args_list[1].args[-1],
            RunTerminalOutcome.RUNTIME_ERROR,
        )

    def test_failure_before_final_detection_does_not_fabricate_debug(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = _config(output_dir=Path(temp_dir))
            with (
                patch(
                    "x5crop.runtime.workflow.read_tiff_profile",
                    side_effect=ValueError("profile failed"),
                ),
                patch("x5crop.runtime.workflow.write_debug_outputs") as write_debug,
            ):
                outcome = process_one(
                    Path("input.tif"),
                    config,
                    DetectionConfigurationBundle.for_format_mode("135", "full"),
                )

        self.assertIsInstance(outcome, FailedInput)
        self.assertEqual(outcome.failure_stage, FailureStage.INPUT_PROFILE)
        self.assertIsNone(outcome.artifacts.debug_analysis)
        write_debug.assert_not_called()


if __name__ == "__main__":
    unittest.main()
