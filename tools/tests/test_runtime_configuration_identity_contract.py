from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.architecture_contracts import PROJECT_ROOT
from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.run_config import RunConfig
from x5crop.runtime.app import run_runtime
from x5crop.runtime.invocation import RuntimeInvocation
from x5crop.runtime.outcome import CompletedInput, RuntimeArtifacts, RuntimeMetrics


def _config() -> RunConfig:
    return RunConfig(
        input_path=Path("input.tif"),
        output_dir=None,
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


class RuntimeConfigurationIdentityContractTest(unittest.TestCase):
    def test_workflow_has_no_selection_owned_configuration_alias(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/workflow.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("selected_configuration", source)

    def test_runtime_passes_one_canonical_config_to_workflow(self) -> None:
        config = _config()
        invocation = RuntimeInvocation(
            config,
            (Path("input.tif"),),
            DetectionConfigurationBundle.for_format_mode("135", "full"),
        )
        result = CompletedInput(
            result=SimpleNamespace(
                record={
                    "decision": {"status": "approved_auto"},
                    "output": {"warnings": [], "output_files": []},
                }
            ),
            artifacts=RuntimeArtifacts.empty(),
            metrics=RuntimeMetrics(1.0, 0.5, 2, 10, 1, 2),
        )
        with (
            patch("x5crop.runtime.app.process_one", return_value=result) as process,
            patch(
                "x5crop.runtime.app.write_report_outputs_for_result",
                return_value=True,
            ),
            patch("x5crop.runtime.app.append_run_manifest"),
            patch("builtins.print"),
        ):
            self.assertEqual(run_runtime(invocation), 0)

        self.assertIs(process.call_args.args[1], config)


if __name__ == "__main__":
    unittest.main()
