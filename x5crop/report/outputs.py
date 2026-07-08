from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from ..app_info import REPORT_JSONL_NAME, SUMMARY_CSV_NAME
from ..domain import ProcessResult
from ..export.paths import output_directory_for
from ..runtime.config import RuntimeConfig
from ..utils import json_safe


def append_report_jsonl(path: Path, result: ProcessResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(json_safe(asdict(result)), ensure_ascii=False) + "\n")


def append_summary_csv(path: Path, result: ProcessResult) -> None:
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
                "version": result.version,
                "policy_id": result.policy_id,
                "status": result.status,
                "confidence": f"{result.confidence:.3f}",
                "film_format": result.film_format,
                "layout": result.layout,
                "strip_mode": result.strip_mode,
                "count": result.count,
                "final_review_reasons": ";".join(result.final_review_reasons),
                "output_count": len(result.output_files),
            }
        )


def write_report_outputs_for_result(result: ProcessResult, config: RuntimeConfig) -> None:
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
