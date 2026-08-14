"""Run the tracked 111-source cohort as non-blocking recognition diagnostics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from x5crop.report.validation import validate_current_report_record

from .cohort_count_authority import validate_count_authority
from .diagnostic_contract import (
    aggregate_work,
    bounded_work,
    peak_temporary_limit_bytes,
)
from .file_identity import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_COHORT_PATH = (
    Path(__file__).with_name("cohorts")
    / "diagnostic_unreviewed.jsonl"
)
COHORT_SCHEMA = "x5crop_diagnostic_unreviewed_cohort_v1"
RECORD_SCHEMA = "x5crop_diagnostic_record_v3"
SUMMARY_SCHEMA = "x5crop_diagnostic_summary_v3"
EXPECTED_RECORD_COUNT = 111
DIAGNOSTIC_SOURCE_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class DiagnosticSource:
    identity: dict[str, Any]
    source_path: Path


def load_diagnostic_sources(
    *,
    verify_source_files: bool = True,
) -> tuple[DiagnosticSource, ...]:
    validate_count_authority()
    rows = tuple(
        json.loads(line)
        for line in DIAGNOSTIC_COHORT_PATH.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    )
    if (
        len(rows) != EXPECTED_RECORD_COUNT
        or tuple(row.get("sort_index") for row in rows)
        != tuple(range(1, EXPECTED_RECORD_COUNT + 1))
        or len({row.get("sample_id") for row in rows}) != len(rows)
    ):
        raise ValueError("diagnostic cohort identity is incomplete")
    project_root = PROJECT_ROOT.resolve()
    sources: list[DiagnosticSource] = []
    for row in rows:
        expected_keys = {
            "cohort_schema",
            "sample_id",
            "sort_index",
            "source_relative_path",
            "source_sha256",
            "format_id",
            "strip_mode",
            "validation_role",
            "count_authority",
            "raw_width_px",
            "raw_height_px",
            "dtype",
            "samples_per_pixel",
            "page_count",
        }
        if row.get("strip_mode") == "partial":
            expected_keys.add("confirmed_slot_count")
        relative = Path(str(row.get("source_relative_path", "")))
        source_path = (PROJECT_ROOT / relative).resolve()
        digest = str(row.get("source_sha256", ""))
        if (
            set(row) != expected_keys
            or row.get("cohort_schema") != COHORT_SCHEMA
            or row.get("validation_role") != "diagnostic_unreviewed"
            or relative.is_absolute()
            or not source_path.is_relative_to(project_root)
            or len(digest) != 64
            or (
                verify_source_files
                and (
                    not source_path.is_file()
                    or sha256_file(source_path) != digest
                )
            )
        ):
            raise ValueError(
                f"diagnostic source identity is invalid: "
                f"{row.get('sample_id')}"
            )
        sources.append(DiagnosticSource(row, source_path))
    return tuple(sources)


def _source_geometry_within_authority(
    report: dict[str, Any],
    *,
    width: int,
    height: int,
) -> bool:
    for lane in report["photo_geometry"]["lanes"]:
        for geometry in lane["safe_crop_envelopes"]:
            footprint = geometry["constrained_source_footprint"]
            if not footprint or not all(
                0.0 <= float(point[0]) <= width - 1
                and 0.0 <= float(point[1]) <= height - 1
                for point in footprint
            ):
                return False
    return True


def _production_command(source: DiagnosticSource, output: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "tools.regression.development_run",
        str(source.source_path),
        "--output",
        str(output),
        "--format",
        str(source.identity["format_id"]),
        "--strip",
        str(source.identity["strip_mode"]),
    ]
    if source.identity["strip_mode"] == "partial":
        command.extend(
            ("--count", str(source.identity["confirmed_slot_count"]))
        )
    return command


def _failure_record(
    source: DiagnosticSource,
    *,
    error_code: str,
    error_message: str,
    failure_stage: str,
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "record_schema": RECORD_SCHEMA,
        "validation_role": "diagnostic_unreviewed",
        "sample_id": source.identity["sample_id"],
        "source_sha256": source.identity["source_sha256"],
        "format_id": source.identity["format_id"],
        "strip_mode": source.identity["strip_mode"],
        "terminal_outcome": "runtime_error",
        "decision_status": None,
        "final_review_reasons": [],
        "candidate_gate": None,
        "scan_canvas_profile_id": None,
        "output_slot_count": None,
        "slot_identities": [],
        "geometry_outcome": None,
        "transform_outcome": None,
        "metrics": metrics,
        "structured_exception": {
            "failure_stage": failure_stage,
            "error_code": error_code,
            "error_message": error_message,
        },
        "engineering_checks": None,
        "recognition_accuracy_verdict": "not_assessed",
        "engineering_contract_passed": False,
    }


def run_diagnostic_source(source: DiagnosticSource) -> dict[str, Any]:
    before = source.source_path.stat()
    with TemporaryDirectory(
        prefix=f"x5crop-diagnostic-{source.identity['sample_id']}-"
    ) as temporary:
        output = Path(temporary) / "x5_crop_output"
        try:
            completed = subprocess.run(
                _production_command(source, output),
                cwd=PROJECT_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=DIAGNOSTIC_SOURCE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            return _failure_record(
                source,
                error_code="TimeoutExpired",
                error_message=str(exc),
                failure_stage="production_cli",
                metrics=None,
            )
        if completed.returncode != 0:
            return _failure_record(
                source,
                error_code="ProductionCliFailed",
                error_message=completed.stdout[-4000:],
                failure_stage="production_cli",
                metrics=None,
            )
        try:
            report_path = output / "x5_crop_report.jsonl"
            reports = tuple(
                json.loads(line)
                for line in report_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            if len(reports) != 1:
                raise ValueError("production output requires one report")
            report = reports[0]
            validate_current_report_record(report)
            after = source.source_path.stat()
            source_identity = report["runtime_identity"]["source"]
            if (
                before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or source_identity["input_ordinal"] != 1
                or source_identity["name"] != source.source_path.name
                or source_identity["size"] != before.st_size
                or source_identity["mtime_ns"] != before.st_mtime_ns
            ):
                raise ValueError("source stat identity changed across production run")
            width = int(source.identity["raw_width_px"])
            height = int(source.identity["raw_height_px"])
            source_pixels = width * height
            canonical_extent = report["measurement"]["source_extent"]
            geometry_authorized = _source_geometry_within_authority(
                report,
                width=int(canonical_extent["width"]),
                height=int(canonical_extent["height"]),
            )
            work_bounded = bounded_work(
                report,
                source_pixels=source_pixels,
            )
            output_files = tuple(report["output"]["output_files"])
            review_copy = report["output"]["review_copy"]
            status = report["decision"]["status"]
            output_contract = (
                all((output / relative).is_file() for relative in output_files)
                and (review_copy is None or (output / review_copy).is_file())
                and (
                    (status == "approved_auto" and bool(output_files))
                    or (status == "needs_review" and not output_files)
                )
            )
            metrics = aggregate_work(
                tuple(
                    lane["work"]
                    for lane in report["development"]["lanes"]
                )
            )
            engineering_passed = (
                geometry_authorized and work_bounded and output_contract
            )
            engineering_checks = {
                "source_lane_authority_bounded": geometry_authorized,
                "query_template_memory_bounded": work_bounded,
                "production_output_contract": output_contract,
                "peak_temporary_limit_bytes": (
                    peak_temporary_limit_bytes(source_pixels)
                ),
                "peak_temporary_bound": (
                    "10_bytes_per_source_pixel_plus_32_mib_per_input"
                ),
            }
        except Exception as exc:
            return _failure_record(
                source,
                error_code=type(exc).__name__,
                error_message=str(exc),
                failure_stage="diagnostic_validation",
                metrics=None,
            )
    decision = report["decision"]
    geometry = report["photo_geometry"]
    return {
        "record_schema": RECORD_SCHEMA,
        "validation_role": "diagnostic_unreviewed",
        "sample_id": source.identity["sample_id"],
        "source_sha256": source.identity["source_sha256"],
        "format_id": source.identity["format_id"],
        "strip_mode": source.identity["strip_mode"],
        "terminal_outcome": "completed",
        "decision_status": decision["status"],
        "final_review_reasons": list(
            decision["final_review_reasons"]
        ),
        "candidate_gate": report["candidate_gate"],
        "scan_canvas_profile_id": geometry[
            "selected_scan_canvas_profile_id"
        ],
        "output_slot_count": geometry["output_slot_count"],
        "slot_identities": geometry["slot_identities"],
        "geometry_outcome": {
            "selected_placement_ids": [
                lane["selected_placement_id"]
                for lane in geometry["lanes"]
            ],
        },
        "transform_outcome": {
            "source": report["output"]["finalization"][
                "source_transform_assessment"
            ],
            "lanes": geometry["lane_transform_assessments"],
            "output_transforms": report["output"]["finalization"][
                "output_transforms"
            ],
        },
        "metrics": metrics,
        "structured_exception": None,
        "engineering_checks": engineering_checks,
        "recognition_accuracy_verdict": "not_assessed",
        "engineering_contract_passed": engineering_passed,
    }


def run_diagnostic_cohort(
    output_root: Path,
) -> tuple[bool, dict[str, Any]]:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(
            f"diagnostic output root must be empty: {output_root}"
        )
    sources = load_diagnostic_sources()
    output_root.mkdir(parents=True, exist_ok=True)
    records = tuple(map(run_diagnostic_source, sources))
    records_path = output_root / "diagnostic_records.jsonl"
    records_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    terminal = len(records) == EXPECTED_RECORD_COUNT and all(
        record["terminal_outcome"] in {"completed", "runtime_error"}
        for record in records
    )
    engineering_passed = terminal and all(
        record["engineering_contract_passed"]
        for record in records
    )
    summary = {
        "summary_schema": SUMMARY_SCHEMA,
        "validation_role": "diagnostic_unreviewed",
        "source_count": len(sources),
        "terminal_record_count": len(records),
        "diagnostic_run_completed": terminal,
        "engineering_contract_failure_count": sum(
            not record["engineering_contract_passed"]
            for record in records
        ),
        "engineering_failure_counts": {
            "runtime_error": sum(
                record["terminal_outcome"] == "runtime_error"
                for record in records
            ),
            "source_lane_authority": sum(
                record["engineering_checks"] is not None
                and not record["engineering_checks"][
                    "source_lane_authority_bounded"
                ]
                for record in records
            ),
            "query_template_memory": sum(
                record["engineering_checks"] is not None
                and not record["engineering_checks"][
                    "query_template_memory_bounded"
                ]
                for record in records
            ),
            "production_output_contract": sum(
                record["engineering_checks"] is not None
                and not record["engineering_checks"][
                    "production_output_contract"
                ]
                for record in records
            ),
        },
        "approved_auto_count": sum(
            record["decision_status"] == "approved_auto"
            for record in records
        ),
        "needs_review_count": sum(
            record["decision_status"] == "needs_review"
            for record in records
        ),
        "recognition_accuracy_verdict": "not_assessed",
        "filename_status_expectations_consumed": False,
        "filename_count_annotations_consumed": False,
        "engineering_contract_passed": engineering_passed,
    }
    (output_root / "diagnostic_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return engineering_passed, summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the non-blocking 111-source diagnostic cohort"
    )
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    if args.output_root is None:
        with TemporaryDirectory(prefix="x5crop-diagnostic-results-") as temporary:
            passed, summary = run_diagnostic_cohort(
                Path(temporary),
            )
    else:
        passed, summary = run_diagnostic_cohort(
            args.output_root.expanduser().resolve(),
        )
    print(
        f"diagnostic terminal records: "
        f"{summary['terminal_record_count']}/"
        f"{summary['source_count']}"
    )
    print(
        "recognition accuracy verdict: "
        f"{summary['recognition_accuracy_verdict']}"
    )
    print(
        "engineering contracts: "
        f"{'passed' if summary['engineering_contract_passed'] else 'failed'}; "
        f"failures={summary['engineering_contract_failure_count']}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
