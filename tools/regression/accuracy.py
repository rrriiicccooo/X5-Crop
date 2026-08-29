"""Run the source-bound V5 golden comparator around the production CLI."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Iterable, Sequence

from tools.manual_annotation.model import (
    BASELINE_SCHEMA,
    EVALUATION_ROLE_CONTRACT,
    AnnotationError,
    canonical_record_sha256,
    evaluation_task_role,
)

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
GOLD_COHORT_SCHEMA = "x5crop_gold_accuracy_cohort_v7"
GOLD_COMPLETION_SCOPE = "all_current_user_confirmed_tasks_exactly_once"
CONFIRMED_GEOMETRY_KEYS = frozenset(
    {
        "baseline_schema",
        "sample_id",
        "status",
        "authority",
        "confirmation_scope",
        "accuracy_scope",
        "confirmed_at_utc",
        "proposal_snapshot_sha256",
        "source_relative_path",
        "source_sha256",
        "format_id",
        "count",
        "coordinate_system",
        "strip_orientation",
        "shared_edges",
        "boundary_pool",
        "slots",
        "adjacencies",
        "evaluation_role",
        "frames",
        "confirmed_review_artifact",
        "confirmed_review_artifact_sha256",
    }
)


def validate_gold_evaluation_role(record: dict[str, object]) -> None:
    """Reject a cohort role that disagrees with its frozen human evidence."""
    sample_id = str(record.get("sample_id", ""))
    geometry = record.get("confirmed_geometry")
    if not isinstance(geometry, dict):
        raise ValueError(f"gold evaluation role is invalid: {sample_id}")
    task = {
        "task_id": sample_id,
        "sample_id": sample_id,
        "count": geometry.get("count"),
        "slots": geometry.get("slots"),
        "adjacencies": geometry.get("adjacencies"),
    }
    coordinate_system = geometry.get("coordinate_system")
    if not isinstance(coordinate_system, dict):
        raise ValueError(f"gold evaluation role is invalid: {sample_id}")
    try:
        derived = evaluation_task_role(
            format_id=str(geometry["format_id"]),
            strip_axis_display=str(geometry["strip_orientation"]),
            source_canonical_extent=coordinate_system["canonical_extent"],
            orientation_mapping=coordinate_system["orientation_mapping"],
            shared_edges=geometry["shared_edges"],
            boundary_pool=geometry["boundary_pool"],
            task=task,
        )
    except (AnnotationError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"gold evaluation role is invalid: {sample_id}") from error
    expected = {
        "contract": EVALUATION_ROLE_CONTRACT,
        "cohort_role": derived["cohort_role"],
        "reasons": derived["reasons"],
    }
    if (
        geometry.get("evaluation_role") != expected
        or record.get("cohort_role") != derived["cohort_role"]
    ):
        raise ValueError(f"gold evaluation role is invalid: {sample_id}")


def validate_gold_source_identities() -> tuple[dict[str, object], ...]:
    validate_cohort_counts()
    records = tuple(
        json.loads(line)
        for line in GOLD_COHORT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if not records:
        raise ValueError(
            "gold accuracy calibration is incomplete: no current user-confirmed sources"
        )
    project_root = PROJECT_ROOT.resolve()
    sample_ids: set[str] = set()
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
        }
        sample_id = str(record.get("sample_id", ""))
        relative = Path(str(record.get("source_relative_path", "")))
        source = (PROJECT_ROOT / relative).resolve()
        expected_sha = str(record.get("source_sha256", "")).lower()
        count = record.get("count")
        if (
            set(record) != expected_keys
            or record.get("cohort_schema") != GOLD_COHORT_SCHEMA
            or record.get("completion_scope") != GOLD_COMPLETION_SCOPE
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
        coordinate_system = (
            geometry.get("coordinate_system")
            if isinstance(geometry, dict)
            else None
        )
        if (
            not isinstance(geometry, dict)
            or set(geometry) != CONFIRMED_GEOMETRY_KEYS
            or geometry.get("baseline_schema") != BASELINE_SCHEMA
            or geometry.get("status") != "user_confirmed"
            or geometry.get("sample_id") != sample_id
            or geometry.get("source_relative_path") != relative.as_posix()
            or geometry.get("source_sha256") != expected_sha
            or geometry.get("format_id") != record.get("format_id")
            or geometry.get("count") != count
            or geometry.get("accuracy_scope")
            != "slots_with_boundary_pair_reference_geometry"
            or record.get("acceptance_baseline_schema")
            != BASELINE_SCHEMA
            or canonical_record_sha256(geometry)
            != record.get("geometry_digest")
            or not isinstance(geometry.get("slots"), list)
            or len(geometry["slots"]) != count
            or not isinstance(geometry.get("frames"), list)
            or not isinstance(coordinate_system, dict)
            or set(coordinate_system) != {
                "origin",
                "x_direction",
                "y_direction",
                "continuous_coordinates",
                "canonical_extent",
                "orientation_mapping",
            }
        ):
            raise ValueError(f"gold geometry is invalid: {sample_id}")
        validate_gold_evaluation_role(record)
        sample_ids.add(sample_id)
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


def validate_gold_task_result(
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
        return validate_gold_task_result(record, report)


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
    try:
        records = validate_gold_source_identities()
        passed, approved = run_accuracy(records)
    except ValueError as error:
        print(f"gold accuracy: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        f"gold accuracy: {passed}/{len(records)} safe; "
        f"approved={approved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
