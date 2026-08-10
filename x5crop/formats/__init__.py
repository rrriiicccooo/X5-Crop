from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive


@dataclass(frozen=True, order=True)
class FramePhysicalSpec:
    """The single fixed frame rectangle owned by one format."""

    frame_width_mm: float
    frame_height_mm: float
    format_gap_prior_mm: float | None

    def __post_init__(self) -> None:
        require_positive("frame design width", self.frame_width_mm)
        require_positive("frame design height", self.frame_height_mm)
        if self.format_gap_prior_mm is not None:
            require_positive("format gap search prior", self.format_gap_prior_mm)

    @property
    def identity_fields(self) -> tuple[str, str, str]:
        return (
            self.frame_width_mm.hex(),
            self.frame_height_mm.hex(),
            "none"
            if self.format_gap_prior_mm is None
            else self.format_gap_prior_mm.hex(),
        )

    @property
    def frame_spec_id(self) -> str:
        return "frame-spec:" + ":".join(self.identity_fields)


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
    partial_mode_supported: bool
    layout: ScanLayoutSpec
    scan_canvas_fits: tuple[ScanCanvasFit, ...]

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("format identity must not be empty")
        if (
            self.layout.kind == "dual_lane"
            and self.partial_mode_supported
        ):
            raise ValueError("dual-lane format is full-only")
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

    @property
    def interactive_partial_counts(self) -> tuple[int, ...]:
        if not self.partial_mode_supported:
            return ()
        return tuple(range(1, self.maximum_full_count))


FRAME_135 = FramePhysicalSpec(36.0, 24.0, 2.0)


FORMATS: dict[str, FormatSpec] = {
    "135": FormatSpec(
        "135",
        FRAME_135,
        True,
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 6),
            ScanCanvasFit("135_narrow", 6),
        ),
    ),
    "135-dual": FormatSpec(
        "135-dual",
        FRAME_135,
        False,
        ScanLayoutSpec("dual_lane", 2, "135"),
        (ScanCanvasFit("135_dual", 12),),
    ),
    "half": FormatSpec(
        "half",
        FramePhysicalSpec(18.0, 24.0, 1.0),
        True,
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 12),
            ScanCanvasFit("135_narrow", 12),
        ),
    ),
    "xpan": FormatSpec(
        "xpan",
        FramePhysicalSpec(65.0, 24.0, 2.0),
        True,
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 3),
            ScanCanvasFit("135_narrow", 3),
        ),
    ),
    "120-645": FormatSpec(
        "120-645",
        FramePhysicalSpec(42.0, 56.0, None),
        True,
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
        True,
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
        True,
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
