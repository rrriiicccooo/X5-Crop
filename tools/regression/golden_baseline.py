"""Compare current safe-crop source footprints with confirmed polygons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from x5crop.report.validation import validate_current_report_record


COMPARISON_SCHEMA = "x5crop_safe_containment_comparison_v1"
CONFIRMED_BASELINE_SCHEMA = "x5crop_user_confirmed_golden_baseline_v1"


def _validate_baseline_record(record: dict[str, Any]) -> None:
    if record.get("baseline_schema") != CONFIRMED_BASELINE_SCHEMA:
        raise ValueError("unsupported confirmed baseline schema")
    if record.get("status") != "user_confirmed":
        raise ValueError("baseline is not user-confirmed")
    if not record.get("sample_id") or not record.get("source_sha256"):
        raise ValueError("baseline identity is incomplete")


def _inverse_map(
    matrix: Sequence[Sequence[float]],
    x: float,
    y: float,
) -> tuple[float, float]:
    a, b, tx = matrix[0]
    c, d, ty = matrix[1]
    determinant = a * d - b * c
    if abs(determinant) <= 1.0e-12:
        raise ValueError("report transform is not invertible")
    x -= tx
    y -= ty
    return (
        (d * x - b * y) / determinant,
        (-c * x + a * y) / determinant,
    )


def _contains(
    polygon: Sequence[tuple[float, float]],
    point: tuple[float, float],
) -> bool:
    signs = []
    for index, left in enumerate(polygon):
        right = polygon[(index + 1) % len(polygon)]
        signs.append(
            (right[0] - left[0]) * (point[1] - left[1])
            - (right[1] - left[1]) * (point[0] - left[0])
        )
    return all(value >= -1.0e-6 for value in signs) or all(
        value <= 1.0e-6 for value in signs
    )


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
    finalization = report["output"]["finalization"]
    if report["decision"]["status"] != "approved_auto":
        return {
            "comparison_schema": COMPARISON_SCHEMA,
            "sample_id": str(baseline["sample_id"]),
            "comparison_status": "not_applicable_needs_review",
            "core_facts_sha256": report["core_facts_sha256"],
            "selected_count": finalization["selected_count"],
            "source_footprints": [],
            "frame_containment": [],
            "all_confirmed_content_contained": False,
        }
    boxes = finalization["final_boxes"]
    frames = baseline["frames"]
    if len(boxes) != len(frames):
        raise ValueError("final box count disagrees with confirmed frame count")
    matrix = finalization["transform_assessment"]["transform"]["matrix"]
    footprints = []
    containment = []
    for box, frame in zip(boxes, frames, strict=True):
        footprint = tuple(
            _inverse_map(matrix, x, y)
            for x, y in (
                (float(box["left"]), float(box["top"])),
                (float(box["right"]), float(box["top"])),
                (float(box["right"]), float(box["bottom"])),
                (float(box["left"]), float(box["bottom"])),
            )
        )
        contained = all(
            _contains(
                footprint,
                (float(point[0]), float(point[1])),
            )
            for point in frame["confirmed_integer_boundary_polygon"]
        )
        footprints.append([list(point) for point in footprint])
        containment.append(bool(contained))
    return {
        "comparison_schema": COMPARISON_SCHEMA,
        "sample_id": str(baseline["sample_id"]),
        "comparison_status": "compared",
        "core_facts_sha256": report["core_facts_sha256"],
        "selected_count": finalization["selected_count"],
        "source_footprints": footprints,
        "frame_containment": containment,
        "all_confirmed_content_contained": all(containment),
    }


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


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
        if baseline is not None:
            results.append(
                compare_baseline_record_to_report(baseline, report)
            )
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
