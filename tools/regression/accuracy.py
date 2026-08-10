"""Run the source-bound V5 golden comparator around the production CLI."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Iterable, Sequence

from x5crop.report.validation import validate_current_report_record


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_COHORT_PATH = Path(__file__).with_name("cohorts") / "gold_accuracy.jsonl"
EXPECTED_SOURCE_COUNT = 9
EXPECTED_TASK_COUNT = 9


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_gold_source_identities() -> tuple[dict[str, object], ...]:
    records = tuple(
        json.loads(line)
        for line in GOLD_COHORT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if len(records) != EXPECTED_SOURCE_COUNT:
        raise ValueError("gold accuracy cohort must contain exactly nine sources")
    project_root = PROJECT_ROOT.resolve()
    sample_ids: set[str] = set()
    task_count = 0
    for record in records:
        sample_id = str(record.get("sample_id", ""))
        relative = Path(str(record.get("source_relative_path", "")))
        source = (PROJECT_ROOT / relative).resolve()
        expected_sha = str(record.get("source_sha256", "")).lower()
        count_modes = tuple(record.get("count_modes", ()))
        strip_mode = str(record.get("strip_mode", ""))
        expected_count_modes = {
            "full": ("fixed_full",),
            "partial": ("explicit",),
        }.get(strip_mode)
        if (
            record.get("cohort_schema") != "x5crop_gold_accuracy_cohort_v3"
            or not sample_id
            or sample_id in sample_ids
            or record.get("validation_role") != "gold_accuracy_blocking"
            or record.get("cohort_role") not in {"nominal", "challenge"}
            or count_modes != expected_count_modes
            or relative.is_absolute()
            or not source.is_relative_to(project_root)
            or not source.is_file()
            or len(expected_sha) != 64
            or _source_sha256(source) != expected_sha
        ):
            raise ValueError(f"gold source identity is invalid: {sample_id or relative}")
        geometry = record.get("confirmed_geometry")
        if (
            not isinstance(geometry, dict)
            or geometry.get("status") != "user_confirmed"
            or geometry.get("source_sha256") != expected_sha
            or len(geometry.get("frames", ()))
            != int(record.get("confirmed_photo_count", 0))
        ):
            raise ValueError(f"gold geometry is invalid: {sample_id}")
        sample_ids.add(sample_id)
        task_count += len(count_modes)
    if task_count != EXPECTED_TASK_COUNT:
        raise ValueError("gold accuracy cohort must contain exactly nine tasks")
    return records


def _contains_point(
    polygon: Sequence[Sequence[float]],
    point: Sequence[float],
    *,
    epsilon: float = 1.0e-6,
) -> bool:
    signs: list[bool] = []
    for left, right in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
        cross = (
            (right[0] - left[0]) * (point[1] - left[1])
            - (right[1] - left[1]) * (point[0] - left[0])
        )
        if abs(cross) > epsilon:
            signs.append(cross > 0.0)
    return not signs or all(signs) or not any(signs)


def _contains_polygon(
    outer: Sequence[Sequence[float]],
    inner: Sequence[Sequence[float]],
) -> bool:
    return all(_contains_point(outer, point) for point in inner)


def _unit_vector(x: float, y: float) -> tuple[float, float]:
    magnitude = math.hypot(x, y)
    if magnitude <= 0.0:
        raise ValueError("gold frame has a degenerate axis")
    return x / magnitude, y / magnitude


def _mean_edge_axis(
    polygon: Sequence[Sequence[float]],
    first: tuple[int, int],
    second: tuple[int, int],
) -> tuple[float, float]:
    return _unit_vector(
        (
            polygon[first[1]][0]
            - polygon[first[0]][0]
            + polygon[second[1]][0]
            - polygon[second[0]][0]
        )
        / 2.0,
        (
            polygon[first[1]][1]
            - polygon[first[0]][1]
            + polygon[second[1]][1]
            - polygon[second[0]][1]
        )
        / 2.0,
    )


def _projection_bounds(
    polygon: Sequence[Sequence[float]],
    axis: tuple[float, float],
) -> tuple[float, float]:
    values = tuple(point[0] * axis[0] + point[1] * axis[1] for point in polygon)
    return min(values), max(values)


def _assert_direct_use_budget(
    sample_id: str,
    frame_index: int,
    gold: Sequence[Sequence[float]],
    output: Sequence[Sequence[float]],
    strip_orientation: str,
) -> None:
    horizontal = strip_orientation == "horizontal"
    sequence_axis = _mean_edge_axis(
        gold,
        (0, 1) if horizontal else (0, 3),
        (3, 2) if horizontal else (1, 2),
    )
    cross_axis = _mean_edge_axis(
        gold,
        (0, 3) if horizontal else (0, 1),
        (1, 2) if horizontal else (3, 2),
    )
    gold_sequence = _projection_bounds(gold, sequence_axis)
    output_sequence = _projection_bounds(output, sequence_axis)
    gold_cross = _projection_bounds(gold, cross_axis)
    output_cross = _projection_bounds(output, cross_axis)
    sequence_span = gold_sequence[1] - gold_sequence[0]
    cross_span = gold_cross[1] - gold_cross[0]
    sequence_expansion = max(
        gold_sequence[0] - output_sequence[0],
        output_sequence[1] - gold_sequence[1],
    )
    cross_expansion = max(
        gold_cross[0] - output_cross[0],
        output_cross[1] - gold_cross[1],
    )
    pixel_allowance = 0.5
    if (
        sequence_expansion > sequence_span * 0.05 + pixel_allowance
        or cross_expansion > cross_span * 0.03 + pixel_allowance
    ):
        raise ValueError(
            f"{sample_id} frame {frame_index} exceeds gold direct-use budget"
        )


def _ordered_gold_mapping(
    gold_frames: Sequence[dict[str, object]],
    output_geometries: Sequence[dict[str, object]],
) -> tuple[int, ...]:
    mapping: list[int] = []
    next_output = 0
    for frame in gold_frames:
        polygon = frame["polygon_source_pixel_center_coordinates"]
        matches = tuple(
            index
            for index in range(next_output, len(output_geometries))
            if _contains_polygon(
                output_geometries[index]["constrained_source_footprint"],
                polygon,
            )
        )
        if not matches:
            return ()
        selected = matches[0]
        mapping.append(selected)
        next_output = selected + 1
    return tuple(mapping)


def _production_command(
    source: Path,
    output: Path,
    record: dict[str, object],
    count_mode: str,
) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "X5_Crop.py"),
        str(source),
        "--output",
        str(output),
        "--format",
        str(record["format_id"]),
        "--strip",
        str(record["strip_mode"]),
        "--jobs",
        "1",
    ]
    if count_mode == "explicit":
        command.extend(("--count", str(record["confirmed_photo_count"])))
    return command


def _validate_approved_geometry(
    record: dict[str, object],
    report: dict[str, object],
) -> None:
    sample_id = str(record["sample_id"])
    gold = record["confirmed_geometry"]
    frames = gold["frames"]
    outputs = report["output"]["finalization"]["resolved_output_geometries"]
    mapping = _ordered_gold_mapping(frames, outputs)
    if len(mapping) != len(frames):
        raise ValueError(f"{sample_id} approved output cuts confirmed content")
    for frame, output_index in zip(frames, mapping, strict=True):
        polygon = frame["polygon_source_pixel_center_coordinates"]
        output_polygon = outputs[output_index]["constrained_source_footprint"]
        _assert_direct_use_budget(
            sample_id,
            int(frame["frame_index"]),
            polygon,
            output_polygon,
            str(gold["strip_orientation"]),
        )
    transform = report["output"]["finalization"]["transform_assessment"]
    observed_angle = transform["observed_angle_interval_degrees"]
    gold_angles = tuple(
        math.degrees(math.atan(float(edge["slope"])))
        for edge in gold["shared_edges"]
    )
    if not all(
        observed_angle["minimum"] - 1.0e-9
        <= angle
        <= observed_angle["maximum"] + 1.0e-9
        for angle in gold_angles
    ):
        raise ValueError(f"{sample_id} deskew interval excludes confirmed edges")


def _run_task(record: dict[str, object], count_mode: str) -> str:
    source = (PROJECT_ROOT / str(record["source_relative_path"])).resolve()
    before = source.stat()
    with TemporaryDirectory(prefix="x5crop-accuracy-") as temporary:
        output = Path(temporary) / "x5_crop_output"
        completed = subprocess.run(
            _production_command(source, output, record, count_mode),
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"{record['sample_id']}/{count_mode} production CLI failed:\n"
                + completed.stdout[-4000:]
            )
        report_path = output / "x5_crop_report.jsonl"
        rows = tuple(
            json.loads(line)
            for line in report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if len(rows) != 1:
            raise ValueError("accuracy task must produce exactly one terminal report")
        report = rows[0]
        validate_current_report_record(report)
        identity = report["runtime_identity"]["source"]
        after = source.stat()
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or identity["input_ordinal"] != 1
            or identity["name"] != source.name
            or identity["size"] != before.st_size
            or identity["mtime_ns"] != before.st_mtime_ns
        ):
            raise ValueError("source stat identity changed across accuracy task")
        status = str(report["decision"]["status"])
        role = str(record["cohort_role"])
        if role == "nominal" and status != "approved_auto":
            raise ValueError(
                f"{record['sample_id']}/{count_mode} nominal task is {status}"
            )
        if role == "challenge" and status not in {
            "approved_auto",
            "needs_review",
        }:
            raise ValueError(
                f"{record['sample_id']}/{count_mode} challenge task is {status}"
            )
        if status == "approved_auto":
            _validate_approved_geometry(record, report)
        return status


def run_accuracy(records: Iterable[dict[str, object]]) -> tuple[int, int]:
    passed = 0
    approved = 0
    failures: list[str] = []
    for record in records:
        for count_mode in record["count_modes"]:
            identity = f"{record['sample_id']}/{count_mode}"
            try:
                status = _run_task(record, str(count_mode))
            except Exception as exc:
                failures.append(f"{identity}: {exc}")
                print(f"{identity}: FAIL: {exc}")
                continue
            passed += 1
            approved += status == "approved_auto"
            print(f"{identity}: {status}")
    if failures:
        raise ValueError(
            f"gold accuracy failed {len(failures)} task(s):\n"
            + "\n".join(failures)
        )
    return passed, approved


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise SystemExit("accuracy verifier takes no arguments")
    records = validate_gold_source_identities()
    passed, approved = run_accuracy(records)
    print(
        f"gold accuracy: {passed}/{EXPECTED_TASK_COUNT} safe; "
        f"approved={approved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
