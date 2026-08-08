"""Profile production CLI stage boundaries without production instrumentation."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
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
    "detection_decision",
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


def _run_profiled(command: list[str]) -> tuple[float, int, str, int]:
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
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
    detection = sum(
        (
            _cumulative(stats, "x5crop/detection/pipeline.py", "choose_detection"),
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
    readback = _cumulative(stats, "x5crop/io/tiff.py", "validate_written_tiff")
    encode_write = max(0.0, validated_write - readback)
    publish = _cumulative(
        stats, "x5crop/output/transaction.py", "publish"
    )
    attributed = decode + detection + sampling + encode_write + readback + publish
    return {
        "startup_import_unattributed": max(0.0, wall_seconds - attributed),
        "decode": decode,
        "detection_decision": detection,
        "sampling": sampling,
        "encode_write": encode_write,
        "readback": readback,
        "publish": publish,
    }


def _runtime_peak_temporary(report: dict[str, Any]) -> int:
    return max(
        (
            int(lane["work"]["peak_temporary_bytes"])
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
            "--strip",
            source.strip_mode,
            "--jobs",
            "1",
        ]
        if source.strip_mode == "partial":
            command.extend(("--count", "auto"))
        wall, peak_rss, process_output, returncode = _run_profiled(command)
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
