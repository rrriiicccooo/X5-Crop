"""Compare two current bounded-safe-crop report sets."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from x5crop.report.validation import validate_current_report_record


DEFAULT_FIELDS = (
    "measurement",
    "grid_selection",
    "candidate_gate",
    "decision",
    "output.finalization",
    "core_facts_sha256",
)


@dataclass(frozen=True, order=True)
class ReportComparisonIdentity:
    source: str
    page: int
    format_id: str
    layout: str
    strip_mode: str
    output_slot_policy: str
    authoritative_count: int | None


@dataclass(frozen=True)
class ReportDiff:
    identity: ReportComparisonIdentity
    field: str
    before: Any
    after: Any


def field_value(row: dict[str, Any], field: str) -> Any:
    value: Any = row
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"current report field is missing: {field}")
        value = value[part]
    return value


def load_jsonl_report(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [
            json.loads(line)
            for line in handle
            if line.strip()
        ]


def report_key(row: dict[str, Any]) -> ReportComparisonIdentity:
    validate_current_report_record(row)
    source = row["analysis_identity"]["source"]
    config = row["analysis_identity"]["runtime_configuration"]
    if int(source["page"]) != int(config["page"]):
        raise ValueError("report source and runtime page disagree")
    policy = config["output_slot_policy"]
    return ReportComparisonIdentity(
        source=str(row["source"]),
        page=int(source["page"]),
        format_id=str(config["format_id"]),
        layout=str(config["layout"]),
        strip_mode=str(config["strip_mode"]),
        output_slot_policy=str(policy["policy"]),
        authoritative_count=(
            None
            if policy.get("authoritative_count") is None
            else int(policy["authoritative_count"])
        ),
    )


def _indexed_rows(
    rows: Iterable[dict[str, Any]],
    label: str,
) -> dict[ReportComparisonIdentity, dict[str, Any]]:
    indexed: dict[ReportComparisonIdentity, dict[str, Any]] = {}
    for row in rows:
        identity = report_key(row)
        if identity in indexed:
            raise ValueError(f"duplicate {label} report identity: {identity}")
        indexed[identity] = row
    return indexed


def compare_report_rows(
    baseline_rows: Iterable[dict[str, Any]],
    candidate_rows: Iterable[dict[str, Any]],
    fields: Iterable[str] = DEFAULT_FIELDS,
) -> list[ReportDiff]:
    baseline = _indexed_rows(baseline_rows, "baseline")
    candidate = _indexed_rows(candidate_rows, "candidate")
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
        fields,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare current X5 Crop reports")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--field", action="append", dest="fields")
    args = parser.parse_args(argv)
    fields = tuple(args.fields) if args.fields else DEFAULT_FIELDS
    diffs = compare_report_files(args.baseline, args.candidate, fields)
    print(f"diff count: {len(diffs)}")
    for diff in diffs[:200]:
        print(f"{diff.identity}: {diff.field}")
        print(f"  before: {diff.before}")
        print(f"  after:  {diff.after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
