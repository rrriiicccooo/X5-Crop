"""Run the canonical bounded-safe-crop acceptance and coverage audit."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import finalize_detection
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.formats import FORMAT_CHOICES, format_spec
from x5crop.geometry.layout import infer_layout
from x5crop.io.tiff import read_tiff
from x5crop.report.validation import validate_current_report_record


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COHORT = (
    Path(__file__).with_name("cohorts") / "safe_crop_acceptance.jsonl"
)
DEFAULT_MANIFEST = PROJECT_ROOT / "Test/manual_review/manifest.jsonl"
DEFAULT_BASELINE = (
    PROJECT_ROOT / "Test/manual_review/user_confirmed_golden_baseline.jsonl"
)
RESULTS_NAME = "safe_crop_acceptance_results.jsonl"
SUMMARY_NAME = "safe_crop_acceptance_summary.json"
COVERAGE_AUDIT_NAME = "safe_crop_coverage_audit.json"
RESULT_SCHEMA = "x5crop_safe_crop_acceptance_result_v1"
SUMMARY_SCHEMA = "x5crop_safe_crop_acceptance_summary_v1"
COVERAGE_SCHEMA = "x5crop_safe_crop_coverage_audit_v1"
COHORT_SCHEMA = "x5crop_safe_crop_acceptance_cohort_v1"
MANIFEST_SCHEMA = "x5crop_manual_review_manifest_v2"
BASELINE_SCHEMA = "x5crop_user_confirmed_golden_baseline_v1"
EXPECTED_GOLDEN_SAMPLE_COUNT = 9
EXPECTED_SCENARIO_COUNT = 14
EXPECTED_MANIFEST_RECORD_COUNT = 111
COUNT_ANNOTATION = re.compile(r"_X5_(\d+)_")
RESULT_FIELDS = (
    "result_schema",
    "scenario_id",
    "sample_id",
    "source_sha256",
    "format_id",
    "strip_mode",
    "count_mode",
    "expected_count",
    "selected_count",
    "decision_status",
    "final_review_reasons",
    "candidate_gate_blocking_checks",
    "containment_by_frame",
    "containment_passed",
    "tiff_output_count",
    "expectation",
    "passed",
    "failure",
)
SUMMARY_FIELDS = (
    "summary_schema",
    "completion_scope",
    "real_holdout",
    "scenario_count",
    "passed_scenario_count",
    "failed_scenario_count",
    "must_approve_safe_count",
    "auto_or_review_count",
    "duplicate_source_sha_groups",
    "manifest_record_count_is_not_independent_sample_count",
    "coverage_audit",
    "coverage_audit_failed_record_count",
    "passed",
)


class AcceptancePreflightError(ValueError):
    pass


@dataclass(frozen=True)
class AcceptanceScenario:
    sample_id: str
    source_path: Path
    source_sha256: str
    format_id: str
    strip_mode: str
    expected_count: int
    count_mode: str
    expectation: str
    baseline: dict[str, Any]

    @property
    def scenario_id(self) -> str:
        return f"{self.sample_id}:{self.count_mode}"


def _load_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AcceptancePreflightError(f"cannot read {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AcceptancePreflightError(
                f"{path}:{line_number} is not valid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise AcceptancePreflightError(
                f"{path}:{line_number} must be a JSON object"
            )
        rows.append(value)
    return tuple(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AcceptancePreflightError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _indexed(
    rows: Iterable[dict[str, Any]],
    *,
    key: str,
    label: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key, ""))
        if not value or value in indexed:
            raise AcceptancePreflightError(
                f"{label} has missing or duplicate {key}: {value!r}"
            )
        indexed[value] = row
    return indexed


def _format_id_from_manifest(row: dict[str, Any]) -> str:
    directory = str(row["format_directory"])
    return {"66": "120-66", "67": "120-67"}.get(
        directory,
        directory,
    )


def _validate_output_root(output_root: Path) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        raise AcceptancePreflightError(
            f"acceptance output root must be empty: {output_root}"
        )


def _validated_manifest(
    manifest_rows: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    manifest = _indexed(
        manifest_rows,
        key="sample_id",
        label="canonical manifest",
    )
    sort_indices: list[int] = []
    project_root = PROJECT_ROOT.resolve()
    for row in manifest_rows:
        sample_id = str(row["sample_id"])
        try:
            sort_index = int(row["sort_index"])
            width = int(row["raw_width_px"])
            height = int(row["raw_height_px"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AcceptancePreflightError(
                f"canonical manifest numeric identity is invalid for {sample_id}"
            ) from exc
        if (
            sample_id != f"S{sort_index:03d}"
            or width <= 0
            or height <= 0
        ):
            raise AcceptancePreflightError(
                f"canonical manifest identity is invalid for {sample_id}"
            )
        sort_indices.append(sort_index)
        try:
            format_id = _format_id_from_manifest(row)
            spec = format_spec(format_id)
            strip_mode = str(row["strip_mode"])
            digest = str(row["source_sha256"]).lower()
            relative = Path(str(row["source_relative_path"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AcceptancePreflightError(
                f"canonical manifest fields are invalid for {sample_id}"
            ) from exc
        if (
            format_id not in FORMAT_CHOICES
            or strip_mode not in {"full", "partial"}
            or (
                strip_mode == "partial"
                and not spec.strip.partial_mode_supported
            )
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or relative.is_absolute()
            or relative.suffix.lower() not in {".tif", ".tiff"}
        ):
            raise AcceptancePreflightError(
                f"canonical manifest contract is invalid for {sample_id}"
            )
        source_path = (PROJECT_ROOT / relative).resolve()
        if (
            not source_path.is_relative_to(project_root)
            or not source_path.is_file()
        ):
            raise AcceptancePreflightError(
                f"canonical source path is invalid for {sample_id}: {source_path}"
            )
        annotation = COUNT_ANNOTATION.search(relative.name)
        if strip_mode == "full":
            if annotation is not None:
                raise AcceptancePreflightError(
                    f"full source carries a partial count annotation: {sample_id}"
                )
        elif (
            annotation is None
            or int(annotation.group(1)) not in spec.strip.partial_count_range
        ):
            raise AcceptancePreflightError(
                f"validation count annotation is invalid for {sample_id}"
            )
        if _sha256(source_path) != digest:
            raise AcceptancePreflightError(
                f"canonical source SHA mismatch for {sample_id}"
            )
    if tuple(sorted(sort_indices)) != tuple(
        range(1, EXPECTED_MANIFEST_RECORD_COUNT + 1)
    ):
        raise AcceptancePreflightError(
            "canonical manifest sort indices are not complete and unique"
        )
    return manifest


def _validated_baseline_by_sha(
    baseline_rows: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    baseline = _indexed(
        baseline_rows,
        key="source_sha256",
        label="confirmed baseline SHA oracle",
    )
    for digest, row in baseline.items():
        frames = row.get("frames")
        try:
            frame_count = int(row["frame_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AcceptancePreflightError(
                f"confirmed geometry count is invalid for SHA {digest}"
            ) from exc
        if (
            len(digest) != 64
            or not isinstance(frames, list)
            or len(frames) != frame_count
            or frame_count <= 0
        ):
            raise AcceptancePreflightError(
                f"confirmed geometry is incomplete for SHA {digest}"
            )
        for frame in frames:
            polygon = frame.get("confirmed_integer_boundary_polygon")
            if (
                not isinstance(polygon, list)
                or len(polygon) < 4
                or any(
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(
                        not isinstance(value, (int, float))
                        for value in point
                    )
                    for point in polygon
                )
            ):
                raise AcceptancePreflightError(
                    f"confirmed geometry polygon is invalid for SHA {digest}"
                )
    return baseline


def validate_acceptance_result_record(record: dict[str, Any]) -> None:
    if (
        tuple(record) != RESULT_FIELDS
        or record["result_schema"] != RESULT_SCHEMA
        or record["decision_status"]
        not in {"approved_auto", "needs_review", "terminal_failure"}
        or not isinstance(record["passed"], bool)
    ):
        raise ValueError("acceptance result does not use the frozen v1 schema")


def validate_acceptance_summary_record(record: dict[str, Any]) -> None:
    if (
        tuple(record) != SUMMARY_FIELDS
        or record["summary_schema"] != SUMMARY_SCHEMA
        or record["real_holdout"] != "unavailable"
        or not isinstance(record["passed"], bool)
    ):
        raise ValueError("acceptance summary does not use the frozen v1 schema")


def acceptance_preflight(
    cohort_path: Path,
    manifest_path: Path,
    baseline_path: Path,
    output_root: Path,
) -> tuple[
    tuple[AcceptanceScenario, ...],
    tuple[dict[str, Any], ...],
    tuple[tuple[str, tuple[str, ...]], ...],
]:
    _validate_output_root(output_root)
    cohort_rows = _load_jsonl(cohort_path)
    manifest_rows = _load_jsonl(manifest_path)
    baseline_rows = _load_jsonl(baseline_path)
    if len(cohort_rows) != EXPECTED_GOLDEN_SAMPLE_COUNT:
        raise AcceptancePreflightError(
            f"acceptance cohort requires {EXPECTED_GOLDEN_SAMPLE_COUNT} records"
        )
    if len(manifest_rows) != EXPECTED_MANIFEST_RECORD_COUNT:
        raise AcceptancePreflightError(
            f"canonical manifest requires {EXPECTED_MANIFEST_RECORD_COUNT} records"
        )
    if len(baseline_rows) != EXPECTED_GOLDEN_SAMPLE_COUNT:
        raise AcceptancePreflightError(
            f"confirmed baseline requires {EXPECTED_GOLDEN_SAMPLE_COUNT} records"
        )
    if any(row.get("cohort_schema") != COHORT_SCHEMA for row in cohort_rows):
        raise AcceptancePreflightError("acceptance cohort schema is not current")
    if any(
        row.get("manifest_schema") != MANIFEST_SCHEMA for row in manifest_rows
    ):
        raise AcceptancePreflightError("source manifest schema is not current")
    if any(
        row.get("baseline_schema") != BASELINE_SCHEMA
        or row.get("status") != "user_confirmed"
        for row in baseline_rows
    ):
        raise AcceptancePreflightError(
            "geometry oracle must be the confirmed current baseline"
        )

    manifest = _validated_manifest(manifest_rows)
    baseline_by_sha = _validated_baseline_by_sha(baseline_rows)
    sha_groups: dict[str, list[str]] = defaultdict(list)
    for row in manifest_rows:
        sha_groups[str(row["source_sha256"]).lower()].append(
            str(row["sample_id"])
        )
    duplicate_sha_groups = tuple(
        (digest, tuple(sample_ids))
        for digest, sample_ids in sorted(sha_groups.items())
        if len(sample_ids) > 1
    )

    scenarios: list[AcceptanceScenario] = []
    for row in cohort_rows:
        sample_id = str(row["sample_id"])
        manifest_row = manifest.get(sample_id)
        if manifest_row is None:
            raise AcceptancePreflightError(
                f"cohort sample is absent from canonical manifest: {sample_id}"
            )
        expected_identity = (
            str(row["source_relative_path"]),
            str(row["source_sha256"]).lower(),
            str(row["format_id"]),
            str(row["strip_mode"]),
        )
        actual_identity = (
            str(manifest_row["source_relative_path"]),
            str(manifest_row["source_sha256"]).lower(),
            _format_id_from_manifest(manifest_row),
            str(manifest_row["strip_mode"]),
        )
        if actual_identity != expected_identity:
            raise AcceptancePreflightError(
                f"cohort/manifest identity mismatch for {sample_id}"
            )
        source_path = (PROJECT_ROOT / actual_identity[0]).resolve()
        baseline = baseline_by_sha.get(actual_identity[1])
        if baseline is None:
            raise AcceptancePreflightError(
                f"confirmed geometry SHA oracle is missing for {sample_id}"
            )
        expected_count = int(row["expected_count"])
        if (
            int(baseline["frame_count"]) != expected_count
            or expected_count <= 0
            or expected_count
            > format_spec(actual_identity[2]).strip.default_count
        ):
            raise AcceptancePreflightError(
                f"confirmed count is invalid for {sample_id}"
            )
        count_modes = tuple(row.get("count_modes", ()))
        if (
            not count_modes
            or any(
                mode not in {"fixed_full", "explicit", "auto"}
                for mode in count_modes
            )
            or (
                actual_identity[3] == "full"
                and count_modes != ("fixed_full",)
            )
        ):
            raise AcceptancePreflightError(
                f"count modes are invalid for {sample_id}"
            )
        for count_mode in count_modes:
            scenarios.append(
                AcceptanceScenario(
                    sample_id=sample_id,
                    source_path=source_path,
                    source_sha256=actual_identity[1],
                    format_id=actual_identity[2],
                    strip_mode=actual_identity[3],
                    expected_count=expected_count,
                    count_mode=count_mode,
                    expectation=str(row["expectation"]),
                    baseline=baseline,
                )
            )
    if len(scenarios) != EXPECTED_SCENARIO_COUNT:
        raise AcceptancePreflightError(
            f"acceptance requires {EXPECTED_SCENARIO_COUNT} scenarios"
        )
    return tuple(scenarios), manifest_rows, duplicate_sha_groups


def _load_single_report(path: Path) -> dict[str, Any]:
    rows = _load_jsonl(path)
    if len(rows) != 1:
        raise RuntimeError(f"{path} must contain exactly one report")
    validate_current_report_record(rows[0])
    return rows[0]


def _inverse_map(
    matrix: Sequence[Sequence[float]],
    x: float,
    y: float,
) -> tuple[float, float]:
    a, b, tx = matrix[0]
    c, d, ty = matrix[1]
    determinant = a * d - b * c
    if abs(determinant) <= 1.0e-12:
        raise RuntimeError("reported transform is not invertible")
    output_x = x - tx
    output_y = y - ty
    return (
        (d * output_x - b * output_y) / determinant,
        (-c * output_x + a * output_y) / determinant,
    )


def _cross(
    left: tuple[float, float],
    right: tuple[float, float],
    point: tuple[float, float],
) -> float:
    return (
        (right[0] - left[0]) * (point[1] - left[1])
        - (right[1] - left[1]) * (point[0] - left[0])
    )


def _point_in_convex_polygon(
    point: tuple[float, float],
    polygon: Sequence[tuple[float, float]],
    *,
    epsilon: float = 1.0e-6,
) -> bool:
    values = tuple(
        _cross(
            polygon[index],
            polygon[(index + 1) % len(polygon)],
            point,
        )
        for index in range(len(polygon))
    )
    return all(value >= -epsilon for value in values) or all(
        value <= epsilon for value in values
    )


def _containment_results(
    report: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[bool, tuple[bool, ...]]:
    finalization = report["output"]["finalization"]
    boxes = finalization["final_boxes"]
    frames = baseline["frames"]
    if len(boxes) != len(frames):
        return False, ()
    matrix = finalization["transform_assessment"]["transform"]["matrix"]
    frame_results: list[bool] = []
    for box, frame in zip(boxes, frames, strict=True):
        output_polygon = (
            (float(box["left"]), float(box["top"])),
            (float(box["right"]), float(box["top"])),
            (float(box["right"]), float(box["bottom"])),
            (float(box["left"]), float(box["bottom"])),
        )
        source_footprint = tuple(
            _inverse_map(matrix, x, y) for x, y in output_polygon
        )
        frame_results.append(
            all(
                _point_in_convex_polygon(
                    (float(point[0]), float(point[1])),
                    source_footprint,
                )
                for point in frame[
                    "confirmed_integer_boundary_polygon"
                ]
            )
        )
    return all(frame_results), tuple(frame_results)


def _run_scenario(
    scenario: AcceptanceScenario,
    output_root: Path,
) -> dict[str, Any]:
    scenario_root = output_root / "scenarios" / scenario.scenario_id.replace(
        ":",
        "_",
    )
    scenario_root.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(
        prefix=f"x5crop-{scenario.sample_id}-",
        dir="/private/tmp",
    ) as staging:
        staged_source = (
            Path(staging)
            / f"{scenario.sample_id}{scenario.source_path.suffix.lower()}"
        )
        staged_source.symlink_to(scenario.source_path)
        command = [
            sys.executable,
            str(PROJECT_ROOT / "X5_Crop.py"),
            str(staged_source),
            "--output",
            str(scenario_root),
            "--format",
            scenario.format_id,
            "--strip",
            scenario.strip_mode,
            "--layout",
            str(scenario.baseline["strip_orientation"]),
            "--compression",
            "same",
            "--jobs",
            "1",
            "--report",
            "--debug-analysis",
            "--no-copy-review-files",
        ]
        if scenario.count_mode == "explicit":
            command.extend(("--count", str(scenario.expected_count)))
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    report_path = scenario_root / "x5_crop_report.jsonl"
    if completed.returncode != 0 or not report_path.is_file():
        return {
            "result_schema": RESULT_SCHEMA,
            "scenario_id": scenario.scenario_id,
            "sample_id": scenario.sample_id,
            "source_sha256": scenario.source_sha256,
            "format_id": scenario.format_id,
            "strip_mode": scenario.strip_mode,
            "count_mode": scenario.count_mode,
            "expected_count": scenario.expected_count,
            "selected_count": None,
            "decision_status": "terminal_failure",
            "final_review_reasons": [],
            "candidate_gate_blocking_checks": [],
            "containment_by_frame": [],
            "containment_passed": False,
            "tiff_output_count": 0,
            "expectation": scenario.expectation,
            "passed": False,
            "failure": (
                f"runtime exit {completed.returncode}: "
                f"{completed.stdout[-2000:]}"
            ),
        }
    report = _load_single_report(report_path)
    decision = report["decision"]
    status = str(decision["status"])
    selected_count = report["grid_selection"]["selected_count"]
    containment_passed, containment_by_frame = (
        _containment_results(report, scenario.baseline)
        if status == "approved_auto"
        else (False, ())
    )
    gate_blocking = tuple(
        item["code"]
        for item in report["candidate_gate"]["checks"]
        if item["blocks"]
    )
    if scenario.expectation == "must_approve_safe":
        passed = (
            status == "approved_auto"
            and selected_count == scenario.expected_count
            and containment_passed
        )
    elif scenario.expectation == "auto_or_review":
        passed = (
            status == "approved_auto"
            and selected_count == scenario.expected_count
            and containment_passed
        ) or (
            status == "needs_review"
            and bool(gate_blocking)
            and bool(decision["final_review_reasons"])
        )
    else:
        passed = False
    return {
        "result_schema": RESULT_SCHEMA,
        "scenario_id": scenario.scenario_id,
        "sample_id": scenario.sample_id,
        "source_sha256": scenario.source_sha256,
        "format_id": scenario.format_id,
        "strip_mode": scenario.strip_mode,
        "count_mode": scenario.count_mode,
        "expected_count": scenario.expected_count,
        "selected_count": selected_count,
        "decision_status": status,
        "final_review_reasons": list(
            decision["final_review_reasons"]
        ),
        "candidate_gate_blocking_checks": list(gate_blocking),
        "containment_by_frame": list(containment_by_frame),
        "containment_passed": containment_passed,
        "tiff_output_count": len(report["output"]["output_files"]),
        "expectation": scenario.expectation,
        "passed": passed,
        "failure": None if passed else "acceptance_contract_failed",
    }


def _expected_count_annotation(row: dict[str, Any]) -> int | None:
    if row["strip_mode"] != "partial":
        return format_spec(_format_id_from_manifest(row)).strip.default_count
    match = COUNT_ANNOTATION.search(Path(row["source_relative_path"]).name)
    return None if match is None else int(match.group(1))


def _audit_manifest_record(row: dict[str, Any]) -> dict[str, Any]:
    source = PROJECT_ROOT / str(row["source_relative_path"])
    format_id = _format_id_from_manifest(row)
    strip_mode = str(row["strip_mode"])
    configuration = get_detection_configuration(
        format_id,
        strip_mode,
        None,
    )
    array, profile, _warnings = read_tiff(source, 0)
    height = int(row["raw_height_px"])
    width = int(row["raw_width_px"])
    layout = infer_layout(width, height)
    workspace = prepare_detection_workspace(
        array,
        profile,
        layout,
        configuration,
        None,
    )
    candidate = choose_detection(workspace, configuration, None)
    decision = apply_decision_gate(
        candidate.gate,
        configuration.count_request.mode,
    )
    final = finalize_detection(candidate, decision, layout=layout)
    expected_count = _expected_count_annotation(row)
    return {
        "sample_id": str(row["sample_id"]),
        "source_sha256": str(row["source_sha256"]),
        "format_id": format_id,
        "strip_mode": strip_mode,
        "validation_filename_cohort": (
            "pass"
            if Path(row["source_relative_path"]).name.startswith("pass_")
            else "unknown"
        ),
        "expected_count_annotation": expected_count,
        "selected_count": final.selected_count,
        "decision_status": decision.status,
        "final_review_reasons": list(decision.final_review_reasons),
        "count_match": (
            None
            if expected_count is None
            else final.selected_count == expected_count
        ),
        "filename_annotation_runtime_input": False,
    }


def run_coverage_audit(
    manifest_rows: Sequence[dict[str, Any]],
    duplicate_sha_groups: Sequence[tuple[str, tuple[str, ...]]],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for row in manifest_rows:
        try:
            records.append(_audit_manifest_record(row))
        except Exception as exc:
            failures.append(
                {
                    "sample_id": str(row.get("sample_id", "")),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    partial = tuple(
        item for item in records if item["strip_mode"] == "partial"
    )
    pass_partial = tuple(
        item
        for item in partial
        if item["validation_filename_cohort"] == "pass"
    )
    confusion: Counter[str] = Counter()
    for item in partial:
        expected = item["expected_count_annotation"]
        selected = item["selected_count"]
        confusion[f"{expected}->{selected}"] += 1
    covered_cells = {
        (item["format_id"], item["strip_mode"]) for item in records
    }
    coverage_cells = [
        {
            "format_id": format_id,
            "strip_mode": strip_mode,
            "real_sample_coverage": (
                "available"
                if (format_id, strip_mode) in covered_cells
                else "unavailable"
            ),
        }
        for format_id in FORMAT_CHOICES
        for strip_mode in ("full", "partial")
        if not (
            strip_mode == "partial"
            and not format_spec(format_id).strip.partial_mode_supported
        )
    ]
    return {
        "schema": COVERAGE_SCHEMA,
        "blocking": False,
        "real_holdout": "unavailable",
        "manifest_record_count": len(manifest_rows),
        "independent_source_sha_count": len(
            {str(row["source_sha256"]) for row in manifest_rows}
        ),
        "duplicate_source_sha_groups": [
            {"source_sha256": digest, "sample_ids": list(sample_ids)}
            for digest, sample_ids in duplicate_sha_groups
        ],
        "completed_record_count": len(records),
        "failed_record_count": len(failures),
        "failures": failures,
        "partial_record_count": len(partial),
        "partial_count_confusion_matrix": dict(sorted(confusion.items())),
        "pass_partial_record_count": len(pass_partial),
        "pass_partial_quality": {
            "approved_auto_count": sum(
                item["decision_status"] == "approved_auto"
                for item in pass_partial
            ),
            "count_match_count": sum(
                item["count_match"] is True for item in pass_partial
            ),
            "record_count_is_not_independent_sample_count": True,
        },
        "coverage_cells": coverage_cells,
        "records": records,
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_acceptance(
    cohort_path: Path,
    manifest_path: Path,
    baseline_path: Path,
    output_root: Path,
    *,
    include_coverage_audit: bool,
) -> tuple[bool, dict[str, Any]]:
    (
        scenarios,
        manifest_rows,
        duplicate_sha_groups,
    ) = acceptance_preflight(
        cohort_path,
        manifest_path,
        baseline_path,
        output_root,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    results = tuple(
        _run_scenario(scenario, output_root) for scenario in scenarios
    )
    for result in results:
        validate_acceptance_result_record(result)
    results_path = output_root / RESULTS_NAME
    results_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False) + "\n" for item in results
        ),
        encoding="utf-8",
    )
    audit = (
        run_coverage_audit(manifest_rows, duplicate_sha_groups)
        if include_coverage_audit
        else None
    )
    if audit is not None:
        _write_json(output_root / COVERAGE_AUDIT_NAME, audit)
    passed = all(bool(item["passed"]) for item in results)
    summary = {
        "summary_schema": SUMMARY_SCHEMA,
        "completion_scope": "user_confirmed_golden_only",
        "real_holdout": "unavailable",
        "scenario_count": len(results),
        "passed_scenario_count": sum(
            bool(item["passed"]) for item in results
        ),
        "failed_scenario_count": sum(
            not bool(item["passed"]) for item in results
        ),
        "must_approve_safe_count": sum(
            item["expectation"] == "must_approve_safe"
            for item in results
        ),
        "auto_or_review_count": sum(
            item["expectation"] == "auto_or_review"
            for item in results
        ),
        "duplicate_source_sha_groups": [
            {"source_sha256": digest, "sample_ids": list(sample_ids)}
            for digest, sample_ids in duplicate_sha_groups
        ],
        "manifest_record_count_is_not_independent_sample_count": True,
        "coverage_audit": (
            "completed_non_blocking"
            if audit is not None
            else "not_requested"
        ),
        "coverage_audit_failed_record_count": (
            None if audit is None else audit["failed_record_count"]
        ),
        "passed": passed,
    }
    validate_acceptance_summary_record(summary)
    _write_json(output_root / SUMMARY_NAME, summary)
    return passed, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run X5 Crop bounded-safe-crop acceptance."
    )
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--audit-111",
        action="store_true",
        help="Also run the non-blocking canonical 111-record coverage audit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        passed, summary = run_acceptance(
            args.cohort.expanduser().resolve(),
            args.manifest.expanduser().resolve(),
            args.baseline.expanduser().resolve(),
            args.output_root.expanduser().resolve(),
            include_coverage_audit=bool(args.audit_111),
        )
    except AcceptancePreflightError as exc:
        print(f"preflight error: {exc}", file=sys.stderr)
        return 2
    print(
        f"acceptance: {summary['passed_scenario_count']}/"
        f"{summary['scenario_count']} passed"
    )
    print(f"artifacts: {args.output_root.expanduser().resolve()}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
