"""Run the fixed status-independent V4.2.8/V4.9 paired benchmark."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from typing import Any, Sequence

from x5crop.geometry.layout import infer_layout
from x5crop.io.tiff import read_tiff_page_shape

from .benchmark_adapter import ADAPTER_RESULT_SCHEMA
from .benchmark_workload import (
    BENCHMARK_WORKLOAD_PATH,
    FIXED_SOURCE_COUNT,
    FIXED_WORKLOAD_COUNT,
    PERFORMANCE_COHORT_PATH,
    PROJECT_ROOT,
    file_sha256,
    load_performance_sources,
    load_workload_records,
)


PERFORMANCE_RESULT_SCHEMA = "x5crop_paired_performance_v1"
BASELINE_TAG = "v4.2.8"
BASELINE_COMMIT = "8d14c55d8af5c944a0b78b51df4c4c428e606f07"
PRODUCTION_JOBS = 2
SECONDS_PER_INPUT_LIMIT = 5.0
PAIRED_ORDERS = (
    ("v428", "v49"),
    ("v49", "v428"),
    ("v428", "v49"),
)
ADAPTER_PATH = Path(__file__).with_name("benchmark_adapter.py")
CONTROLLER_PATH = Path(__file__)


@dataclass(frozen=True)
class VersionRunTiming:
    label: str
    version_kind: str
    wall_seconds: float
    adapter_result: dict[str, Any]

    @property
    def seconds_per_input(self) -> float:
        return self.wall_seconds / FIXED_SOURCE_COUNT

    def as_record(self) -> dict[str, Any]:
        sources = self.adapter_result["sources"]
        return {
            "label": self.label,
            "version_kind": self.version_kind,
            "wall_seconds": self.wall_seconds,
            "seconds_per_input": self.seconds_per_input,
            "source_count": self.adapter_result["source_count"],
            "workload_task_count": self.adapter_result[
                "workload_task_count"
            ],
            "source_decode_count": self.adapter_result[
                "source_decode_count"
            ],
            "official_product_tiff_count": self.adapter_result[
                "official_product_tiff_count"
            ],
            "diagnostic_breakdown": {
                "summed_detection_decision_seconds": sum(
                    item["detection_decision_seconds"]
                    for item in sources
                ),
                "summed_benchmark_io_seconds": sum(
                    item["benchmark_io_seconds"] for item in sources
                ),
                "sampled_output_pixels": sum(
                    item["sampled_output_pixels"] for item in sources
                ),
                "benchmark_output_bytes": sum(
                    item["benchmark_output_bytes"] for item in sources
                ),
                "approved_auto_count": sum(
                    item["decision_status"] == "approved_auto"
                    for item in sources
                ),
                "needs_review_count": sum(
                    item["decision_status"] == "needs_review"
                    for item in sources
                ),
            },
        }


@dataclass(frozen=True)
class PairedRunGroup:
    group_ordinal: int
    order: tuple[str, str]
    v428: VersionRunTiming
    v49: VersionRunTiming

    @property
    def relative_difference(self) -> float:
        return (
            self.v49.wall_seconds - self.v428.wall_seconds
        ) / self.v428.wall_seconds

    def as_record(self) -> dict[str, Any]:
        return {
            "group_ordinal": self.group_ordinal,
            "order": list(self.order),
            "v428": self.v428.as_record(),
            "v49": self.v49.as_record(),
            "relative_difference": self.relative_difference,
        }


def _mad(values: Sequence[float]) -> float:
    median = statistics.median(values)
    return statistics.median(abs(value - median) for value in values)


@dataclass(frozen=True)
class PairedPerformanceResult:
    output_root: Path
    baseline_commit: str
    v49_commit: str
    workload_sha256: str
    controller_sha256: str
    adapter_sha256: str
    source_manifest_sha256: str
    source_sha256s: tuple[str, ...]
    warmups: tuple[VersionRunTiming, VersionRunTiming]
    groups: tuple[PairedRunGroup, ...]
    environment: dict[str, Any]

    def __post_init__(self) -> None:
        if (
            self.baseline_commit != BASELINE_COMMIT
            or len(self.source_sha256s) != FIXED_SOURCE_COUNT
            or len(self.groups) != len(PAIRED_ORDERS)
            or tuple(group.order for group in self.groups)
            != PAIRED_ORDERS
        ):
            raise ValueError("paired performance identity is invalid")
        for run in (
            *self.warmups,
            *(
                timing
                for group in self.groups
                for timing in (group.v428, group.v49)
            ),
        ):
            adapter = run.adapter_result
            if (
                adapter.get("adapter_result_schema")
                != ADAPTER_RESULT_SCHEMA
                or adapter.get("source_count") != FIXED_SOURCE_COUNT
                or adapter.get("workload_task_count")
                != FIXED_WORKLOAD_COUNT
                or adapter.get("source_decode_count")
                != FIXED_SOURCE_COUNT
                or adapter.get("official_product_tiff_count") != 0
                or adapter.get("completed") is not True
            ):
                raise ValueError("paired adapter run is incomplete")

    @property
    def v49_times(self) -> tuple[float, ...]:
        return tuple(group.v49.wall_seconds for group in self.groups)

    @property
    def v428_times(self) -> tuple[float, ...]:
        return tuple(group.v428.wall_seconds for group in self.groups)

    @property
    def median_v49_seconds_per_input(self) -> float:
        return statistics.median(self.v49_times) / FIXED_SOURCE_COUNT

    @property
    def relative_differences(self) -> tuple[float, ...]:
        return tuple(
            group.relative_difference for group in self.groups
        )

    @property
    def noise_floor(self) -> float:
        v49_median = statistics.median(self.v49_times)
        v428_median = statistics.median(self.v428_times)
        return max(
            0.01,
            _mad(self.v49_times) / v49_median,
            _mad(self.v428_times) / v428_median,
        )

    @property
    def absolute_passed(self) -> bool:
        return (
            self.median_v49_seconds_per_input
            <= SECONDS_PER_INPUT_LIMIT
        )

    @property
    def relative_passed(self) -> bool:
        return (
            statistics.median(self.relative_differences)
            < -self.noise_floor
        )

    @property
    def passed(self) -> bool:
        return self.absolute_passed and self.relative_passed

    def as_record(self) -> dict[str, Any]:
        return {
            "performance_schema": PERFORMANCE_RESULT_SCHEMA,
            "baseline": {
                "tag": BASELINE_TAG,
                "commit": self.baseline_commit,
            },
            "v49_commit": self.v49_commit,
            "jobs": PRODUCTION_JOBS,
            "source_count": FIXED_SOURCE_COUNT,
            "workload_task_count": FIXED_WORKLOAD_COUNT,
            "compression": "same",
            "count_mapping": {
                "v49_full": "native_fixed_full",
                "v49_partial": "--count auto",
                "v428_full": "native_fixed_full",
                "v428_partial": "no --count argument",
            },
            "product_export_policy": (
                "native_detection_decision_then_benchmark_only_io"
            ),
            "status_filtering": False,
            "identity": {
                "workload_manifest_sha256": self.workload_sha256,
                "controller_sha256": self.controller_sha256,
                "adapter_sha256": self.adapter_sha256,
                "source_manifest_sha256": self.source_manifest_sha256,
                "source_sha256s": list(self.source_sha256s),
            },
            "environment": self.environment,
            "warmups": [item.as_record() for item in self.warmups],
            "paired_groups": [
                group.as_record() for group in self.groups
            ],
            "v49_median_seconds_per_input": (
                self.median_v49_seconds_per_input
            ),
            "seconds_per_input_limit": SECONDS_PER_INPUT_LIMIT,
            "relative_differences": list(
                self.relative_differences
            ),
            "relative_difference_median": statistics.median(
                self.relative_differences
            ),
            "noise_floor": self.noise_floor,
            "relative_requirement": "median(d_j) < -noise_floor",
            "absolute_passed": self.absolute_passed,
            "relative_passed": self.relative_passed,
            "passed": self.passed,
        }


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _prepare_baseline_worktree(path: Path) -> None:
    tag_commit = _git("rev-parse", f"{BASELINE_TAG}^{{commit}}")
    if tag_commit != BASELINE_COMMIT:
        raise RuntimeError("V4.2.8 tag no longer resolves to the frozen commit")
    if path.exists():
        actual = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=path,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        if actual != BASELINE_COMMIT:
            raise RuntimeError("existing V4.2.8 worktree has the wrong commit")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        (
            "git",
            "worktree",
            "add",
            "--detach",
            str(path),
            BASELINE_COMMIT,
        ),
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"cannot create V4.2.8 worktree: {completed.stdout.strip()}"
        )


def _source_manifest(output_root: Path) -> tuple[Path, str, tuple[str, ...]]:
    sources = load_performance_sources()
    tasks = load_workload_records()
    tasks_by_sample: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_sample.setdefault(str(task["sample_id"]), []).append(task)
    rows = []
    source_sha256s = []
    for source in sources:
        height, width = read_tiff_page_shape(source.source_path, 0)
        rows.append(
            {
                "sample_id": source.sample_id,
                "source_path": str(source.source_path.resolve()),
                "source_sha256": source.source_sha256,
                "format_id": source.format_id,
                "strip_mode": source.strip_mode,
                "layout": infer_layout(width, height),
                "tasks": tasks_by_sample[source.sample_id],
            }
        )
        source_sha256s.append(source.source_sha256)
    payload = {
        "manifest_schema": "x5crop_benchmark_source_manifest_v1",
        "sources": rows,
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    )
    path = output_root / "controller" / "source_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
    return (
        path,
        hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        tuple(source_sha256s),
    )


def _environment_record() -> dict[str, Any]:
    dependencies = {}
    for name in ("numpy", "tifffile", "imagecodecs", "Pillow"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "unavailable"
    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependencies": dependencies,
    }


def _run_version(
    *,
    label: str,
    version_kind: str,
    project_root: Path,
    source_manifest: Path,
    run_root: Path,
) -> VersionRunTiming:
    output_root = run_root / version_kind
    if output_root.exists():
        raise ValueError(f"benchmark run root is not fresh: {output_root}")
    command = (
        sys.executable,
        str(ADAPTER_PATH),
        "--project-root",
        str(project_root),
        "--version-kind",
        version_kind,
        "--source-manifest",
        str(source_manifest),
        "--output-root",
        str(output_root),
        "--jobs",
        str(PRODUCTION_JOBS),
    )
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wall_seconds = time.perf_counter() - started
    if completed.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit {completed.returncode}: "
            f"{completed.stdout[-4000:]}"
        )
    result_path = output_root / "adapter_result.json"
    if not result_path.is_file():
        raise RuntimeError(f"{label} produced no adapter result")
    adapter_result = json.loads(result_path.read_text(encoding="utf-8"))
    return VersionRunTiming(
        label=label,
        version_kind=version_kind,
        wall_seconds=wall_seconds,
        adapter_result=adapter_result,
    )


def run_paired_performance(output_root: Path) -> PairedPerformanceResult:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"benchmark root must be empty: {output_root}")
    if _git("status", "--porcelain"):
        raise ValueError(
            "formal paired performance requires a clean committed V4.9 tree"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    baseline_worktree = output_root / "v428-worktree"
    _prepare_baseline_worktree(baseline_worktree)
    source_manifest, source_manifest_sha, source_shas = (
        _source_manifest(output_root)
    )
    v49_commit = _git("rev-parse", "HEAD")
    runs_root = output_root / "runs"
    warmup_v428 = _run_version(
        label="warmup-v428",
        version_kind="v428",
        project_root=baseline_worktree,
        source_manifest=source_manifest,
        run_root=runs_root / "warmup-v428",
    )
    warmup_v49 = _run_version(
        label="warmup-v49",
        version_kind="v49",
        project_root=PROJECT_ROOT,
        source_manifest=source_manifest,
        run_root=runs_root / "warmup-v49",
    )
    groups: list[PairedRunGroup] = []
    for group_ordinal, order in enumerate(PAIRED_ORDERS, 1):
        timings: dict[str, VersionRunTiming] = {}
        for sequence_ordinal, version_kind in enumerate(order, 1):
            timings[version_kind] = _run_version(
                label=(
                    f"group-{group_ordinal}-"
                    f"{sequence_ordinal}-{version_kind}"
                ),
                version_kind=version_kind,
                project_root=(
                    baseline_worktree
                    if version_kind == "v428"
                    else PROJECT_ROOT
                ),
                source_manifest=source_manifest,
                run_root=(
                    runs_root
                    / f"group-{group_ordinal}"
                    / f"{sequence_ordinal}-{version_kind}"
                ),
            )
        groups.append(
            PairedRunGroup(
                group_ordinal=group_ordinal,
                order=order,
                v428=timings["v428"],
                v49=timings["v49"],
            )
        )
    result = PairedPerformanceResult(
        output_root=output_root,
        baseline_commit=BASELINE_COMMIT,
        v49_commit=v49_commit,
        workload_sha256=file_sha256(BENCHMARK_WORKLOAD_PATH),
        controller_sha256=file_sha256(CONTROLLER_PATH),
        adapter_sha256=file_sha256(ADAPTER_PATH),
        source_manifest_sha256=source_manifest_sha,
        source_sha256s=source_shas,
        warmups=(warmup_v428, warmup_v49),
        groups=tuple(groups),
        environment=_environment_record(),
    )
    (output_root / "paired_performance_result.json").write_text(
        json.dumps(
            result.as_record(),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen status-independent paired benchmark"
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=(
            PROJECT_ROOT
            / "build"
            / "v49-photo-geometry"
            / "benchmark"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_paired_performance(args.output_root.resolve())
    record = result.as_record()
    print(
        f"V4.9 median: "
        f"{record['v49_median_seconds_per_input']:.3f}s/input "
        f"(limit {SECONDS_PER_INPUT_LIMIT:.1f})"
    )
    print(
        f"paired median difference: "
        f"{record['relative_difference_median']:.3%}; "
        f"noise floor {record['noise_floor']:.3%}"
    )
    print("performance: PASS" if result.passed else "performance: FAIL")
    print(f"artifacts: {result.output_root}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
