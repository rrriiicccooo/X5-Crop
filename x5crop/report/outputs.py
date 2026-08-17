from __future__ import annotations

import csv
import json
from pathlib import Path

from ..app_info import REPORT_JSONL_NAME, SUMMARY_CSV_NAME
from .model import ReportResult


def append_report_jsonl(path: Path, result: ReportResult) -> None:
    if not result.record:
        raise ValueError("Current report record is missing")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result.record, ensure_ascii=False) + "\n")


def append_summary_csv(path: Path, result: ReportResult) -> None:
    if not result.record:
        raise ValueError("Current report record is missing")
    record = result.record
    script_version = record["script_version"]
    output_files = record["output"]["output_files"]
    decision = record["decision"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "script_version",
        "configuration_id",
        "status",
        "format_id",
        "layout",
        "requested_count",
        "selected_scan_canvas_profile_id",
        "lane_output_slot_counts",
        "output_slot_count",
        "candidate_gate_gaps",
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
                "format_id": record["configuration"]["format_id"],
                "layout": record["runtime_identity"][
                    "runtime_configuration"
                ]["layout"],
                "requested_count": record["configuration"][
                    "slot_count_request"
                ]["user_count"],
                "selected_scan_canvas_profile_id": record[
                    "photo_geometry"
                ]["selected_scan_canvas_profile_id"],
                "lane_output_slot_counts": ";".join(
                    str(value)
                    for value in (
                        []
                        if record["photo_geometry"][
                            "resolved_output_slots"
                        ]
                        is None
                        else record["photo_geometry"][
                            "resolved_output_slots"
                        ]["lane_output_slot_counts"]
                    )
                ),
                "output_slot_count": record["photo_geometry"][
                    "output_slot_count"
                ],
                "candidate_gate_gaps": ";".join(
                    check["gap"]
                    for check in record["candidate_gate"]["checks"]
                    if check["gap"] is not None
                ),
                "final_review_reasons": ";".join(
                    decision["final_review_reasons"]
                ),
                "output_count": len(output_files),
            }
        )


def write_report_outputs_for_result(result: ReportResult, output_dir: Path) -> None:
    append_summary_csv(output_dir / SUMMARY_CSV_NAME, result)
    append_report_jsonl(output_dir / REPORT_JSONL_NAME, result)
