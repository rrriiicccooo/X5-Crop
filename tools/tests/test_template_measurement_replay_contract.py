from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

from tools.regression.template_measurement_replay import (
    REPLAY_SCHEMA,
    TemplateMeasurementReplay,
    dump_file,
    dump_jsonl,
    load_file,
    load_jsonl,
)
from tools.tests.template_runtime_test_support import (
    prepared_template_lane as _prepared,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA256 = "a" * 64


class TemplateMeasurementReplayContractTest(unittest.TestCase):
    def test_round_trip_preserves_exact_solver_inputs_and_answers(self) -> None:
        prepared = _prepared()
        replay = TemplateMeasurementReplay.capture(
            prepared,
            source_sha256=SOURCE_SHA256,
        )
        payload = dump_jsonl((replay,))
        restored = load_jsonl(
            payload,
            expected_source_sha256=SOURCE_SHA256,
            expected_plan_identity=prepared.measurement_plan.plan_identity,
        )

        self.assertEqual(restored, (replay,))
        phase, cross = restored[0].rerun()
        self.assertEqual(phase, prepared.phase_competition)
        self.assertEqual(cross, prepared.cross_competition)
        self.assertEqual(json.loads(payload)["schema"], REPLAY_SCHEMA)

    def test_file_helpers_are_stable_jsonl(self) -> None:
        replay = TemplateMeasurementReplay.capture(
            _prepared(),
            source_sha256=SOURCE_SHA256,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "measurement.jsonl"
            dump_file(path, (replay,))
            first = path.read_bytes()
            dump_file(path, load_file(path))
            self.assertEqual(path.read_bytes(), first)

    def test_identity_mismatch_is_a_hard_failure(self) -> None:
        replay = TemplateMeasurementReplay.capture(
            _prepared(),
            source_sha256=SOURCE_SHA256,
        )
        payload = dump_jsonl((replay,))
        with self.assertRaisesRegex(ValueError, "source identity mismatch"):
            load_jsonl(payload, expected_source_sha256="b" * 64)
        with self.assertRaisesRegex(ValueError, "plan identity mismatch"):
            load_jsonl(payload, expected_plan_identity="another-plan")

    def test_truth_and_unknown_schema_fields_are_forbidden(self) -> None:
        replay = TemplateMeasurementReplay.capture(
            _prepared(),
            source_sha256=SOURCE_SHA256,
        )
        record = json.loads(dump_jsonl((replay,)))
        record["gold_geometry"] = {"frames": []}
        with self.assertRaisesRegex(ValueError, "truth or accuracy"):
            load_jsonl(json.dumps(record))

    def test_production_never_imports_developer_replay(self) -> None:
        for path in (ROOT / "x5crop").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imported.update(
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            )
            self.assertNotIn("tools.regression.template_measurement_replay", imported)


if __name__ == "__main__":
    unittest.main()
