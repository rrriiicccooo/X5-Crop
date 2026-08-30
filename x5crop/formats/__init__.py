from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from ..utils import require_positive


@dataclass(frozen=True, order=True)
class FramePhysicalSpec:
    """One format's design aperture and bounded cross-camera prior."""

    frame_width_mm: float
    frame_height_mm: float
    format_gap_prior_mm: float | None
    frame_width_factor_minimum: float = 0.9875
    frame_width_factor_maximum: float = 1.0125
    frame_height_factor_minimum: float = 0.9960
    frame_height_factor_maximum: float = 1.0040

    def __post_init__(self) -> None:
        require_positive("frame design width", self.frame_width_mm)
        require_positive("frame design height", self.frame_height_mm)
        if self.format_gap_prior_mm is not None:
            require_positive("format gap search prior", self.format_gap_prior_mm)
        for name, minimum, maximum in (
            (
                "frame width factor",
                self.frame_width_factor_minimum,
                self.frame_width_factor_maximum,
            ),
            (
                "frame height factor",
                self.frame_height_factor_minimum,
                self.frame_height_factor_maximum,
            ),
        ):
            if not 0.0 < minimum <= 1.0 <= maximum:
                raise ValueError(f"{name} prior must contain design unity")

    @property
    def identity_fields(self) -> tuple[str, ...]:
        return (
            self.frame_width_mm.hex(),
            self.frame_height_mm.hex(),
            "none"
            if self.format_gap_prior_mm is None
            else self.format_gap_prior_mm.hex(),
            self.frame_width_factor_minimum.hex(),
            self.frame_width_factor_maximum.hex(),
            self.frame_height_factor_minimum.hex(),
            self.frame_height_factor_maximum.hex(),
        )

    @property
    def frame_spec_id(self) -> str:
        return "frame-spec:" + ":".join(self.identity_fields)

@dataclass(frozen=True, order=True)
class OutputProtectionSpec:
    """One product policy for bleed and automatic-output limits.

    Bleed is deterministic output geometry.  It is not measurement evidence
    and never helps select a placement.  The five-percent limit is applied to
    the complete selected-output requirement on each aperture side.  A
    directly observed enclosing support pair has its own total-height limit
    and receives no additional cross-axis bleed.
    """

    sequence_bleed_minimum_mm: float = 0.15
    sequence_bleed_frame_ratio: float = 0.007
    cross_bleed_mm: float = 0.25
    maximum_expansion_ratio_per_side: float = 0.05
    maximum_enclosing_support_height_ratio: float = 1.10

    def __post_init__(self) -> None:
        for name, value in (
            ("sequence minimum bleed", self.sequence_bleed_minimum_mm),
            ("cross bleed", self.cross_bleed_mm),
        ):
            require_positive(name, value)
        for name, value in (
            ("sequence bleed ratio", self.sequence_bleed_frame_ratio),
            ("maximum per-side expansion", self.maximum_expansion_ratio_per_side),
        ):
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if not 1.0 < self.maximum_enclosing_support_height_ratio < 2.0:
            raise ValueError("enclosing-support height ratio must be between one and two")

    def sequence_bleed_mm(self, frame_width_mm: float) -> float:
        require_positive("frame width", frame_width_mm)
        return max(
            self.sequence_bleed_minimum_mm,
            self.sequence_bleed_frame_ratio * frame_width_mm,
        )


OUTPUT_PROTECTION_SPEC = OutputProtectionSpec()


@dataclass(frozen=True)
class ScanLayoutSpec:
    kind: str = "single_strip"
    lane_count: int = 1
    lane_format_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"single_strip", "dual_lane"}:
            raise ValueError(f"unsupported scan layout: {self.kind}")
        if self.kind == "dual_lane":
            if self.lane_count != 2 or not self.lane_format_id:
                raise ValueError(
                    "dual-lane authority requires exactly two identified lanes"
                )
        elif self.lane_count != 1 or self.lane_format_id is not None:
            raise ValueError("single-strip layout cannot declare lane geometry")


@dataclass(frozen=True, order=True)
class ScanCanvasFit:
    """Format-owned applicability and full count for one physical holder."""

    profile_id: str
    full_count: int

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("scan-canvas fit requires a profile identity")
        require_positive("scan-canvas full count", self.full_count)


@dataclass(frozen=True)
class FormatSpec:
    format_id: str
    frame: FramePhysicalSpec
    layout: ScanLayoutSpec
    scan_canvas_fits: tuple[ScanCanvasFit, ...]

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("format identity must not be empty")
        profile_ids = tuple(item.profile_id for item in self.scan_canvas_fits)
        if not profile_ids or len(set(profile_ids)) != len(profile_ids):
            raise ValueError("format scan-canvas fits must be non-empty and unique")

    def holder_full_count(self, profile_id: str) -> int | None:
        return next(
            (
                item.full_count
                for item in self.scan_canvas_fits
                if item.profile_id == profile_id
            ),
            None,
        )

    @property
    def maximum_full_count(self) -> int:
        return max(item.full_count for item in self.scan_canvas_fits)

FRAME_135 = FramePhysicalSpec(36.0, 24.0, 2.0)


FORMAT_CATALOG_REVISION = "x5crop_format_catalog_v3"


_FORMAT_SPECS: dict[str, FormatSpec] = {
    "135": FormatSpec(
        "135",
        FRAME_135,
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 6),
            ScanCanvasFit("135_narrow", 6),
        ),
    ),
    "135-dual": FormatSpec(
        "135-dual",
        FRAME_135,
        ScanLayoutSpec("dual_lane", 2, "135"),
        (ScanCanvasFit("135_dual", 12),),
    ),
    "half": FormatSpec(
        "half",
        FramePhysicalSpec(
            18.0,
            24.0,
            1.0,
            frame_width_factor_minimum=0.965,
        ),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 12),
            ScanCanvasFit("135_narrow", 12),
        ),
    ),
    "xpan": FormatSpec(
        "xpan",
        FramePhysicalSpec(65.0, 24.0, 2.0),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 3),
            ScanCanvasFit("135_narrow", 3),
        ),
    ),
    "120-645": FormatSpec(
        "120-645",
        FramePhysicalSpec(42.0, 56.0, None),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("120_standard", 4),
            ScanCanvasFit("120_wide_224_5", 4),
            ScanCanvasFit("120_wide_223", 4),
            ScanCanvasFit("120_wide_188_5", 4),
        ),
    ),
    "120-66": FormatSpec(
        "120-66",
        FramePhysicalSpec(56.0, 56.0, None),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("120_standard", 3),
            ScanCanvasFit("120_wide_224_5", 3),
            ScanCanvasFit("120_wide_223", 3),
            ScanCanvasFit("120_wide_188_5", 3),
        ),
    ),
    "120-67": FormatSpec(
        "120-67",
        FramePhysicalSpec(70.0, 56.0, None),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("120_standard", 3),
            ScanCanvasFit("120_wide_224_5", 3),
            ScanCanvasFit("120_wide_223", 3),
            ScanCanvasFit("120_wide_188_5", 2),
        ),
    ),
}

FORMATS = MappingProxyType(_FORMAT_SPECS)
FORMAT_CHOICES = tuple(FORMATS)


def format_spec(format_id: str) -> FormatSpec:
    return FORMATS[format_id]
