"""Run the source-bound V5 golden comparator around the production CLI."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Iterable, Sequence

from .report_validation import validate_current_report_record

from .cohort_count import validate_cohort_counts
from .file_identity import sha256_file
from .gold_geometry import (
    GOLD_ACCEPTANCE_CONTRACT,
    validate_approved_geometry,
    validate_selected_candidate_coverage,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_COHORT_PATH = Path(__file__).with_name("cohorts") / "gold_accuracy.jsonl"
EXPECTED_SOURCE_COUNT = 9
EXPECTED_TASK_COUNT = 9


def validate_gold_source_identities() -> tuple[dict[str, object], ...]:
    validate_cohort_counts()
    records = tuple(
        json.loads(line)
        for line in GOLD_COHORT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if len(records) != EXPECTED_SOURCE_COUNT:
        raise ValueError("gold accuracy cohort must contain exactly nine sources")
    project_root = PROJECT_ROOT.resolve()
    sample_ids: set[str] = set()
    task_count = 0
    for record in records:
        expected_keys = {
            "cohort_schema",
            "completion_scope",
            "sample_id",
            "source_relative_path",
            "source_sha256",
            "format_id",
            "count",
            "validation_role",
            "cohort_role",
            "acceptance_contract",
            "acceptance_baseline_schema",
            "geometry_digest",
            "confirmed_geometry",
            "confirmed_geometry_slot_count",
        }
        sample_id = str(record.get("sample_id", ""))
        relative = Path(str(record.get("source_relative_path", "")))
        source = (PROJECT_ROOT / relative).resolve()
        expected_sha = str(record.get("source_sha256", "")).lower()
        count = record.get("count")
        if (
            set(record) != expected_keys
            or record.get("cohort_schema") != "x5crop_gold_accuracy_cohort_v5"
            or not sample_id
            or sample_id in sample_ids
            or record.get("validation_role") != "gold_accuracy_blocking"
            or record.get("cohort_role") not in {"nominal", "challenge"}
            or record.get("acceptance_contract")
            != GOLD_ACCEPTANCE_CONTRACT
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
            or relative.is_absolute()
            or not source.is_relative_to(project_root)
            or not source.is_file()
            or len(expected_sha) != 64
            or sha256_file(source) != expected_sha
        ):
            raise ValueError(f"gold source identity is invalid: {sample_id or relative}")
        geometry = record.get("confirmed_geometry")
        if (
            not isinstance(geometry, dict)
            or geometry.get("status") != "user_confirmed"
            or geometry.get("source_sha256") != expected_sha
            or record.get("acceptance_baseline_schema")
            != geometry.get("baseline_schema")
            or len(geometry.get("frames", ()))
            != int(record.get("confirmed_geometry_slot_count", 0))
        ):
            raise ValueError(f"gold geometry is invalid: {sample_id}")
        sample_ids.add(sample_id)
        task_count += 1
    if task_count != EXPECTED_TASK_COUNT:
        raise ValueError("gold accuracy cohort must contain exactly nine tasks")
    return records


def _production_command(
    source: Path,
    output: Path,
    record: dict[str, object],
) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "X5_Crop.py"),
        str(source),
        "--output",
        str(output),
        "--format",
        str(record["format_id"]),
        "--count",
        str(record["count"]),
        "--jobs",
        "1",
    ]
    return command


def _validate_task_result(
    record: dict[str, object],
    report: dict[str, object],
) -> str:
    validate_selected_candidate_coverage(record, report)
    status = str(report["decision"]["status"])
    role = str(record["cohort_role"])
    if role == "nominal" and status != "approved_auto":
        raise ValueError(f"{record['sample_id']} nominal task is {status}")
    if role == "challenge" and status not in {
        "approved_auto",
        "needs_review",
    }:
        raise ValueError(f"{record['sample_id']} challenge task is {status}")
    if status == "approved_auto":
        validate_approved_geometry(record, report)
    return status


def _run_task(record: dict[str, object]) -> str:
    source = (PROJECT_ROOT / str(record["source_relative_path"])).resolve()
    before = source.stat()
    with TemporaryDirectory(prefix="x5crop-accuracy-") as temporary:
        output = Path(temporary) / "x5_crop_output"
        completed = subprocess.run(
            _production_command(source, output, record),
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"{record['sample_id']} production CLI failed:\n"
                + completed.stdout[-4000:]
            )
        report_path = output / "x5_crop_report.jsonl"
        rows = tuple(
            json.loads(line)
            for line in report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if len(rows) != 1:
            raise ValueError("accuracy task must produce exactly one terminal report")
        report = rows[0]
        validate_current_report_record(report)
        identity = report["runtime_identity"]["source"]
        after = source.stat()
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or identity["input_ordinal"] != 1
            or identity["name"] != source.name
            or identity["size"] != before.st_size
            or identity["mtime_ns"] != before.st_mtime_ns
        ):
            raise ValueError("source stat identity changed across accuracy task")
        return _validate_task_result(record, report)


def run_accuracy(records: Iterable[dict[str, object]]) -> tuple[int, int]:
    passed = 0
    approved = 0
    failures: list[str] = []
    for record in records:
        identity = str(record["sample_id"])
        try:
            status = _run_task(record)
        except Exception as exc:
            failures.append(f"{identity}: {exc}")
            print(f"{identity}: FAIL: {exc}")
            continue
        passed += 1
        approved += status == "approved_auto"
        print(f"{identity}: {status}")
    if failures:
        raise ValueError(
            f"gold accuracy failed {len(failures)} task(s):\n"
            + "\n".join(failures)
        )
    return passed, approved


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise SystemExit("accuracy verifier takes no arguments")
    records = validate_gold_source_identities()
    passed, approved = run_accuracy(records)
    print(
        f"gold accuracy: {passed}/{EXPECTED_TASK_COUNT} safe; "
        f"approved={approved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
