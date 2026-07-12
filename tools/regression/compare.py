"""Report comparison helpers for X5 Crop regression checks."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from x5crop.report.validation import validate_current_report_record


DEFAULT_FIELDS = (
    "status",
    "final_review_reasons",
    "output_geometry.crop_envelope",
    "output_geometry.frame_boxes",
    "separator_observations",
    "separator_assignments",
    "frame_boundaries",
)


@dataclass(frozen=True)
class ReportDiff:
    source: str
    field: str
    before: Any
    after: Any


def field_value(row: dict[str, Any], field: str) -> Any:
    value: Any = row
    for part in str(field).split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"Current report field is missing: {field}")
        value = value[part]
    return value


def validate_report_row(row: dict[str, Any]) -> None:
    validate_current_report_record(row)


def load_jsonl_report(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def report_key(row: dict[str, Any]) -> str:
    validate_report_row(row)
    return str(row["source"])


def compare_report_rows(
    baseline_rows: Iterable[dict[str, Any]],
    candidate_rows: Iterable[dict[str, Any]],
    fields: Iterable[str] = DEFAULT_FIELDS,
) -> list[ReportDiff]:
    baseline = {report_key(row): row for row in baseline_rows}
    candidate = {report_key(row): row for row in candidate_rows}
    diffs: list[ReportDiff] = []
    for key in sorted(set(baseline) | set(candidate)):
        if key not in baseline:
            diffs.append(ReportDiff(key, "__row__", None, "added"))
            continue
        if key not in candidate:
            diffs.append(ReportDiff(key, "__row__", "removed", None))
            continue
        for field in fields:
            before = field_value(baseline[key], field)
            after = field_value(candidate[key], field)
            if before != after:
                diffs.append(ReportDiff(key, field, before, after))
    return diffs


def compare_report_files(
    baseline_path: Path,
    candidate_path: Path,
    fields: Iterable[str] = DEFAULT_FIELDS,
) -> list[ReportDiff]:
    return compare_report_rows(
        load_jsonl_report(baseline_path),
        load_jsonl_report(candidate_path),
        fields=fields,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two X5 Crop JSONL reports.")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--field", action="append", dest="fields", help="Field to compare. Can be repeated.")
    args = parser.parse_args(argv)
    fields = tuple(args.fields) if args.fields else DEFAULT_FIELDS
    diffs = compare_report_files(args.baseline, args.candidate, fields=fields)
    print(f"baseline rows: {len(load_jsonl_report(args.baseline))}")
    print(f"candidate rows: {len(load_jsonl_report(args.candidate))}")
    print(f"diff count: {len(diffs)}")
    for diff in diffs[:200]:
        print(f"{diff.source}: {diff.field}")
        print(f"  before: {diff.before}")
        print(f"  after:  {diff.after}")
    if len(diffs) > 200:
        print(f"... {len(diffs) - 200} more diffs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
