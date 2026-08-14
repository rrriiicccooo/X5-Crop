from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.regression.template_measurement_replay import (
    TemplateMeasurementReplay,
    capture_template_measurement_replay,
    dump_file,
    dump_jsonl,
    load_file,
    load_jsonl,
    rerun_template_fits,
)
from tools.tests.test_template_runtime_model_contract import _prepared


def _replay() -> TemplateMeasurementReplay:
    return TemplateMeasurementReplay(
        source_sha256="a" * 64,
        config_identity={"format_id": "135", "strip_mode": "full"},
        measurement_revision="photo-boundary-r3",
        template_plan_identity={"template_id": "135-full-3", "count": 3},
        fitted_template_spec={"template_id": "135-full-3"},
        registered_query_receipts=({"query_id": "q:1", "pixel_query_count": 2},),
        sequence_edges=({"observation_id": "seq:1", "coordinate_px": 10.0},),
        separator_bands=({"observation_id": "sep:1", "interval_px": [20.0, 22.0]},),
        cross_bindings=({"observation_id": "cross:top", "role": "top"},),
        content_occupancy_summary=({"lane_id": "lane:0", "occupied_cell_count": 4},),
    )


class TemplateMeasurementReplayContractTest(unittest.TestCase):
    def test_roundtrip_and_stable_bytes(self) -> None:
        replay = _replay()
        encoded = dump_jsonl(replay)
        self.assertEqual(encoded, dump_jsonl(load_jsonl(encoded)))
        self.assertEqual(encoded, dump_jsonl(load_jsonl(encoded.encode("utf-8").decode("utf-8"))))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "measurements.jsonl"
            dump_file(replay, path)
            self.assertEqual(replay, load_file(path))

    def test_identity_and_revision_mismatch_rejected(self) -> None:
        encoded = dump_jsonl(_replay())
        with self.assertRaises(ValueError):
            load_jsonl(encoded, source_sha256="b" * 64)
        with self.assertRaises(ValueError):
            load_jsonl(encoded, config_identity={"format_id": "120"})
        with self.assertRaises(ValueError):
            load_jsonl(encoded, measurement_revision="photo-boundary-r4")
        with self.assertRaises(ValueError):
            load_jsonl(encoded, template_plan_identity={"template_id": "other"})

    def test_no_accuracy_or_reference_authority(self) -> None:
        replay = _replay()
        with self.assertRaises(ValueError):
            TemplateMeasurementReplay(
                source_sha256=replay.source_sha256,
                config_identity={"reference": "bad"},
                measurement_revision=replay.measurement_revision,
                template_plan_identity=replay.template_plan_identity,
                fitted_template_spec=replay.fitted_template_spec,
                registered_query_receipts=(),
                sequence_edges=(),
                separator_bands=(),
                cross_bindings=(),
                content_occupancy_summary=(),
            )

    def test_cli_validate_and_inspect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "measurements.jsonl"
            dump_file(_replay(), path)
            command = [sys.executable, "-m", "tools.regression.template_measurement_replay"]
            valid = subprocess.run(command + ["validate", str(path)], capture_output=True, text=True, check=True)
            self.assertEqual(valid.stdout.strip(), "valid")
            inspected = subprocess.run(command + ["inspect", str(path)], capture_output=True, text=True, check=True)
            self.assertIn('"measurement_revision":"photo-boundary-r3"', inspected.stdout)

    def test_production_does_not_import_replay(self) -> None:
        production = Path(__file__).parents[2] / "x5crop"
        for path in production.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            ]
            self.assertFalse(any("template_measurement_replay" in name for name in imports), path)

    def test_captured_registered_facts_rerun_without_pixel_measurement(self) -> None:
        prepared = _prepared()
        replay = capture_template_measurement_replay(
            prepared,
            source_sha256="c" * 64,
            config_identity={
                "format_id": "135",
                "strip_mode": "partial",
                "count": 1,
            },
            measurement_revision="photo-boundary-r3",
        )

        result = rerun_template_fits(replay, prepared.measurement_plan)

        self.assertEqual(
            result.phase.status,
            prepared.phase_competition.status,
        )
        self.assertEqual(
            result.cross.status,
            prepared.cross_competition.status,
        )
        self.assertEqual(replay.registered_query_receipts, ())


if __name__ == "__main__":
    unittest.main()
