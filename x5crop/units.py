from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .domain import ImageProfile


@dataclass(frozen=True)
class ScanCalibration:
    x_px_per_mm: float | None
    y_px_per_mm: float | None
    source: str
    trusted: bool
    warnings: tuple[str, ...] = ()

    def px_per_mm(self, axis: str) -> float | None:
        return self.y_px_per_mm if axis == "y" else self.x_px_per_mm


@dataclass(frozen=True)
class PhysicalLength:
    mm: float | None
    fallback_ratio: float
    min_px: int
    max_px: int

    def fallback_px(self, reference_px: float) -> int:
        value = float(reference_px) * float(self.fallback_ratio)
        return max(int(self.min_px), min(int(self.max_px), int(round(value))))

    def resolve_px(
        self,
        calibration: ScanCalibration,
        *,
        axis: str,
        reference_px: float,
    ) -> int:
        px_per_mm = calibration.px_per_mm(axis)
        if (
            calibration.trusted
            and self.mm is not None
            and px_per_mm is not None
            and px_per_mm > 0.0
        ):
            value = float(self.mm) * float(px_per_mm)
        else:
            return self.fallback_px(reference_px)
        return max(int(self.min_px), min(int(self.max_px), int(round(value))))

@dataclass(frozen=True)
class ScanCalibrationTrustParameters:
    min_axis_resolution_ratio: float = 0.5
    max_axis_resolution_ratio: float = 2.0


def _numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2:
        denominator = float(value[1])
        if denominator == 0.0:
            return None
        return float(value[0]) / denominator
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolution_unit_name(value: Any) -> str:
    raw = str(getattr(value, "name", value) or "").strip().lower()
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
        source="unavailable",
        trusted=False,
        warnings=tuple(warnings),
    )


def scan_calibration_from_profile(
    profile: ImageProfile,
    parameters: ScanCalibrationTrustParameters,
) -> ScanCalibration:
    if not profile.resolution:
        return _unavailable("missing_tiff_resolution")
    unit = _resolution_unit_name(profile.resolution_unit)
    if unit == "inch":
        divisor = 25.4
    elif unit == "centimeter":
        divisor = 10.0
    elif unit == "none":
        return _unavailable("resolution_unit_has_no_absolute_length")
    else:
        return _unavailable(f"unsupported_resolution_unit:{unit}")

    x_res = _numeric_value(profile.resolution[0])
    y_res = _numeric_value(profile.resolution[1])
    if x_res is None or y_res is None or x_res <= 0.0 or y_res <= 0.0:
        return _unavailable("invalid_tiff_resolution")
    x_px_per_mm = float(x_res) / divisor
    y_px_per_mm = float(y_res) / divisor
    if not math.isfinite(x_px_per_mm) or not math.isfinite(y_px_per_mm):
        return _unavailable("non_finite_tiff_resolution")
    ratio = x_px_per_mm / y_px_per_mm if y_px_per_mm else 0.0
    if (
        ratio < float(parameters.min_axis_resolution_ratio)
        or ratio > float(parameters.max_axis_resolution_ratio)
    ):
        return ScanCalibration(
            x_px_per_mm=x_px_per_mm,
            y_px_per_mm=y_px_per_mm,
            source="tiff_resolution",
            trusted=False,
            warnings=("non_square_resolution_ratio",),
        )
    return ScanCalibration(
        x_px_per_mm=x_px_per_mm,
        y_px_per_mm=y_px_per_mm,
        source="tiff_resolution",
        trusted=True,
        warnings=(),
    )
