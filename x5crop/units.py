from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


MILLIMETERS_PER_INCH = 25.4
MILLIMETERS_PER_CENTIMETER = 10.0


class ScanCalibrationSource(str, Enum):
    TIFF_RESOLUTION = "tiff_resolution"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ScanCalibration:
    x_px_per_mm: float | None
    y_px_per_mm: float | None
    source: ScanCalibrationSource
    trusted: bool
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, ScanCalibrationSource):
            raise ValueError("scan calibration requires a typed source")
        values = (self.x_px_per_mm, self.y_px_per_mm)
        if any(
            value is not None
            and (not math.isfinite(value) or value <= 0.0)
            for value in values
        ):
            raise ValueError("scan calibration scale must be finite and positive")
        if self.trusted and any(value is None for value in values):
            raise ValueError("trusted scan calibration requires both axis scales")
        if self.trusted and self.source == ScanCalibrationSource.UNAVAILABLE:
            raise ValueError("unavailable scan calibration cannot be trusted")

    def px_per_mm(self, axis: str) -> float | None:
        if axis not in {"x", "y"}:
            raise ValueError(f"unsupported calibration axis: {axis}")
        return self.y_px_per_mm if axis == "y" else self.x_px_per_mm


def _resolution_unit_name(value: int | str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"2", "inch", "inches"}:
        return "inch"
    if raw in {"3", "centimeter", "centimetre", "cm"}:
        return "centimeter"
    if raw in {"1", "none", "no_absolute_unit"}:
        return "none"
    return raw or "missing"


def _unavailable(*warnings: str) -> ScanCalibration:
    return ScanCalibration(
        x_px_per_mm=None,
        y_px_per_mm=None,
        source=ScanCalibrationSource.UNAVAILABLE,
        trusted=False,
        warnings=tuple(warnings),
    )


def scan_calibration_from_resolution(
    resolution: tuple[float, float] | None,
    resolution_unit: int | str | None,
) -> ScanCalibration:
    if not resolution:
        return _unavailable("missing_tiff_resolution")
    unit = _resolution_unit_name(resolution_unit)
    if unit == "inch":
        divisor = MILLIMETERS_PER_INCH
    elif unit == "centimeter":
        divisor = MILLIMETERS_PER_CENTIMETER
    elif unit == "none":
        return _unavailable("resolution_unit_has_no_absolute_length")
    else:
        return _unavailable(f"unsupported_resolution_unit:{unit}")

    x_res, y_res = resolution
    if x_res <= 0.0 or y_res <= 0.0:
        return _unavailable("invalid_tiff_resolution")
    x_px_per_mm = float(x_res) / divisor
    y_px_per_mm = float(y_res) / divisor
    if not math.isfinite(x_px_per_mm) or not math.isfinite(y_px_per_mm):
        return _unavailable("non_finite_tiff_resolution")
    return ScanCalibration(
        x_px_per_mm=x_px_per_mm,
        y_px_per_mm=y_px_per_mm,
        source=ScanCalibrationSource.TIFF_RESOLUTION,
        trusted=True,
        warnings=(),
    )


def scan_calibration_after_rotation(
    calibration: ScanCalibration,
    angle_degrees: float,
) -> ScanCalibration:
    if (
        not calibration.trusted
        or float(angle_degrees) == 0.0
        or calibration.x_px_per_mm == calibration.y_px_per_mm
    ):
        return calibration
    return _unavailable(
        *calibration.warnings,
        "anisotropic_resolution_invalid_after_rotation",
    )
