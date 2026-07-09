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
    inferred_from_frame_short_axis: dict[str, Any] | None = None

    def px_per_mm(self, axis: str) -> float | None:
        return self.y_px_per_mm if axis == "y" else self.x_px_per_mm

    def detail(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "trusted": bool(self.trusted),
            "x_px_per_mm": self.x_px_per_mm,
            "y_px_per_mm": self.y_px_per_mm,
            "warnings": list(self.warnings),
            "inferred_from_frame_short_axis": self.inferred_from_frame_short_axis
            or {"used": False, "reason": "not_used_to_avoid_candidate_calibration_cycle"},
        }


@dataclass(frozen=True)
class PhysicalLength:
    mm: float | None = None
    fallback_ratio: float | None = None
    min_px: float | None = None
    max_px: float | None = None

    def resolve_px(
        self,
        calibration: ScanCalibration,
        *,
        axis: str = "x",
        reference_px: float | None = None,
    ) -> float | None:
        value: float | None = None
        px_per_mm = calibration.px_per_mm(axis)
        if self.mm is not None and calibration.trusted and px_per_mm is not None:
            value = float(self.mm) * float(px_per_mm)
        elif self.fallback_ratio is not None and reference_px is not None:
            value = float(self.fallback_ratio) * float(reference_px)
        elif self.min_px is not None:
            value = float(self.min_px)
        elif self.max_px is not None:
            value = float(self.max_px)

        if value is None:
            return None
        if self.min_px is not None:
            value = max(float(self.min_px), value)
        if self.max_px is not None:
            value = min(float(self.max_px), value)
        return float(value)

    def detail(
        self,
        calibration: ScanCalibration,
        *,
        axis: str = "x",
        reference_px: float | None = None,
    ) -> dict[str, Any]:
        resolved_px = self.resolve_px(calibration, axis=axis, reference_px=reference_px)
        if self.mm is not None and calibration.trusted and calibration.px_per_mm(axis) is not None:
            source = "scan_calibration_mm"
        elif self.fallback_ratio is not None and reference_px is not None:
            source = "fallback_ratio"
        elif resolved_px is not None:
            source = "pixel_clamp"
        else:
            source = "unavailable"
        return {
            "mm": self.mm,
            "fallback_ratio": self.fallback_ratio,
            "min_px": self.min_px,
            "max_px": self.max_px,
            "axis": axis,
            "reference_px": reference_px,
            "resolved_px": resolved_px,
            "source": source,
        }


@dataclass(frozen=True)
class PixelKernel:
    px: int

    def __post_init__(self) -> None:
        if int(self.px) <= 0:
            raise ValueError("PixelKernel.px must be positive")


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


def scan_calibration_from_profile(profile: ImageProfile) -> ScanCalibration:
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
    if ratio < 0.5 or ratio > 2.0:
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


__all__ = [
    "PhysicalLength",
    "PixelKernel",
    "ScanCalibration",
    "scan_calibration_from_profile",
]
