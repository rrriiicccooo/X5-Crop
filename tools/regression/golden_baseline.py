"""Post-detection comparison with user-confirmed source geometry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from x5crop.report.validation import validate_current_report_record


COMPARISON_SCHEMA = "x5crop_golden_baseline_directional_comparison_v3"
CONFIRMED_BASELINE_SCHEMA = "x5crop_user_confirmed_golden_baseline_v1"
COMPARISON_STATES = frozenset(
    {
        "production_geometry_unavailable",
        "compared",
    }
)


def _validate_baseline_record(record: dict[str, Any]) -> None:
    if record.get("baseline_schema") != CONFIRMED_BASELINE_SCHEMA:
        raise ValueError("unsupported confirmed baseline schema")
    if record.get("status") != "user_confirmed":
        raise ValueError("baseline is not user-confirmed")
    if not record.get("sample_id") or not record.get("source_sha256"):
        raise ValueError("baseline identity is incomplete")


def compare_baseline_record_to_report(
    baseline: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    _validate_baseline_record(baseline)
    validate_current_report_record(report)
    source_identity = report["analysis_identity"]["source"]
    if (
        str(baseline["source_sha256"]).lower()
        != str(source_identity["content_sha256"]).lower()
    ):
        raise ValueError("baseline and report source SHA-256 disagree")
    result = {
        "comparison_schema": COMPARISON_SCHEMA,
        "sample_id": str(baseline["sample_id"]),
        "comparison_status": "production_geometry_unavailable",
        "core_facts_sha256": report["core_facts_sha256"],
        "geometry_resolution": "frame_grid_authority_unavailable",
        "source_envelopes": [],
        "protected_envelopes": [],
        "mapped_envelopes": [],
        "deskew": {
            "outcome": report["source_core"]["visual_deskew_outcome"],
            "angle_interval_degrees": None,
        },
        "transform": None,
        "final_boxes": [],
        "edge_metrics": [],
    }
    if result["comparison_status"] not in COMPARISON_STATES:
        raise AssertionError("unowned comparison state")
    return result


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [
            json.loads(line)
            for line in stream
            if line.strip()
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare current reports with confirmed geometry"
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    baselines = {
        str(row["source_sha256"]).lower(): row
        for row in _jsonl(args.baseline)
    }
    results = []
    for report in _jsonl(args.report):
        digest = str(
            report["analysis_identity"]["source"]["content_sha256"]
        ).lower()
        baseline = baselines.get(digest)
        if baseline is None:
            continue
        results.append(compare_baseline_record_to_report(baseline, report))
    text = "".join(
        json.dumps(result, ensure_ascii=False) + "\n"
        for result in results
    )
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
