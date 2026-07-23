"""Report comparison helpers for X5 Crop regression checks."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from x5crop.report.validation import validate_current_report_record


DEFAULT_FIELDS = (
    "input.scan_canvas_evidence",
    "input.transform_geometry",
    "input.source_photo_edge_pairs",
    "input.mapped_photo_edge_pairs",
    "input.shared_short_axes",
    "input.source_lane_divider",
    "input.lane_divider",
    "decision.status",
    "decision.final_review_reasons",
    "selection.selected_rank",
    "selection.geometry_resolution",
    "output.final_geometry.frame_crop_envelopes",
    "output.final_geometry.final_boxes",
)


@dataclass(frozen=True)
class ReportComparisonIdentity:
    source: str
    page: int
    format_id: str
    layout: str
    strip_mode: str
    requested_count: int | None
    bleed_x: int
    bleed_y: int

    def __str__(self) -> str:
        count = "auto" if self.requested_count is None else str(self.requested_count)
        return (
            f"{self.source}#page={self.page} "
            f"[{self.format_id}/{self.strip_mode}, layout={self.layout}, "
            f"count={count}, "
            f"bleed={self.bleed_x}x{self.bleed_y}]"
        )


@dataclass(frozen=True)
class ReportDiff:
    identity: ReportComparisonIdentity
    field: str
    before: Any
    after: Any


def field_value(row: dict[str, Any], field: str) -> Any:
    value: Any = row
    for part in str(field).split("."):
        if value is None:
            return None
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"Current report field is missing: {field}")
        value = value[part]
    return value


def load_jsonl_report(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def report_key(row: dict[str, Any]) -> ReportComparisonIdentity:
    validate_current_report_record(row)
    analysis_identity = row["analysis_identity"]
    source = analysis_identity["source"]
    config = analysis_identity["runtime_configuration"]
    if int(source["page"]) != int(config["page"]):
        raise ValueError("report source and configuration page disagree")
    return ReportComparisonIdentity(
        source=str(row["source"]),
        page=int(source["page"]),
        format_id=str(config["format_id"]),
        layout=str(config["layout"]),
        strip_mode=str(config["strip_mode"]),
        requested_count=(
            None
            if config["requested_count"] is None
            else int(config["requested_count"])
        ),
        bleed_x=int(config["bleed_x"]),
        bleed_y=int(config["bleed_y"]),
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
    for key in sorted(set(baseline) | set(candidate), key=str):
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
        print(f"{diff.identity}: {diff.field}")
        print(f"  before: {diff.before}")
        print(f"  after:  {diff.after}")
    if len(diffs) > 200:
        print(f"... {len(diffs) - 200} more diffs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
