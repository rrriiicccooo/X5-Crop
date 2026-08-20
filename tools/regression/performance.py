"""Measure the 24-source V5 production path and freeze its receipt."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from x5crop.report.validation import validate_current_report_record
from tools.install.dependency_manager import load_dependency_contract
from .environment_identity import verification_environment_identity

from .performance_identity import (
    FIXED_SOURCE_COUNT,
    PROJECT_ROOT,
    cohort_sha256,
    load_performance_sources,
)
from .performance_hardware import build_hardware_identity
from .performance_profile import (
    STAGE_NAMES,
    ProfiledSource,
    profile_source,
    run_with_peak_rss,
)


PERFORMANCE_RECEIPT_SCHEMA = "x5crop_performance_receipt_v5_4"
DEFAULT_RECEIPT_PATH = (
    PROJECT_ROOT / "build" / "v5-performance" / "performance_receipt.json"
)
SECONDS_PER_INPUT_LIMIT = 5.0
SECONDS_PER_INPUT_CHALLENGE = 3.0
FROZEN_CONTRACT_PATH = PROJECT_ROOT / "tools/install/dependencies.toml"
PRODUCTION_TIMING_BOUNDARY = (
    "production_cli_startup_decode_detection_decision_sampling_"
    "compression_write_readback_publish"
)
PRODUCTION_RSS_METHOD = "external_uninstrumented_subprocess_peak_rss"
PROFILING_METHOD = "external_cprofile_subprocess_peak_rss"


def frozen_dependency_identity() -> dict[str, dict[str, str]]:
    contract = load_dependency_contract(FROZEN_CONTRACT_PATH)
    return {
        pin.name: {
            "module": pin.module,
            "module_version": pin.module_version,
        }
        for pin in contract.dependencies
    }


def _dependencies_are_frozen(dependencies: object) -> bool:
    expected = frozen_dependency_identity()
    if not isinstance(dependencies, dict) or set(dependencies) != set(expected):
        return False
    for name, required in expected.items():
        actual = dependencies.get(name)
        if not isinstance(actual, dict):
            return False
        if (
            actual.get("module") != required["module"]
            or actual.get("module_version") != required["module_version"]
            or actual.get("provider") not in {"homebrew", "pip", "external"}
            or not str(actual.get("package", ""))
            or not str(actual.get("package_version", ""))
            or not str(actual.get("module_origin", ""))
        ):
            return False
    return True


def performance_environment_is_frozen(environment: object) -> bool:
    if not isinstance(environment, dict):
        return False
    dependencies = environment.get("dependencies")
    threads = environment.get("threads")
    python_version = str(environment.get("python_version", ""))
    try:
        major, minor, *_rest = (int(part) for part in python_version.split("."))
    except ValueError:
        return False
    if not isinstance(threads, dict):
        return False
    thread_environment = threads.get("environment")
    return (
        (major, minor) in {(3, 12), (3, 13), (3, 14)}
        and environment.get("platform_system") in {"Darwin", "Windows", "Linux"}
        and _dependencies_are_frozen(dependencies)
        and threads.get("x5crop_source_workers") == "--jobs"
        and threads.get("opencv_threads") == 1
        and isinstance(thread_environment, dict)
        and thread_environment
        and all(value == "1" for value in thread_environment.values())
    )


def require_frozen_performance_environment(
    environment: dict[str, Any],
) -> None:
    if not performance_environment_is_frozen(environment):
        raise ValueError(
            "performance receipt requires the frozen Python, dependency, "
            "and single-thread environment"
        )


@dataclass(frozen=True)
class SourceTiming:
    sample_id: str
    wall_seconds: float
    process_peak_rss_bytes: int
    status: str
    output_tiff_count: int
    output_bytes: int

    def as_record(self) -> dict[str, object]:
        return {
            "sample_id": self.sample_id,
            "wall_seconds": self.wall_seconds,
            "process_peak_rss_bytes": self.process_peak_rss_bytes,
            "status": self.status,
            "output_tiff_count": self.output_tiff_count,
            "output_bytes": self.output_bytes,
        }


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _clean_commit() -> str:
    if _git("status", "--porcelain"):
        raise ValueError("performance receipt requires a clean committed tree")
    commit = _git("rev-parse", "HEAD")
    if len(commit) != 40:
        raise ValueError("performance receipt requires one Git commit")
    return commit


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _run_source(source) -> SourceTiming:
    with TemporaryDirectory(prefix="x5crop-performance-") as temporary:
        output = Path(temporary) / "x5_crop_output"
        command = [
            sys.executable,
            str(PROJECT_ROOT / "X5_Crop.py"),
            str(source.source_path),
            "--output",
            str(output),
            "--format",
            source.format_id,
            "--count",
            str(source.count),
            "--jobs",
            "1",
        ]
        wall, peak_rss, process_output, returncode = run_with_peak_rss(command)
        if returncode != 0:
            raise ValueError(
                f"{source.sample_id} production path failed:\n"
                + process_output[-4000:]
            )
        report_path = output / "x5_crop_report.jsonl"
        rows = tuple(
            json.loads(line)
            for line in report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if len(rows) != 1:
            raise ValueError(f"{source.sample_id} lacks one terminal report")
        report = rows[0]
        validate_current_report_record(report)
        status = str(report["decision"]["status"])
        files = tuple(output.rglob("*.tif"))
        return SourceTiming(
            sample_id=source.sample_id,
            wall_seconds=wall,
            process_peak_rss_bytes=peak_rss,
            status=status,
            output_tiff_count=len(files),
            output_bytes=sum(path.stat().st_size for path in files),
        )


def _named_summary(values: Sequence[float], names: Sequence[str]) -> dict[str, object]:
    maximum = max(values)
    index = values.index(maximum)
    return {
        "mean": statistics.fmean(values),
        "maximum": maximum,
        "maximum_source": names[index],
    }


def _profiling_summary(profiles: Sequence[ProfiledSource]) -> dict[str, object]:
    sample_ids = [item.sample_id for item in profiles]
    wall = [item.wall_seconds for item in profiles]
    rss = [float(item.process_peak_rss_bytes) for item in profiles]
    temporary = [float(item.runtime_peak_temporary_bytes) for item in profiles]
    stages = {
        name: _named_summary(
            [item.stages[name] for item in profiles],
            sample_ids,
        )
        for name in STAGE_NAMES
    }
    stages["io_total"] = _named_summary(
        [item.io_total_seconds for item in profiles],
        sample_ids,
    )
    return {
        "wall_p50_seconds": statistics.median(wall),
        "wall_p95_seconds": _percentile(wall, 0.95),
        "slowest_source": sample_ids[wall.index(max(wall))],
        "slowest_seconds": max(wall),
        "process_peak_rss_bytes": _named_summary(rss, sample_ids),
        "runtime_peak_temporary_bytes": _named_summary(temporary, sample_ids),
        "stages": stages,
    }


def build_receipt() -> dict[str, Any]:
    commit = _clean_commit()
    environment = verification_environment_identity()
    require_frozen_performance_environment(environment)
    # Full TIFF SHA validation deliberately completes before product timing.
    sources = load_performance_sources(verify_source_files=True)
    hardware = build_hardware_identity(sources[0].source_path.parent)
    timings: list[SourceTiming] = []
    for source in sources:
        timing = _run_source(source)
        timings.append(timing)
        print(f"{source.sample_id}: {timing.wall_seconds:.3f}s {timing.status}")
    wall = tuple(item.wall_seconds for item in timings)
    rss = tuple(float(item.process_peak_rss_bytes) for item in timings)
    mean = statistics.fmean(wall)
    profiles: list[ProfiledSource] = []
    for source in sources:
        profile = profile_source(source)
        profiles.append(profile)
        print(
            f"{source.sample_id}: profile={profile.wall_seconds:.3f}s "
            f"rss={profile.process_peak_rss_bytes}"
        )
    return {
        "receipt_schema": PERFORMANCE_RECEIPT_SCHEMA,
        "git_commit": commit,
        "cohort_sha256": cohort_sha256(),
        "source_count": len(sources),
        "source_sha256s": [item.source_sha256 for item in sources],
        "environment": environment,
        "hardware": hardware,
        "production_gate": {
            "timing_boundary": PRODUCTION_TIMING_BOUNDARY,
            "rss_method": PRODUCTION_RSS_METHOD,
            "sha_validation_in_timing": False,
            "debug_analysis_in_timing": False,
            "summary": {
                "mean_seconds_per_input": mean,
                "p50_seconds": statistics.median(wall),
                "p95_seconds": _percentile(wall, 0.95),
                "slowest_source": timings[wall.index(max(wall))].sample_id,
                "slowest_seconds": max(wall),
                "seconds_per_input_limit": SECONDS_PER_INPUT_LIMIT,
                "passed": mean <= SECONDS_PER_INPUT_LIMIT,
                "process_peak_rss_bytes": _named_summary(
                    rss,
                    [item.sample_id for item in timings],
                ),
            },
            "nonblocking_challenge": {
                "seconds_per_input": SECONDS_PER_INPUT_CHALLENGE,
                "achieved": mean <= SECONDS_PER_INPUT_CHALLENGE,
                "participates_in_gate": False,
            },
            "sources": [item.as_record() for item in timings],
        },
        "profiling": {
            "method": PROFILING_METHOD,
            "participates_in_speed_gate": False,
            "stage_names": list(STAGE_NAMES),
            "summary": _profiling_summary(profiles),
            "sources": [item.as_record() for item in profiles],
        },
    }


def _records_equivalent(actual: object, expected: object) -> bool:
    """Compare a parsed receipt with a freshly derived deterministic summary."""

    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(
                _records_equivalent(actual[key], value)
                for key, value in expected.items()
            )
        )
    if isinstance(expected, float):
        try:
            value = float(actual)
        except (TypeError, ValueError):
            return False
        return math.isfinite(value) and math.isclose(
            value,
            expected,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    return actual == expected


def _invalid_receipt() -> ValueError:
    return ValueError("performance receipt identity or Gate is invalid")


def validate_receipt(
    record: dict[str, Any],
    *,
    expected_commit: str | None = None,
) -> None:
    sources = load_performance_sources(verify_source_files=False)
    expected_sample_ids = [item.sample_id for item in sources]
    production = record.get("production_gate")
    profiling = record.get("profiling")
    hardware = record.get("hardware")
    commit = str(record.get("git_commit", ""))
    if (
        set(record)
        != {
            "receipt_schema",
            "git_commit",
            "cohort_sha256",
            "source_count",
            "source_sha256s",
            "environment",
            "hardware",
            "production_gate",
            "profiling",
        }
        or record.get("receipt_schema") != PERFORMANCE_RECEIPT_SCHEMA
        or len(commit) != 40
        or (expected_commit is not None and commit != expected_commit)
        or record.get("source_count") != FIXED_SOURCE_COUNT
        or record.get("cohort_sha256") != cohort_sha256()
        or record.get("source_sha256s")
        != [item.source_sha256 for item in sources]
        or not performance_environment_is_frozen(record.get("environment"))
        or not isinstance(hardware, dict)
        or set(hardware)
        != {
            "machine_name",
            "cpu_model",
            "physical_core_count",
            "logical_core_count",
            "total_memory_bytes",
            "input_volume",
            "output_volume",
            "power",
            "windows_defender",
        }
        or not str(hardware.get("machine_name", ""))
        or not str(hardware.get("cpu_model", ""))
        or not isinstance(hardware.get("physical_core_count"), int)
        or int(hardware.get("physical_core_count", 0)) <= 0
        or not isinstance(hardware.get("logical_core_count"), int)
        or int(hardware.get("logical_core_count", 0)) <= 0
        or int(hardware.get("total_memory_bytes", 0)) <= 0
        or not isinstance(production, dict)
        or set(production)
        != {
            "timing_boundary",
            "rss_method",
            "sha_validation_in_timing",
            "debug_analysis_in_timing",
            "summary",
            "nonblocking_challenge",
            "sources",
        }
        or production.get("timing_boundary") != PRODUCTION_TIMING_BOUNDARY
        or production.get("rss_method") != PRODUCTION_RSS_METHOD
        or production.get("sha_validation_in_timing") is not False
        or production.get("debug_analysis_in_timing") is not False
        or not isinstance(profiling, dict)
        or set(profiling)
        != {
            "method",
            "participates_in_speed_gate",
            "stage_names",
            "summary",
            "sources",
        }
        or profiling.get("method") != PROFILING_METHOD
        or profiling.get("participates_in_speed_gate") is not False
        or profiling.get("stage_names") != list(STAGE_NAMES)
    ):
        raise _invalid_receipt()

    try:
        raw_timings = production["sources"]
        if not isinstance(raw_timings, list):
            raise TypeError
        timings = tuple(
            SourceTiming(
                sample_id=str(item["sample_id"]),
                wall_seconds=float(item["wall_seconds"]),
                process_peak_rss_bytes=int(item["process_peak_rss_bytes"]),
                status=str(item["status"]),
                output_tiff_count=int(item["output_tiff_count"]),
                output_bytes=int(item["output_bytes"]),
            )
            for item in raw_timings
        )
        raw_profiles = profiling["sources"]
        if not isinstance(raw_profiles, list):
            raise TypeError
        profiles = tuple(
            ProfiledSource(
                sample_id=str(item["sample_id"]),
                wall_seconds=float(item["wall_seconds"]),
                stages={
                    str(name): float(value)
                    for name, value in item["stages"].items()
                },
                io_total_seconds=float(item["io_total_seconds"]),
                process_peak_rss_bytes=int(item["process_peak_rss_bytes"]),
                runtime_peak_temporary_bytes=int(
                    item["runtime_peak_temporary_bytes"]
                ),
            )
            for item in raw_profiles
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _invalid_receipt() from exc

    timing_keys = {
        "sample_id",
        "wall_seconds",
        "process_peak_rss_bytes",
        "status",
        "output_tiff_count",
        "output_bytes",
    }
    profile_keys = {
        "sample_id",
        "wall_seconds",
        "stages",
        "io_total_seconds",
        "process_peak_rss_bytes",
        "runtime_peak_temporary_bytes",
    }
    if (
        len(timings) != FIXED_SOURCE_COUNT
        or [item.sample_id for item in timings] != expected_sample_ids
        or any(set(item) != timing_keys for item in raw_timings)
        or any(
            not math.isfinite(item.wall_seconds)
            or item.wall_seconds <= 0.0
            or item.process_peak_rss_bytes <= 0
            or item.status not in {"approved_auto", "needs_review"}
            or item.output_bytes <= 0
            or (
                item.status == "approved_auto"
                and item.output_tiff_count != source.count
            )
            or (
                item.status == "needs_review"
                and item.output_tiff_count != 1
            )
            for item, source in zip(timings, sources, strict=True)
        )
        or len(profiles) != FIXED_SOURCE_COUNT
        or [item.sample_id for item in profiles] != expected_sample_ids
        or any(set(item) != profile_keys for item in raw_profiles)
        or any(
            set(item.stages) != set(STAGE_NAMES)
            or not math.isfinite(item.wall_seconds)
            or item.wall_seconds <= 0.0
            or any(
                not math.isfinite(value) or value < 0.0
                for value in item.stages.values()
            )
            or not math.isfinite(item.io_total_seconds)
            or item.io_total_seconds < 0.0
            or item.process_peak_rss_bytes <= 0
            or item.runtime_peak_temporary_bytes < 0
            for item in profiles
        )
    ):
        raise _invalid_receipt()

    wall = tuple(item.wall_seconds for item in timings)
    mean = statistics.fmean(wall)
    expected_summary = {
        "mean_seconds_per_input": mean,
        "p50_seconds": statistics.median(wall),
        "p95_seconds": _percentile(wall, 0.95),
        "slowest_source": timings[wall.index(max(wall))].sample_id,
        "slowest_seconds": max(wall),
        "seconds_per_input_limit": SECONDS_PER_INPUT_LIMIT,
        "passed": mean <= SECONDS_PER_INPUT_LIMIT,
        "process_peak_rss_bytes": _named_summary(
            tuple(float(item.process_peak_rss_bytes) for item in timings),
            expected_sample_ids,
        ),
    }
    expected_challenge = {
        "seconds_per_input": SECONDS_PER_INPUT_CHALLENGE,
        "achieved": mean <= SECONDS_PER_INPUT_CHALLENGE,
        "participates_in_gate": False,
    }
    if (
        expected_summary["passed"] is not True
        or not _records_equivalent(production["summary"], expected_summary)
        or not _records_equivalent(
            production["nonblocking_challenge"],
            expected_challenge,
        )
        or not _records_equivalent(
            profiling["summary"],
            _profiling_summary(profiles),
        )
    ):
        raise _invalid_receipt()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--check-receipt", type=Path)
    parser.add_argument("--expected-commit")
    args = parser.parse_args(argv)
    if args.check_receipt is not None:
        record = json.loads(args.check_receipt.read_text(encoding="utf-8"))
        validate_receipt(record, expected_commit=args.expected_commit)
        print(f"performance receipt valid: {args.check_receipt}")
        return 0
    if args.expected_commit is not None:
        parser.error("--expected-commit requires --check-receipt")
    record = build_receipt()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    validate_receipt(record, expected_commit=str(record["git_commit"]))
    print(f"performance receipt: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
