"""One-version adapter for the status-independent paired benchmark.

The adapter runs native detection/decision without product export, captures
that run's single decoded source array, and then performs only the frozen
benchmark I/O tasks.  Benchmark TIFFs never enter a runtime report or product
manifest.
"""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from threading import Lock
import time
from typing import Any, Callable, Sequence

import numpy as np
import tifffile


ADAPTER_RESULT_SCHEMA = "x5crop_benchmark_adapter_result_v1"


@dataclass(frozen=True)
class AdapterSource:
    sample_id: str
    source_path: Path
    source_sha256: str
    format_id: str
    strip_mode: str
    layout: str
    tasks: tuple[dict[str, Any], ...]


def _load_sources(path: Path) -> tuple[AdapterSource, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("sources")
    if not isinstance(rows, list) or not rows:
        raise ValueError("adapter source manifest is empty")
    sources = tuple(
        AdapterSource(
            sample_id=str(row["sample_id"]),
            source_path=Path(str(row["source_path"])).resolve(),
            source_sha256=str(row["source_sha256"]),
            format_id=str(row["format_id"]),
            strip_mode=str(row["strip_mode"]),
            layout=str(row["layout"]),
            tasks=tuple(row["tasks"]),
        )
        for row in rows
    )
    if len({source.sample_id for source in sources}) != len(sources):
        raise ValueError("adapter source identities must be unique")
    if any(
        not source.source_path.is_file()
        or source.layout not in {"horizontal", "vertical"}
        or not source.tasks
        for source in sources
    ):
        raise ValueError("adapter source manifest is invalid")
    return sources


def _activate_project(project_root: Path) -> None:
    root = str(project_root.resolve())
    for key in tuple(sys.modules):
        if key == "x5crop" or key.startswith("x5crop."):
            del sys.modules[key]
    sys.path[:] = [
        value
        for value in sys.path
        if not value or str(Path(value).resolve()) != root
    ]
    sys.path.insert(0, root)


class _DecodeCapture:
    def __init__(self, original: Callable[..., tuple[Any, ...]]) -> None:
        self.original = original
        self._values: dict[Path, tuple[Any, ...]] = {}
        self._lock = Lock()

    def __call__(self, path: Path, *args: object, **kwargs: object):
        key = Path(path).resolve()
        with self._lock:
            existing = self._values.get(key)
        if existing is not None:
            return existing
        value = self.original(path, *args, **kwargs)
        with self._lock:
            previous = self._values.setdefault(key, value)
        return previous

    def take(self, path: Path) -> tuple[Any, ...]:
        key = path.resolve()
        with self._lock:
            value = self._values.pop(key, None)
        if value is None:
            raise RuntimeError(
                f"native detection did not decode {path.name}"
            )
        return value


class _RuntimeHarness:
    def __init__(
        self,
        project_root: Path,
        version_kind: str,
    ) -> None:
        _activate_project(project_root)
        self.version_kind = version_kind
        if version_kind == "v49":
            from x5crop.runtime.bootstrap import (
                runtime_invocation_from_options,
            )
            from x5crop.runtime.options import RuntimeOptions
            import x5crop.runtime.workflow as workflow

            self.runtime_invocation_from_options = (
                runtime_invocation_from_options
            )
            self.RuntimeOptions = RuntimeOptions
            self.runtime_module = workflow
        elif version_kind == "v428":
            import x5crop.cli as runtime

            self.runtime_module = runtime
        else:
            raise ValueError(f"unsupported benchmark version: {version_kind}")
        original = self.runtime_module.read_tiff
        self.capture = _DecodeCapture(original)
        self.runtime_module.read_tiff = self.capture

    def run_detection(
        self,
        source: AdapterSource,
        output_root: Path,
    ) -> tuple[str, np.ndarray, object, float]:
        detection_root = output_root / "detection" / source.sample_id
        detection_root.mkdir(parents=True, exist_ok=False)
        started = time.perf_counter()
        if self.version_kind == "v49":
            options = self.RuntimeOptions(
                input_path=source.source_path,
                output_dir=detection_root,
                format_id=source.format_id,
                layout=source.layout,
                strip_mode=source.strip_mode,
                requested_count=None,
                page=0,
                review_dir=None,
                copy_review_files=False,
                compression="same",
                debug_analysis=False,
                diagnostics=True,
                overwrite=False,
                report=False,
                debug_errors=True,
                jobs=1,
            )
            invocation = self.runtime_invocation_from_options(options)
            outcome = self.runtime_module.process_one(
                source.source_path,
                invocation.config,
                invocation.configuration_bundle,
            )
            if outcome.__class__.__name__ != "CompletedInput":
                raise RuntimeError(
                    f"{source.sample_id} V4.9 detection did not complete"
                )
            if outcome.artifacts.frame_outputs:
                raise RuntimeError(
                    "V4.9 benchmark detection created product TIFFs"
                )
            status = str(outcome.result.record["decision"]["status"])
        else:
            arguments = [
                str(source.source_path),
                "--output",
                str(detection_root),
                "--format",
                source.format_id,
                "--strip",
                source.strip_mode,
                "--layout",
                source.layout,
                "--compression",
                "same",
                "--dry-run",
                "--no-copy-review-files",
                "--no-reuse-analysis",
                "--jobs",
                "1",
            ]
            parser = self.runtime_module.build_parser()
            config = self.runtime_module.config_from_args(
                parser.parse_args(arguments)
            )
            result = self.runtime_module.process_one(
                source.source_path,
                config,
            )
            if result.output_files:
                raise RuntimeError(
                    "V4.2.8 benchmark detection created product TIFFs"
                )
            status = str(result.status)
        detection_seconds = time.perf_counter() - started
        decoded = self.capture.take(source.source_path)
        array = decoded[0]
        profile = decoded[2] if self.version_kind == "v428" else decoded[1]
        if not isinstance(array, np.ndarray):
            raise RuntimeError("native source decode did not return an array")
        return status, array, profile, detection_seconds


def _spatial_work_array(
    array: np.ndarray,
    axes: str,
) -> np.ndarray:
    try:
        y_axis = axes.index("Y")
        x_axis = axes.index("X")
    except ValueError as exc:
        raise ValueError(f"benchmark source axes are invalid: {axes}") from exc
    return np.moveaxis(array, (y_axis, x_axis), (0, 1))


def _sample_task(
    source: np.ndarray,
    task: dict[str, Any],
) -> np.ndarray:
    extent = task["output_extent"]
    width = int(extent["width"])
    height = int(extent["height"])
    matrix = np.asarray(
        task["source_to_output_affine"],
        dtype=np.float64,
    )
    if matrix.shape != (3, 3) or not np.allclose(
        matrix[2],
        (0.0, 0.0, 1.0),
    ):
        raise ValueError("benchmark affine matrix is invalid")
    inverse = np.linalg.inv(matrix)
    output_y, output_x = np.indices(
        (height, width),
        dtype=np.float64,
    )
    source_x = (
        inverse[0, 0] * output_x
        + inverse[0, 1] * output_y
        + inverse[0, 2]
    )
    source_y = (
        inverse[1, 0] * output_x
        + inverse[1, 1] * output_y
        + inverse[1, 2]
    )
    x0 = np.floor(source_x).astype(np.int64)
    y0 = np.floor(source_y).astype(np.int64)
    x1 = np.minimum(x0 + 1, source.shape[1] - 1)
    y1 = np.minimum(y0 + 1, source.shape[0] - 1)
    if (
        np.any(x0 < 0)
        or np.any(y0 < 0)
        or np.any(x1 >= source.shape[1])
        or np.any(y1 >= source.shape[0])
    ):
        raise ValueError("benchmark affine footprint escaped source authority")
    wx = source_x - x0
    wy = source_y - y0
    extra_dimensions = (1,) * max(0, source.ndim - 2)
    wx = wx.reshape(wx.shape + extra_dimensions)
    wy = wy.reshape(wy.shape + extra_dimensions)
    top = (
        source[y0, x0].astype(np.float64) * (1.0 - wx)
        + source[y0, x1].astype(np.float64) * wx
    )
    bottom = (
        source[y1, x0].astype(np.float64) * (1.0 - wx)
        + source[y1, x1].astype(np.float64) * wx
    )
    sampled = top * (1.0 - wy) + bottom * wy
    if np.issubdtype(source.dtype, np.integer):
        limits = np.iinfo(source.dtype)
        sampled = np.clip(
            np.rint(sampled),
            limits.min,
            limits.max,
        )
    return sampled.astype(source.dtype)


def _write_and_readback(
    sampled: np.ndarray,
    task: dict[str, Any],
    path: Path,
) -> int:
    metadata_profile = task["metadata_profile"]
    photometric = str(metadata_profile["photometric"]).lower()
    if sampled.ndim > 2 and sampled.shape[-1] >= 3:
        photometric = "rgb"
    elif photometric not in {"minisblack", "miniswhite"}:
        photometric = "minisblack"
    compression_name = str(task["compression"]).upper()
    compression = None if compression_name == "NONE" else compression_name.lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        path,
        sampled,
        photometric=photometric,
        compression=compression,
        metadata=None,
    )
    readback = tifffile.imread(path)
    if (
        readback.shape != sampled.shape
        or readback.dtype != sampled.dtype
        or not np.array_equal(readback, sampled)
    ):
        raise RuntimeError(f"benchmark TIFF readback failed: {path}")
    return path.stat().st_size


