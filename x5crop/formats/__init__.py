from __future__ import annotations

from dataclasses import dataclass

from ..domain import FiniteInterval
from ..utils import require_positive


@dataclass(frozen=True, order=True)
class FramePhysicalSpec:
    """One format-owned frame template and local advance authority."""

    component_id: str
    frame_width_mm: float
    frame_height_mm: float
    nominal_gap_mm: float
    local_advance_gap_mm: FiniteInterval

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("frame physical component requires an identity")
        require_positive("frame design width", self.frame_width_mm)
        require_positive("frame design height", self.frame_height_mm)
        if (
            not 0.0 <= self.nominal_gap_mm
            or not self.local_advance_gap_mm.contains(self.nominal_gap_mm)
        ):
            raise ValueError(
                "nominal gap must be finite, non-negative, and locally allowed"
            )


@dataclass(frozen=True, order=True)
class FrameDimensionToleranceSpec:
    """Global design-template separation tolerance.

    The ratios decide whether measured opposite edges can belong to the same
    design template.  They are neither search allowance nor output padding.
    """

    frame_width_tolerance_ratio: float = 0.0125
    frame_height_tolerance_ratio: float = 0.0040

    def __post_init__(self) -> None:
        for name, value in (
            ("frame width tolerance ratio", self.frame_width_tolerance_ratio),
            ("frame height tolerance ratio", self.frame_height_tolerance_ratio),
        ):
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be between zero and one")


FRAME_DIMENSION_TOLERANCE_SPEC = FrameDimensionToleranceSpec()


@dataclass(frozen=True)
class StripHandlingSpec:
    default_count: int
    partial_mode_supported: bool

    def __post_init__(self) -> None:
        require_positive("default frame count", self.default_count)

    @property
    def partial_count_range(self) -> tuple[int, ...]:
        if not self.partial_mode_supported:
            return ()
        return tuple(range(1, self.default_count + 1))


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
    """Format-owned applicability and capacity for one physical canvas."""

    profile_id: str
    maximum_frame_count: int

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("scan-canvas fit requires a profile identity")
        require_positive("scan-canvas maximum frame count", self.maximum_frame_count)


@dataclass(frozen=True)
class FormatSpec:
    format_id: str
    frame_components: tuple[FramePhysicalSpec, ...]
    strip: StripHandlingSpec
    layout: ScanLayoutSpec
    scan_canvas_fits: tuple[ScanCanvasFit, ...]

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("format identity must not be empty")
        if not self.frame_components:
            raise ValueError("format requires physical frame components")
        component_ids = tuple(item.component_id for item in self.frame_components)
        if len(set(component_ids)) != len(component_ids):
            raise ValueError("format physical components must be unique")
        if (
            self.layout.kind == "dual_lane"
            and self.strip.default_count % self.layout.lane_count
        ):
            raise ValueError("dual-lane frame count must divide evenly across lanes")
        profile_ids = tuple(item.profile_id for item in self.scan_canvas_fits)
        if not profile_ids or len(set(profile_ids)) != len(profile_ids):
            raise ValueError("format scan-canvas fits must be non-empty and unique")

    def maximum_frame_count(self, profile_id: str) -> int | None:
        return next(
            (
                item.maximum_frame_count
                for item in self.scan_canvas_fits
                if item.profile_id == profile_id
            ),
            None,
        )


FORMATS: dict[str, FormatSpec] = {
    "135": FormatSpec(
        "135",
        (
            FramePhysicalSpec(
                "36x24mm",
                36.0,
                24.0,
                1.625,
                FiniteInterval(1.0, 2.25),
            ),
        ),
        StripHandlingSpec(6, True),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 6),
            ScanCanvasFit("135_narrow", 6),
        ),
    ),
    "135-dual": FormatSpec(
        "135-dual",
        (
            FramePhysicalSpec(
                "36x24mm",
                36.0,
                24.0,
                1.625,
                FiniteInterval(1.0, 2.25),
            ),
        ),
        StripHandlingSpec(12, False),
        ScanLayoutSpec("dual_lane", 2, "135"),
        (ScanCanvasFit("135_dual", 12),),
    ),
    "half": FormatSpec(
        "half",
        (
            FramePhysicalSpec(
                "18x24mm",
                18.0,
                24.0,
                1.0,
                FiniteInterval(-0.5, 2.5),
            ),
        ),
        StripHandlingSpec(12, True),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 12),
            ScanCanvasFit("135_narrow", 12),
        ),
    ),
    "xpan": FormatSpec(
        "xpan",
        (
            FramePhysicalSpec(
                "65x24mm",
                65.0,
                24.0,
                2.5,
                FiniteInterval(1.0, 4.0),
            ),
        ),
        StripHandlingSpec(3, True),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 3),
            ScanCanvasFit("135_narrow", 3),
        ),
    ),
    "120-645": FormatSpec(
        "120-645",
        (
            FramePhysicalSpec(
                "42x54mm", 42.0, 54.0, 6.5, FiniteInterval(4.0, 9.0)
            ),
            FramePhysicalSpec(
                "42x56mm", 42.0, 56.0, 6.5, FiniteInterval(4.0, 9.0)
            ),
        ),
        StripHandlingSpec(4, True),
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
        (
            FramePhysicalSpec(
                "54x54mm", 54.0, 54.0, 7.5, FiniteInterval(4.0, 11.0)
            ),
            FramePhysicalSpec(
                "56x56mm", 56.0, 56.0, 5.5, FiniteInterval(2.0, 9.0)
            ),
        ),
        StripHandlingSpec(3, True),
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
        (
            FramePhysicalSpec(
                "70x54mm", 70.0, 54.0, 5.0, FiniteInterval(2.0, 8.0)
            ),
            FramePhysicalSpec(
                "70x56mm", 70.0, 56.0, 5.0, FiniteInterval(2.0, 8.0)
            ),
        ),
        StripHandlingSpec(3, True),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("120_standard", 3),
            ScanCanvasFit("120_wide_224_5", 3),
            ScanCanvasFit("120_wide_223", 3),
            ScanCanvasFit("120_wide_188_5", 2),
        ),
    ),
}

FORMAT_CHOICES = tuple(FORMATS)


def format_spec(format_id: str) -> FormatSpec:
    return FORMATS[format_id]
