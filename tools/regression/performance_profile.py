"""Profile production CLI stage boundaries without production instrumentation."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import pstats
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Any

from x5crop.report.validation import validate_current_report_record


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE_NAMES = (
    "startup_import_unattributed",
    "decode",
    "workspace_gray",
    "coarse_support",
    "registered_measurement",
    "template_alignment_decision",
    "sampling",
    "encode_write",
    "readback",
    "publish",
)


@dataclass(frozen=True)
class ProfiledSource:
    sample_id: str
    wall_seconds: float
    stages: dict[str, float]
    io_total_seconds: float
    process_peak_rss_bytes: int
    runtime_peak_temporary_bytes: int

    def as_record(self) -> dict[str, object]:
        return {
            "sample_id": self.sample_id,
            "wall_seconds": self.wall_seconds,
            "stages": dict(self.stages),
            "io_total_seconds": self.io_total_seconds,
            "process_peak_rss_bytes": self.process_peak_rss_bytes,
            "runtime_peak_temporary_bytes": self.runtime_peak_temporary_bytes,
        }


def _windows_rss_bytes(pid: int) -> int:
    from ctypes import wintypes

    process_query_information = 0x0400
    process_vm_read = 0x0010

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_information | process_vm_read,
        False,
        pid,
    )
    if not handle:
        return 0
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            return 0
        return int(counters.PeakWorkingSetSize)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _process_rss_bytes(pid: int) -> int:
    if os.name == "nt":
        return _windows_rss_bytes(pid)
    try:
        completed = subprocess.run(
            ("ps", "-o", "rss=", "-p", str(pid)),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return int(completed.stdout.strip()) * 1024
    except (OSError, ValueError, subprocess.CalledProcessError):
        return 0


def run_with_peak_rss(command: list[str]) -> tuple[float, int, str, int]:
    """Run one CLI subprocess and observe wall time plus process peak RSS."""

    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if os.name != "nt" and hasattr(os, "wait4"):
        _pid, status, usage = os.wait4(process.pid, 0)
        process.returncode = os.waitstatus_to_exitcode(status)
        output, _unused = process.communicate()
        peak = int(usage.ru_maxrss)
        if sys.platform != "darwin":
            peak *= 1024
        return (
            time.perf_counter() - started,
            peak,
            output,
            int(process.returncode),
        )
    peak = 0
    while process.poll() is None:
        peak = max(peak, _process_rss_bytes(process.pid))
        time.sleep(0.05)
    output, _unused = process.communicate()
    peak = max(peak, _process_rss_bytes(process.pid))
    return time.perf_counter() - started, peak, output, int(process.returncode)


def _cumulative(stats: pstats.Stats, suffix: str, function: str) -> float:
    normalized_suffix = suffix.replace("\\", "/")
    return sum(
        float(values[3])
        for (filename, _line, name), values in stats.stats.items()
        if filename.replace("\\", "/").endswith(normalized_suffix)
        and name == function
    )


def _stage_times(profile_path: Path, wall_seconds: float) -> dict[str, float]:
    stats = pstats.Stats(str(profile_path))
    decode = _cumulative(stats, "x5crop/io/tiff.py", "read_tiff_profile") + _cumulative(
        stats, "x5crop/io/tiff.py", "read_tiff"
    )
    workspace = _cumulative(
        stats,
        "x5crop/detection/workspace.py",
        "prepare_detection_workspace",
    )
    coarse_support = _cumulative(
        stats,
        "x5crop/detection/photo_geometry/coarse_strip_support.py",
        "observe_coarse_strip_support",
    )
    measurement = _cumulative(
        stats,
        "x5crop/detection/photo_geometry/registered_measurement.py",
        "measure_registered_queries",
    )
    choose = _cumulative(
        stats, "x5crop/detection/pipeline.py", "choose_detection"
    )
    template_alignment = max(0.0, choose - measurement - coarse_support) + sum(
        (
            _cumulative(
                stats,
                "x5crop/detection/decision/decision_gate.py",
                "apply_decision_gate",
            ),
            _cumulative(
                stats,
                "x5crop/detection/final/finalize.py",
                "finalize_detection",
            ),
        )
    )
    sampling = _cumulative(stats, "x5crop/image/transforms.py", "sample_affine_roi")
    validated_write = _cumulative(
        stats, "x5crop/io/tiff.py", "write_validated_tiff"
    )
    readback = _cumulative(
        stats, "x5crop/io/tiff.py", "validate_written_tiff_header"
    )
    encode_write = max(0.0, validated_write - readback)
    publish = _cumulative(
        stats, "x5crop/output/publication.py", "publish"
    )
    attributed = (
        decode
        + workspace
        + coarse_support
        + measurement
        + template_alignment
        + sampling
        + encode_write
        + readback
        + publish
    )
    return {
        "startup_import_unattributed": max(0.0, wall_seconds - attributed),
        "decode": decode,
        "workspace_gray": workspace,
        "coarse_support": coarse_support,
        "registered_measurement": measurement,
        "template_alignment_decision": template_alignment,
        "sampling": sampling,
        "encode_write": encode_write,
        "readback": readback,
        "publish": publish,
    }


def _runtime_peak_temporary(report: dict[str, Any]) -> int:
    return max(
        (
            int(lane["peak_temporary_bytes"])
            for lane in report["photo_geometry"]["lanes"]
        ),
        default=0,
    )


def profile_source(source) -> ProfiledSource:
    with TemporaryDirectory(prefix="x5crop-performance-profile-") as temporary:
        root = Path(temporary)
        output = root / "x5_crop_output"
        profile_path = root / "production.prof"
        command = [
            sys.executable,
            "-m",
            "cProfile",
            "-o",
            str(profile_path),
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
                f"{source.sample_id} profiling pass failed:\n{process_output[-4000:]}"
            )
        rows = tuple(
            json.loads(line)
            for line in (output / "x5_crop_report.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        if len(rows) != 1:
            raise ValueError(f"{source.sample_id} profiling lacks one report")
        report = rows[0]
        validate_current_report_record(report)
        stages = _stage_times(profile_path, wall)
        io_total = sum(
            stages[name]
            for name in ("decode", "encode_write", "readback", "publish")
        )
        return ProfiledSource(
            sample_id=source.sample_id,
            wall_seconds=wall,
            stages=stages,
            io_total_seconds=io_total,
            process_peak_rss_bytes=peak_rss,
            runtime_peak_temporary_bytes=_runtime_peak_temporary(report),
        )
