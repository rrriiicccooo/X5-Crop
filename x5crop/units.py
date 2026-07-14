from __future__ import annotations

import math
from dataclasses import dataclass


MILLIMETERS_PER_INCH = 25.4
MILLIMETERS_PER_CENTIMETER = 10.0


@dataclass(frozen=True)
class ResolutionMetadataObservation:
    x_px_per_mm: float | None
    y_px_per_mm: float | None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (self.x_px_per_mm, self.y_px_per_mm)
        if any(
            value is not None
            and (not math.isfinite(value) or value <= 0.0)
            for value in values
        ):
            raise ValueError("resolution metadata scale must be finite and positive")
        if len(set(self.diagnostics)) != len(self.diagnostics):
            raise ValueError("resolution metadata diagnostics must be unique")


def _resolution_unit_name(value: int | str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"2", "inch", "inches"}:
        return "inch"
    if raw in {"3", "centimeter", "centimetre", "cm"}:
        return "centimeter"
    if raw in {"1", "none", "no_absolute_unit"}:
        return "none"
    return raw or "missing"


def resolution_metadata_observation(
    resolution: tuple[float, float] | None,
    resolution_unit: int | str | None,
) -> ResolutionMetadataObservation:
    if not resolution:
        return ResolutionMetadataObservation(None, None, ("missing_tiff_resolution",))
    unit = _resolution_unit_name(resolution_unit)
    if unit == "inch":
        divisor = MILLIMETERS_PER_INCH
    elif unit == "centimeter":
        divisor = MILLIMETERS_PER_CENTIMETER
    elif unit == "none":
        return ResolutionMetadataObservation(
            None,
            None,
            ("resolution_unit_has_no_absolute_length",),
        )
    else:
        return ResolutionMetadataObservation(
            None,
            None,
            (f"unsupported_resolution_unit:{unit}",),
        )
    x_res, y_res = resolution
    if x_res <= 0.0 or y_res <= 0.0:
        return ResolutionMetadataObservation(None, None, ("invalid_tiff_resolution",))
    x_px_per_mm = float(x_res) / divisor
    y_px_per_mm = float(y_res) / divisor
    if not math.isfinite(x_px_per_mm) or not math.isfinite(y_px_per_mm):
        return ResolutionMetadataObservation(None, None, ("non_finite_tiff_resolution",))
    return ResolutionMetadataObservation(x_px_per_mm, y_px_per_mm)
