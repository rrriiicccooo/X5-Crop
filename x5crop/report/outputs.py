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
    version = record.get("version", {})
    script_version = (
        version.get("script_version")
        if isinstance(version, dict)
        else str(version)
    )
    output = record.get("output", {})
    output_files = output.get("output_files", []) if isinstance(output, dict) else []
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "version",
        "policy_id",
        "status",
        "confidence",
        "film_format",
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
                "version": script_version,
                "policy_id": record.get("policy_id", ""),
                "status": record.get("status", ""),
                "confidence": f"{float(record.get('confidence', 0.0)):.3f}",
                "film_format": record.get("format_id", ""),
                "layout": record.get("layout", ""),
                "strip_mode": record.get("strip_mode", ""),
                "count": record.get("count", ""),
                "final_review_reasons": ";".join(record.get("final_review_reasons", [])),
                "output_count": len(output_files),
            }
        )


def write_report_outputs_for_result(result: ProcessResult, config: RunConfig) -> None:
    if not config.report:
        return
    output_dir = output_directory_for(Path(result.source), config)
    append_report_jsonl(output_dir / REPORT_JSONL_NAME, result)
    append_summary_csv(output_dir / SUMMARY_CSV_NAME, result)


__all__ = [
    "append_report_jsonl",
    "write_report_outputs_for_result",
    "append_summary_csv",
]
