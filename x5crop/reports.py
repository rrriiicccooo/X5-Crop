from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .app_info import REPORT_JSONL_NAME, SUMMARY_CSV_NAME
from .config import Config
from .domain import ProcessResult
from .export.paths import output_directory_for
from .utils import json_safe


def write_jsonl(path: Path, result: ProcessResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(json_safe(asdict(result)), ensure_ascii=False) + "\n")


def write_summary(path: Path, result: ProcessResult) -> None:
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
        "review_reasons",
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
                "version": result.version,
                "policy_id": result.policy_id,
                "status": result.status,
                "confidence": f"{result.confidence:.3f}",
                "film_format": result.film_format,
                "layout": result.layout,
                "strip_mode": result.strip_mode,
                "count": result.count,
                "review_reasons": ";".join(result.review_reasons),
                "output_count": len(result.output_files),
            }
        )


def write_reports_for_result(result: ProcessResult, config: Config) -> None:
    if not config.report:
        return
    output_dir = output_directory_for(Path(result.source), config)
    write_jsonl(output_dir / REPORT_JSONL_NAME, result)
    write_summary(output_dir / SUMMARY_CSV_NAME, result)


__all__ = [
    "write_jsonl",
    "write_reports_for_result",
    "write_summary",
]
