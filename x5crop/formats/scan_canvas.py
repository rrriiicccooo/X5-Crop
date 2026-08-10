from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive


@dataclass(frozen=True)
class ScanCanvasPhysicalSpec:
    profile_id: str
    short_axis_mm: float
    long_axis_mm: float

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("scan-canvas profile identity must not be empty")
        require_positive("scan-canvas short axis", self.short_axis_mm)
        require_positive("scan-canvas long axis", self.long_axis_mm)
        if self.long_axis_mm <= self.short_axis_mm:
            raise ValueError("scan-canvas long axis must exceed its short axis")

    @property
    def aspect(self) -> float:
        return float(self.long_axis_mm) / float(self.short_axis_mm)

SCAN_CANVAS_PHYSICAL_SPECS = (
    ScanCanvasPhysicalSpec(
        "135_standard",
        short_axis_mm=32.22,
        long_axis_mm=232.0,
    ),
    ScanCanvasPhysicalSpec(
        "135_narrow",
        short_axis_mm=25.4,
        long_axis_mm=232.0,
    ),
    ScanCanvasPhysicalSpec(
        "135_dual",
        short_axis_mm=63.44,
        long_axis_mm=232.0,
    ),
    ScanCanvasPhysicalSpec(
        "120_standard",
        short_axis_mm=60.0,
        long_axis_mm=226.0,
    ),
    ScanCanvasPhysicalSpec(
        "120_wide_224_5",
        short_axis_mm=63.44,
        long_axis_mm=224.5,
    ),
    ScanCanvasPhysicalSpec(
        "120_wide_223",
        short_axis_mm=63.44,
        long_axis_mm=223.0,
    ),
    ScanCanvasPhysicalSpec(
        "120_wide_188_5",
        short_axis_mm=63.44,
        long_axis_mm=188.5,
    ),
)


def scan_canvas_specs_for_format(
    format_id: str,
) -> tuple[ScanCanvasPhysicalSpec, ...]:
    from . import format_spec

    physical = format_spec(format_id)
    profile_by_id = {
        spec.profile_id: spec for spec in SCAN_CANVAS_PHYSICAL_SPECS
    }
    return tuple(
        profile_by_id[fit.profile_id]
        for fit in physical.scan_canvas_fits
    )


def _validate_scan_canvas_catalog() -> None:
    profile_ids = tuple(
        spec.profile_id for spec in SCAN_CANVAS_PHYSICAL_SPECS
    )
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("scan-canvas profile identities must be unique")


_validate_scan_canvas_catalog()
