"""Freeze and validate the status-independent benchmark I/O workload."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.scan_canvas import (
    ScanCanvasOutcome,
    observe_scan_canvas,
)
from x5crop.formats import format_spec
from x5crop.geometry.layout import infer_layout
from x5crop.io.tiff import read_tiff_page_shape, read_tiff_profile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_COHORT_PATH = (
    Path(__file__).with_name("cohorts")
    / "production_performance.jsonl"
)
BENCHMARK_WORKLOAD_PATH = (
    Path(__file__).with_name("cohorts")
    / "benchmark_io_workload.jsonl"
)
COHORT_SCHEMA = "x5crop_performance_cohort_v1"
WORKLOAD_SCHEMA = "x5crop_benchmark_io_workload_v1"
FIXED_SOURCE_COUNT = 24
FIXED_WORKLOAD_COUNT = 168
BENCHMARK_WIDTH_PX = 512
BENCHMARK_HEIGHT_PX = 384


@dataclass(frozen=True)
class PerformanceSourceIdentity:
    sample_id: str
    source_relative_path: str
    source_sha256: str
    format_id: str
    strip_mode: str
    compression: str

    @property
    def source_path(self) -> Path:
        return PROJECT_ROOT / self.source_relative_path


def _jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    return _sha256(path)


def load_performance_sources(
    *,
    verify_source_files: bool = True,
) -> tuple[PerformanceSourceIdentity, ...]:
    rows = _jsonl(PERFORMANCE_COHORT_PATH)
    if len(rows) != FIXED_SOURCE_COUNT:
        raise ValueError("performance cohort must contain exactly 24 sources")
    sources: list[PerformanceSourceIdentity] = []
    project_root = PROJECT_ROOT.resolve()
    for row in rows:
        source = PerformanceSourceIdentity(
            sample_id=str(row.get("sample_id", "")),
            source_relative_path=str(
                row.get("source_relative_path", "")
            ),
            source_sha256=str(row.get("source_sha256", "")).lower(),
            format_id=str(row.get("format_id", "")),
            strip_mode=str(row.get("strip_mode", "")),
            compression=str(row.get("compression", "")),
        )
        path = source.source_path.resolve()
        if (
            row.get("cohort_schema") != COHORT_SCHEMA
            or not source.sample_id
            or Path(source.source_relative_path).is_absolute()
            or not path.is_relative_to(project_root)
            or (
                verify_source_files
                and (
                    not path.is_file()
                    or _sha256(path) != source.source_sha256
                )
            )
        ):
            raise ValueError(
                f"performance source identity is invalid: {source.sample_id}"
            )
        sources.append(source)
    if len({item.sample_id for item in sources}) != len(sources):
        raise ValueError("performance sample identities must be unique")
    return tuple(sources)


def _output_slot_count(
    source: PerformanceSourceIdentity,
    *,
    width: int,
    height: int,
    layout: str,
) -> int:
    configuration = get_detection_configuration(
        source.format_id,
        source.strip_mode,
        None,
    )
    if source.strip_mode == "full":
        count = configuration.count_request.authoritative_count
        if count is None:
            raise ValueError("fixed-full benchmark source has no count")
        return count
    canvas = observe_scan_canvas(
        max(width, height),
        min(width, height),
        layout,
        configuration.scan_canvas,
    )
    if (
        canvas.outcome != ScanCanvasOutcome.SUPPORTED
        or canvas.selected_profile is None
    ):
        raise ValueError(
            f"{source.sample_id} has no unique benchmark scan canvas"
        )
    capacity = configuration.physical_spec.maximum_frame_count(
        canvas.selected_profile.profile_id
    )
    if capacity is None:
        raise ValueError(
            f"{source.sample_id} has no unique benchmark capacity"
        )
    return capacity


def _task_box(
    *,
    width: int,
    height: int,
    layout: str,
    lane_index: int,
    lane_count: int,
    lane_ordinal: int,
    lane_slot_count: int,
) -> tuple[int, int, int, int]:
    if layout == "horizontal":
        lane_top = round(height * lane_index / lane_count)
        lane_bottom = round(height * (lane_index + 1) / lane_count)
        segment_left = round(
            width * (lane_ordinal - 1) / lane_slot_count
        )
        segment_right = round(width * lane_ordinal / lane_slot_count)
        task_width = min(
            BENCHMARK_WIDTH_PX,
            max(1, segment_right - segment_left),
        )
        task_height = min(
            BENCHMARK_HEIGHT_PX,
            max(1, lane_bottom - lane_top),
        )
        center_x = (segment_left + segment_right) // 2
        center_y = (lane_top + lane_bottom) // 2
    else:
        lane_left = round(width * lane_index / lane_count)
        lane_right = round(width * (lane_index + 1) / lane_count)
        segment_top = round(
            height * (lane_ordinal - 1) / lane_slot_count
        )
        segment_bottom = round(
            height * lane_ordinal / lane_slot_count
        )
        task_width = min(
            BENCHMARK_HEIGHT_PX,
            max(1, lane_right - lane_left),
        )
        task_height = min(
            BENCHMARK_WIDTH_PX,
            max(1, segment_bottom - segment_top),
        )
        center_x = (lane_left + lane_right) // 2
        center_y = (segment_top + segment_bottom) // 2
    left = min(max(0, center_x - task_width // 2), width - task_width)
    top = min(max(0, center_y - task_height // 2), height - task_height)
    return left, top, left + task_width, top + task_height


def freeze_workload_records() -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    global_ordinal = 1
    for source in load_performance_sources():
        profile, _warnings = read_tiff_profile(source.source_path, 0)
        height, width = read_tiff_page_shape(source.source_path, 0)
        layout = infer_layout(width, height)
        output_slot_count = _output_slot_count(
            source,
            width=width,
            height=height,
            layout=layout,
        )
        lane_count = format_spec(source.format_id).layout.lane_count
        if output_slot_count % lane_count:
            raise ValueError("benchmark capacity does not divide its lanes")
        lane_slot_count = output_slot_count // lane_count
        source_task_ordinal = 1
        for lane_index in range(lane_count):
            for lane_ordinal in range(1, lane_slot_count + 1):
                left, top, right, bottom = _task_box(
                    width=width,
                    height=height,
                    layout=layout,
                    lane_index=lane_index,
                    lane_count=lane_count,
                    lane_ordinal=lane_ordinal,
                    lane_slot_count=lane_slot_count,
                )
                records.append(
                    {
                        "workload_schema": WORKLOAD_SCHEMA,
                        "workload_ordinal": global_ordinal,
                        "sample_id": source.sample_id,
                        "source_task_ordinal": source_task_ordinal,
                        "source_sha256": source.source_sha256,
                        "source_roi_polygon": [
                            [left, top],
                            [right - 1, top],
                            [right - 1, bottom - 1],
                            [left, bottom - 1],
                        ],
                        "source_to_output_affine": [
                            [1.0, 0.0, float(-left)],
                            [0.0, 1.0, float(-top)],
                            [0.0, 0.0, 1.0],
                        ],
                        "output_extent": {
                            "width": right - left,
                            "height": bottom - top,
                        },
                        "dtype": profile.dtype,
                        "axes": profile.axes,
                        "channels": int(profile.samples_per_pixel),
                        "compression": source.compression,
                        "metadata_profile": {
                            "profile": "benchmark_minimal_source_photometric",
                            "photometric": profile.photometric,
                        },
                    }
                )
                source_task_ordinal += 1
                global_ordinal += 1
    if len(records) != FIXED_WORKLOAD_COUNT:
        raise ValueError(
            "benchmark workload must contain exactly 168 sampling tasks"
        )
    return tuple(records)


def validate_workload_records(
    records: Sequence[dict[str, Any]],
) -> None:
    sources = {
        item.sample_id: item
        for item in load_performance_sources(
            verify_source_files=False,
        )
    }
    if (
        len(records) != FIXED_WORKLOAD_COUNT
        or tuple(
            int(record.get("workload_ordinal", -1))
            for record in records
        )
        != tuple(range(1, FIXED_WORKLOAD_COUNT + 1))
    ):
        raise ValueError("benchmark workload cardinality changed")
    task_ordinals: dict[str, list[int]] = {}
    for record in records:
        sample_id = str(record.get("sample_id", ""))
        source = sources.get(sample_id)
        extent = record.get("output_extent")
        matrix = record.get("source_to_output_affine")
        polygon = record.get("source_roi_polygon")
        if (
            source is None
            or record.get("workload_schema") != WORKLOAD_SCHEMA
            or record.get("source_sha256") != source.source_sha256
            or not isinstance(extent, dict)
            or int(extent.get("width", 0)) <= 0
            or int(extent.get("height", 0)) <= 0
            or not isinstance(matrix, list)
            or len(matrix) != 3
            or not isinstance(polygon, list)
            or len(polygon) != 4
            or record.get("compression") != source.compression
            or record.get("metadata_profile", {}).get("profile")
            != "benchmark_minimal_source_photometric"
        ):
            raise ValueError(
                f"benchmark workload record is invalid: {sample_id}"
            )
        task_ordinals.setdefault(sample_id, []).append(
            int(record["source_task_ordinal"])
        )
    if set(task_ordinals) != set(sources):
        raise ValueError("benchmark workload omitted a source")
    if any(
        ordinals != list(range(1, len(ordinals) + 1))
        for ordinals in task_ordinals.values()
    ):
        raise ValueError("source workload ordinals are not contiguous")


def load_workload_records() -> tuple[dict[str, Any], ...]:
    records = _jsonl(BENCHMARK_WORKLOAD_PATH)
    validate_workload_records(records)
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the tracked status-independent benchmark workload"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BENCHMARK_WORKLOAD_PATH,
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)
    if args.check and args.validate:
        raise SystemExit("--check and --validate are mutually exclusive")
    if args.validate:
        records = load_workload_records()
        encoded = args.output.read_bytes()
        print(
            f"benchmark workload: {len(records)} tracked tasks "
            f"sha256={hashlib.sha256(encoded).hexdigest()}"
        )
        return 0
    records = freeze_workload_records()
    encoded = "".join(
        json.dumps(record, separators=(",", ":")) + "\n"
        for record in records
    )
    if args.check:
        if not args.output.is_file() or args.output.read_text(
            encoding="utf-8"
        ) != encoded:
            raise SystemExit("tracked benchmark workload is not canonical")
    else:
        if args.output.exists():
            raise SystemExit(
                "refusing to overwrite an existing benchmark workload"
            )
        args.output.write_text(encoded, encoding="utf-8")
    print(
        f"benchmark workload: {len(records)} tasks "
        f"sha256={hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