def _run_source(
    harness: _RuntimeHarness,
    source: AdapterSource,
    output_root: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    status, array, profile, detection_seconds = harness.run_detection(
        source,
        output_root,
    )
    axes = str(profile.axes)
    work_array = _spatial_work_array(array, axes)
    workload_started = time.perf_counter()
    sampled_pixels = 0
    output_bytes = 0
    benchmark_root = (
        output_root / "benchmark-only" / source.sample_id
    )
    for task in source.tasks:
        if (
            str(task["source_sha256"]) != source.source_sha256
            or str(task["dtype"]) != str(array.dtype)
        ):
            raise ValueError("benchmark task identity disagrees with source")
        sampled = _sample_task(work_array, task)
        sampled_pixels += int(
            sampled.shape[0] * sampled.shape[1]
        )
        output_bytes += _write_and_readback(
            sampled,
            task,
            benchmark_root
            / f"workload_{int(task['workload_ordinal']):04d}.tif",
        )
    workload_seconds = time.perf_counter() - workload_started
    return {
        "sample_id": source.sample_id,
        "source_sha256": source.source_sha256,
        "decision_status": status,
        "detection_decision_seconds": detection_seconds,
        "benchmark_io_seconds": workload_seconds,
        "total_seconds": time.perf_counter() - started,
        "workload_task_count": len(source.tasks),
        "sampled_output_pixels": sampled_pixels,
        "benchmark_output_bytes": output_bytes,
        "source_decode_count": 1,
        "official_product_tiff_count": 0,
    }


def run_adapter(
    *,
    project_root: Path,
    version_kind: str,
    source_manifest: Path,
    output_root: Path,
    jobs: int,
) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"adapter output root must be empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    sources = _load_sources(source_manifest)
    harness = _RuntimeHarness(project_root, version_kind)
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(2, jobs))
    ) as executor:
        records = tuple(
            executor.map(
                lambda source: _run_source(
                    harness,
                    source,
                    output_root,
                ),
                sources,
            )
        )
    result = {
        "adapter_result_schema": ADAPTER_RESULT_SCHEMA,
        "version_kind": version_kind,
        "jobs": max(1, min(2, jobs)),
        "source_count": len(sources),
        "workload_task_count": sum(
            record["workload_task_count"] for record in records
        ),
        "source_decode_count": sum(
            record["source_decode_count"] for record in records
        ),
        "official_product_tiff_count": sum(
            record["official_product_tiff_count"]
            for record in records
        ),
        "adapter_wall_seconds": time.perf_counter() - started,
        "sources": list(records),
        "completed": True,
    }
    (output_root / "adapter_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one side of the paired V4.2.8/V4.9 benchmark"
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument(
        "--version-kind",
        choices=("v428", "v49"),
        required=True,
    )
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args(argv)
    result = run_adapter(
        project_root=args.project_root.resolve(),
        version_kind=args.version_kind,
        source_manifest=args.source_manifest.resolve(),
        output_root=args.output_root.resolve(),
        jobs=args.jobs,
    )
    if (
        result["source_count"] <= 0
        or result["source_decode_count"] != result["source_count"]
        or result["official_product_tiff_count"] != 0
        or not math.isfinite(result["adapter_wall_seconds"])
    ):
        raise SystemExit("benchmark adapter contract failed")
    print(
        f"{args.version_kind}: {result['source_count']} sources, "
        f"{result['workload_task_count']} benchmark tasks, "
        f"{result['adapter_wall_seconds']:.3f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
