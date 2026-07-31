"""Run the tracked 111-source cohort as non-blocking recognition diagnostics."""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

from x5crop.report.validation import validate_current_report_record
from x5crop.runtime.bootstrap import runtime_invocation_from_options
from x5crop.runtime.options import RuntimeOptions
from x5crop.runtime.outcome import CompletedInput, FailedInput
from x5crop.runtime.workflow import process_one


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_COHORT_PATH = (
    Path(__file__).with_name("cohorts")
    / "diagnostic_unreviewed.jsonl"
)
COHORT_SCHEMA = "x5crop_diagnostic_unreviewed_cohort_v1"
RECORD_SCHEMA = "x5crop_diagnostic_record_v1"
SUMMARY_SCHEMA = "x5crop_diagnostic_summary_v1"
EXPECTED_RECORD_COUNT = 111
MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL = 10
MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class DiagnosticSource:
    identity: dict[str, Any]
    source_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_diagnostic_sources() -> tuple[DiagnosticSource, ...]:
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
        relative = Path(str(row.get("source_relative_path", "")))
        source_path = (PROJECT_ROOT / relative).resolve()
        digest = str(row.get("source_sha256", ""))
        if (
            row.get("cohort_schema") != COHORT_SCHEMA
            or row.get("validation_role") != "diagnostic_unreviewed"
            or relative.is_absolute()
            or not source_path.is_relative_to(project_root)
            or not source_path.is_file()
            or len(digest) != 64
            or _sha256(source_path) != digest
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
        for geometry in lane["selection"][
            "candidate_output_geometries"
        ]:
            box = geometry["source_protected_box"]
            if not (
                0.0 <= float(box["left"]) < float(box["right"]) <= width
                and 0.0
                <= float(box["top"])
                < float(box["bottom"])
                <= height
            ):
                return False
        for candidate in lane["selection"][
            "undominated_candidate_set"
        ]:
            for geometry in candidate["output_geometries"]:
                box = geometry["source_protected_box"]
                if not (
                    0.0
                    <= float(box["left"])
                    < float(box["right"])
                    <= width
                    and 0.0
                    <= float(box["top"])
                    < float(box["bottom"])
                    <= height
                ):
                    return False
    return True


def _bounded_work(
    report: dict[str, Any],
    metrics: dict[str, Any],
    *,
    source_pixels: int,
) -> bool:
    output_slot_count = report["photo_geometry"]["output_slot_count"]
    lane_count = max(1, len(report["photo_geometry"]["lanes"]))
    maximum_slots = (
        1
        if not isinstance(output_slot_count, int)
        else output_slot_count
    )
    return (
        all(
            isinstance(metrics[key], (int, float))
            and math.isfinite(float(metrics[key]))
            and float(metrics[key]) >= 0.0
            for key in metrics
        )
        and metrics["dp_states"] <= maximum_slots * 3
        and metrics["dp_transitions"]
        <= max(0, maximum_slots - lane_count) * 9
        and metrics["pixel_query_count"] <= source_pixels * 128
        and metrics["peak_temporary_bytes"]
        <= _peak_temporary_limit_bytes(source_pixels)
    )


def _peak_temporary_limit_bytes(source_pixels: int) -> int:
    if source_pixels <= 0:
        raise ValueError("source memory bound requires positive pixels")
    return (
        source_pixels
        * MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL
        + MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES
    )


def _runtime_options(source: DiagnosticSource) -> RuntimeOptions:
    return RuntimeOptions(
        input_path=source.source_path,
        output_dir=None,
        format_id=str(source.identity["format_id"]),
        layout="auto",
        strip_mode=str(source.identity["strip_mode"]),
        requested_count=None,
        page=0,
        review_dir=None,
        copy_review_files=False,
        compression="same",
        debug_analysis=False,
        diagnostics=True,
        overwrite=False,
        report=False,
        debug_errors=True,
        jobs=1,
    )


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
    try:
        invocation = runtime_invocation_from_options(
            _runtime_options(source)
        )
        outcome = process_one(
            source.source_path,
            invocation.config,
            invocation.configuration_bundle,
        )
    except Exception as exc:
        return _failure_record(
            source,
            error_code=type(exc).__name__,
            error_message=str(exc),
            failure_stage="diagnostic_controller",
            metrics=None,
        )
    if isinstance(outcome, FailedInput):
        return _failure_record(
            source,
            error_code=outcome.error_code,
            error_message=outcome.error_message,
            failure_stage=outcome.failure_stage.value,
            metrics=outcome.metrics.as_record(),
        )
    assert isinstance(outcome, CompletedInput)
    report = outcome.result.record
    try:
        validate_current_report_record(report)
        metrics = outcome.metrics.as_record()
        width = int(source.identity["raw_width_px"])
        height = int(source.identity["raw_height_px"])
        source_pixels = width * height
        geometry_authorized = _source_geometry_within_authority(
            report,
            width=width,
            height=height,
        )
        work_bounded = _bounded_work(
            report,
            metrics,
            source_pixels=source_pixels,
        )
        no_official_diagnostic_output = (
            not outcome.artifacts.frame_outputs
            and not report["output"]["output_files"]
            and report["output"]["finalization"][
                "official_tiff_count"
            ]
            == 0
        )
        engineering_passed = (
            geometry_authorized
            and work_bounded
            and no_official_diagnostic_output
        )
        engineering_checks = {
            "source_lane_authority_bounded": geometry_authorized,
            "query_dp_memory_bounded": work_bounded,
            "diagnostics_no_official_tiff": no_official_diagnostic_output,
            "peak_temporary_limit_bytes": (
                _peak_temporary_limit_bytes(source_pixels)
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
            metrics=outcome.metrics.as_record(),
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
            "lane_selected_labels": [
                lane["selection"]["selected_label"]
                for lane in geometry["lanes"]
            ],
            "unresolved_codes": geometry["unresolved_codes"],
        },
        "transform_outcome": report["output"]["finalization"][
            "transform_assessment"
        ],
        "metrics": metrics,
        "structured_exception": None,
        "engineering_checks": engineering_checks,
        "recognition_accuracy_verdict": "not_assessed",
        "engineering_contract_passed": engineering_passed,
    }


def run_diagnostic_cohort(
    output_root: Path,
    *,
    jobs: int = 2,
) -> tuple[bool, dict[str, Any]]:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(
            f"diagnostic output root must be empty: {output_root}"
        )
    sources = load_diagnostic_sources()
    output_root.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(3, jobs))
    ) as executor:
        records = tuple(
            executor.map(run_diagnostic_source, sources)
        )
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
            "query_dp_memory": sum(
                record["engineering_checks"] is not None
                and not record["engineering_checks"][
                    "query_dp_memory_bounded"
                ]
                for record in records
            ),
            "diagnostic_official_tiff": sum(
                record["engineering_checks"] is not None
                and not record["engineering_checks"][
                    "diagnostics_no_official_tiff"
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
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args(argv)
    passed, summary = run_diagnostic_cohort(
        args.output_root.expanduser().resolve(),
        jobs=args.jobs,
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
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
