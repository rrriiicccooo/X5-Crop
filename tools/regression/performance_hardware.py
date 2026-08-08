"""Collect named-machine identity for development performance receipts."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Any

from x5crop.output.filesystem import identify_filesystem


def _command(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            args,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _cpu_model() -> str:
    system = platform.system()
    if system == "Darwin":
        value = _command("sysctl", "-n", "machdep.cpu.brand_string")
        if value:
            return value
        overview = _command("system_profiler", "SPHardwareDataType") or ""
        for line in overview.splitlines():
            if line.strip().startswith("Chip:"):
                return line.split(":", 1)[1].strip()
        return platform.processor()
    if system == "Windows":
        return os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor()
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.casefold().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _physical_cores() -> int | None:
    system = platform.system()
    if system == "Darwin":
        value = _command("sysctl", "-n", "hw.physicalcpu")
        if value is None:
            overview = _command("system_profiler", "SPHardwareDataType") or ""
            for line in overview.splitlines():
                if line.strip().startswith("Total Number of Cores:"):
                    value = line.split(":", 1)[1].strip().split(" ", 1)[0]
                    break
    elif system == "Windows":
        value = _command(
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum",
        )
    else:
        value = None
    try:
        return None if value is None else int(value)
    except ValueError:
        return None


def _total_memory_bytes() -> int:
    system = platform.system()
    if system == "Darwin":
        value = _command("sysctl", "-n", "hw.memsize")
        if value is not None:
            return int(value)
    if system == "Windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    page_size = int(os.sysconf("SC_PAGE_SIZE"))
    pages = int(os.sysconf("SC_PHYS_PAGES"))
    return page_size * pages


def _power_identity() -> dict[str, object]:
    system = platform.system()
    if system == "Darwin":
        battery = _command("pmset", "-g", "batt") or "unknown"
        custom = _command("pmset", "-g", "custom") or ""
        return {
            "source": battery.splitlines()[0] if battery else "unknown",
            "low_power_mode_declared": "lowpowermode" in custom,
            "raw_identity": battery,
        }
    if system == "Windows":
        scheme = _command("powercfg", "/getactivescheme") or "unknown"
        return {"active_scheme": scheme}
    return {"identity": "not_frozen_on_linux_ci"}


def _defender_identity() -> dict[str, object]:
    if platform.system() != "Windows":
        return {"applicable": False}
    value = _command(
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "(Get-MpPreference).DisableRealtimeMonitoring",
    )
    if value is None:
        return {"applicable": True, "status": "unavailable"}
    disabled = value.strip().casefold() == "true"
    return {
        "applicable": True,
        "status": "queried",
        "realtime_protection_enabled": not disabled,
        "default_setting_retained": not disabled,
    }


def _volume_identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    filesystem = identify_filesystem(resolved)
    space = shutil.disk_usage(resolved)
    return {
        "path": str(resolved),
        "device_id": int(resolved.stat().st_dev),
        "filesystem": filesystem.as_record(),
        "available_bytes": int(space.free),
        "total_bytes": int(space.total),
    }


def build_hardware_identity(input_root: Path) -> dict[str, Any]:
    logical = os.cpu_count()
    return {
        "machine_name": platform.node() or "unnamed-machine",
        "cpu_model": _cpu_model(),
        "physical_core_count": _physical_cores(),
        "logical_core_count": logical,
        "total_memory_bytes": _total_memory_bytes(),
        "input_volume": _volume_identity(input_root),
        "output_volume": _volume_identity(Path(tempfile.gettempdir())),
        "power": _power_identity(),
        "windows_defender": _defender_identity(),
    }
