from __future__ import annotations

import csv
import json
from pathlib import Path

from ..app_info import REPORT_JSONL_NAME, SUMMARY_CSV_NAME
from .model import ReportResult
from ..output.surface import output_directory_for
from ..run_config import RunConfig
from ..utils import json_safe


def append_report_jsonl(path: Path, result: ReportResult) -> None:
    if not result.record:
        raise ValueError("Current report record is missing")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(json_safe(result.record), ensure_ascii=False) + "\n")


def append_summary_csv(path: Path, result: ReportResult) -> None:
    if not result.record:
        raise ValueError("Current report record is missing")
    record = result.record
    script_version = record["script_version"]
    output_files = record["output"]["output_files"]
    selection = record["selection"]
    selected = selection["candidates"][selection["selected_rank"] - 1]
    geometry = selected["candidate_geometry"]
    decision = record["decision"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "script_version",
        "configuration_id",
        "status",
        "format_id",
        "layout",
        "strip_mode",
        "count",
        "final_review_reasons",
        "output_count",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "source": record["source"],
                "script_version": script_version,
                "configuration_id": record["configuration"]["configuration_id"],
                "status": decision["status"],
                "format_id": geometry["format_id"],
                "layout": geometry["layout"],
                "strip_mode": geometry["strip_mode"],
                "count": geometry["count"],
                "final_review_reasons": ";".join(
                    decision["final_review_reasons"]
                ),
                "output_count": len(output_files),
            }
        )


def write_report_outputs_for_result(result: ReportResult, config: RunConfig) -> None:
    if not config.report:
        return
    output_dir = output_directory_for(Path(result.record["source"]), config)
    append_report_jsonl(output_dir / REPORT_JSONL_NAME, result)
    append_summary_csv(output_dir / SUMMARY_CSV_NAME, result)
