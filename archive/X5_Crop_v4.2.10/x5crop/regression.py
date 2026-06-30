"""Report comparison helpers for X5 Crop regression checks."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FIELDS = (
    "status",
    "confidence",
    "review_reasons",
    "outer_box",
    "frame_boxes",
    "gaps",
)


@dataclass(frozen=True)
class ReportDiff:
    source: str
    field: str
    before: Any
    after: Any


def load_jsonl_report(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def report_key(row: dict[str, Any]) -> str:
    return str(row.get("input_file") or row.get("source") or row.get("input") or row.get("stem") or "")


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
            before = baseline[key].get(field)
            after = candidate[key].get(field)
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
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
