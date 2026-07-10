from __future__ import annotations

import csv
import json
from pathlib import Path

from ..app_info import REPORT_JSONL_NAME, SUMMARY_CSV_NAME
from ..domain import ProcessResult
from ..output.surface import output_directory_for
from ..run_config import RunConfig
from ..utils import json_safe


def append_report_jsonl(path: Path, result: ProcessResult) -> None:
    if not result.report_record:
        raise ValueError("Current report record is missing")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(json_safe(result.report_record), ensure_ascii=False) + "\n")


def append_summary_csv(path: Path, result: ProcessResult) -> None:
    if not result.report_record:
        raise ValueError("Current report record is missing")
    record = result.report_record
    script_version = record["script_version"]
    output_files = record["output"]["output_files"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "script_version",
        "policy_id",
        "status",
        "confidence",
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
                "source": result.source,
                "script_version": script_version,
                "policy_id": record["policy_id"],
                "status": record["status"],
                "confidence": f"{float(record['confidence']):.3f}",
                "format_id": record["format_id"],
                "layout": record["layout"],
                "strip_mode": record["strip_mode"],
                "count": record["count"],
                "final_review_reasons": ";".join(record["final_review_reasons"]),
                "output_count": len(output_files),
            }
        )


def write_report_outputs_for_result(result: ProcessResult, config: RunConfig) -> None:
    if not config.report:
        return
    output_dir = output_directory_for(Path(result.source), config)
    append_report_jsonl(output_dir / REPORT_JSONL_NAME, result)
    append_summary_csv(output_dir / SUMMARY_CSV_NAME, result)
