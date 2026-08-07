from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import threading

from ..io.tiff import read_tiff_profile


DISK_GUARD_BYTES = 32 * 1024 * 1024
REPORT_ALLOWANCE_PER_SOURCE_BYTES = 512 * 1024
TRANSACTION_ALLOWANCE_BYTES = 1024 * 1024


class DiskSpaceBudgetError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiskReservationEstimate:
    output_bytes: int
    report_bytes: int
    debug_bytes: int
    transaction_bytes: int
    guard_bytes: int

    @property
    def total_bytes(self) -> int:
        return (
            self.output_bytes
            + self.report_bytes
            + self.debug_bytes
            + self.transaction_bytes
            + self.guard_bytes
        )


class RunWideDiskBudget:
    """One scheduler-owned reservation; workers never query free space."""

    def __init__(self, available_bytes: int, required_bytes: int) -> None:
        if available_bytes < 0 or required_bytes <= 0:
            raise ValueError("disk budget values must be positive")
        if available_bytes < required_bytes:
            raise DiskSpaceBudgetError(
                "Insufficient space for the complete staged output while the prior "
                f"output remains available: need {required_bytes} bytes, "
                f"have {available_bytes} bytes"
            )
        self.available_bytes = available_bytes
        self.required_bytes = required_bytes
        self._remaining = required_bytes
        self._lock = threading.Lock()

    @classmethod
    def reserve(cls, parent: Path, required_bytes: int) -> "RunWideDiskBudget":
        free = int(shutil.disk_usage(parent).free)
        return cls(free, required_bytes)

    @property
    def remaining_bytes(self) -> int:
        with self._lock:
            return self._remaining

    def claim(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("disk claim cannot be negative")
        with self._lock:
            if amount > self._remaining:
                raise DiskSpaceBudgetError(
                    "Worker output exceeded the invocation-wide disk reservation"
                )
            self._remaining -= amount

    def release(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("disk release cannot be negative")
        with self._lock:
            self._remaining = min(
                self.required_bytes,
                self._remaining + amount,
            )

    def as_record(self) -> dict[str, int]:
        return {
            "available_at_preflight_bytes": self.available_bytes,
            "reserved_bytes": self.required_bytes,
        }


def estimate_run_reservation(
    sources: tuple[Path, ...],
    *,
    debug_analysis: bool,
) -> DiskReservationEstimate:
    """Conservative header-only estimate made before any production sampling."""

    raster_bytes = 0
    source_bytes = 0
    for source in sources:
        try:
            source_bytes += max(0, int(source.stat().st_size))
        except OSError:
            pass
        try:
            profile, _warnings = read_tiff_profile(source)
            samples = 1
            for extent in profile.shape:
                samples *= int(extent)
            raster_bytes += samples * 2
        except Exception:
            # The source will become runtime_error. Its stat size still reserves
            # enough space for the lightweight terminal record.
            continue
    # Lossless encoded crops can be larger than their source file. Two raster
    # copies cover full/capacity slots plus bounded contact overlap without
    # relying on the source's compression ratio.
    output_bytes = max(source_bytes, raster_bytes * 2)
    debug_bytes = raster_bytes if debug_analysis else 0
    return DiskReservationEstimate(
        output_bytes=output_bytes,
        report_bytes=len(sources) * REPORT_ALLOWANCE_PER_SOURCE_BYTES,
        debug_bytes=debug_bytes,
        transaction_bytes=TRANSACTION_ALLOWANCE_BYTES,
        guard_bytes=DISK_GUARD_BYTES,
    )
