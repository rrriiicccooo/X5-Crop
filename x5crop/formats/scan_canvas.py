from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive


@dataclass(frozen=True, order=True)
class ScanCanvasFormatFit:
    format_id: str
    maximum_frame_count: int

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("scan-canvas format identity must not be empty")
        require_positive(
            "scan-canvas maximum frame count",
            self.maximum_frame_count,
        )


@dataclass(frozen=True)
class ScanCanvasPhysicalSpec:
    profile_id: str
    short_axis_mm: float
    long_axis_mm: float
    format_fits: tuple[ScanCanvasFormatFit, ...]

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("scan-canvas profile identity must not be empty")
        require_positive("scan-canvas short axis", self.short_axis_mm)
        require_positive("scan-canvas long axis", self.long_axis_mm)
        if self.long_axis_mm <= self.short_axis_mm:
            raise ValueError("scan-canvas long axis must exceed its short axis")
        format_ids = tuple(item.format_id for item in self.format_fits)
        if not format_ids or len(set(format_ids)) != len(format_ids):
            raise ValueError(
                "scan-canvas format fits must be non-empty and unique"
            )

    @property
    def aspect(self) -> float:
        return float(self.long_axis_mm) / float(self.short_axis_mm)

    def supports(
        self,
        format_id: str,
        frame_count: int | None,
    ) -> bool:
        return any(
            item.format_id == format_id
            and (
                frame_count is None
                or frame_count <= item.maximum_frame_count
            )
            for item in self.format_fits
        )


SCAN_CANVAS_PHYSICAL_SPECS = (
    ScanCanvasPhysicalSpec(
        "135_standard",
        short_axis_mm=32.22,
        long_axis_mm=232.0,
        format_fits=(
            ScanCanvasFormatFit("135", 6),
            ScanCanvasFormatFit("half", 12),
            ScanCanvasFormatFit("xpan", 3),
        ),
    ),
    ScanCanvasPhysicalSpec(
        "135_narrow",
        short_axis_mm=25.4,
        long_axis_mm=232.0,
        format_fits=(
            ScanCanvasFormatFit("135", 6),
            ScanCanvasFormatFit("half", 12),
            ScanCanvasFormatFit("xpan", 3),
        ),
    ),
    ScanCanvasPhysicalSpec(
        "135_dual",
        short_axis_mm=63.44,
        long_axis_mm=232.0,
        format_fits=(ScanCanvasFormatFit("135-dual", 12),),
    ),
    ScanCanvasPhysicalSpec(
        "120_standard",
        short_axis_mm=60.0,
        long_axis_mm=226.0,
        format_fits=(
            ScanCanvasFormatFit("120-645", 4),
            ScanCanvasFormatFit("120-66", 3),
            ScanCanvasFormatFit("120-67", 3),
        ),
    ),
    ScanCanvasPhysicalSpec(
        "120_wide_224_5",
        short_axis_mm=63.44,
        long_axis_mm=224.5,
        format_fits=(
            ScanCanvasFormatFit("120-645", 4),
            ScanCanvasFormatFit("120-66", 3),
            ScanCanvasFormatFit("120-67", 3),
        ),
    ),
    ScanCanvasPhysicalSpec(
        "120_wide_223",
        short_axis_mm=63.44,
        long_axis_mm=223.0,
        format_fits=(
            ScanCanvasFormatFit("120-645", 4),
            ScanCanvasFormatFit("120-66", 3),
            ScanCanvasFormatFit("120-67", 3),
        ),
    ),
    ScanCanvasPhysicalSpec(
        "120_wide_188_5",
        short_axis_mm=63.44,
        long_axis_mm=188.5,
        format_fits=(
            ScanCanvasFormatFit("120-645", 4),
            ScanCanvasFormatFit("120-66", 3),
            ScanCanvasFormatFit("120-67", 2),
        ),
    ),
)


def scan_canvas_specs_for_format(
    format_id: str,
    frame_count: int | None = None,
) -> tuple[ScanCanvasPhysicalSpec, ...]:
    if frame_count is not None:
        require_positive("scan-canvas requested frame count", frame_count)
    return tuple(
        spec
        for spec in SCAN_CANVAS_PHYSICAL_SPECS
        if spec.supports(format_id, frame_count)
    )


def _validate_scan_canvas_catalog() -> None:
    profile_ids = tuple(
        spec.profile_id for spec in SCAN_CANVAS_PHYSICAL_SPECS
    )
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("scan-canvas profile identities must be unique")


_validate_scan_canvas_catalog()
