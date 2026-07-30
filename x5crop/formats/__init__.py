from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive


@dataclass(frozen=True, order=True)
class FrameDesignApertureMm:
    """User-approved design-standard image aperture."""

    long_axis_mm: float
    short_axis_mm: float

    def __post_init__(self) -> None:
        require_positive("frame design long axis", self.long_axis_mm)
        require_positive("frame design short axis", self.short_axis_mm)


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


@dataclass(frozen=True)
class FormatSpec:
    format_id: str
    aperture_components: tuple[FrameDesignApertureMm, ...]
    strip: StripHandlingSpec
    layout: ScanLayoutSpec

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("format identity must not be empty")
        if not self.aperture_components:
            raise ValueError("format requires design aperture components")
        if len(set(self.aperture_components)) != len(self.aperture_components):
            raise ValueError("format design aperture components must be unique")
        if (
            self.layout.kind == "dual_lane"
            and self.strip.default_count % self.layout.lane_count
        ):
            raise ValueError("dual-lane frame count must divide evenly across lanes")


FORMATS: dict[str, FormatSpec] = {
    "135": FormatSpec(
        "135",
        (FrameDesignApertureMm(36.0, 24.0),),
        StripHandlingSpec(6, True),
        ScanLayoutSpec(),
    ),
    "135-dual": FormatSpec(
        "135-dual",
        (FrameDesignApertureMm(36.0, 24.0),),
        StripHandlingSpec(12, False),
        ScanLayoutSpec("dual_lane", 2, "135"),
    ),
    "half": FormatSpec(
        "half",
        (FrameDesignApertureMm(18.0, 24.0),),
        StripHandlingSpec(12, True),
        ScanLayoutSpec(),
    ),
    "xpan": FormatSpec(
        "xpan",
        (FrameDesignApertureMm(65.0, 24.0),),
        StripHandlingSpec(3, True),
        ScanLayoutSpec(),
    ),
    "120-645": FormatSpec(
        "120-645",
        (
            FrameDesignApertureMm(42.0, 54.0),
            FrameDesignApertureMm(42.0, 56.0),
        ),
        StripHandlingSpec(4, True),
        ScanLayoutSpec(),
    ),
    "120-66": FormatSpec(
        "120-66",
        (
            FrameDesignApertureMm(54.0, 54.0),
            FrameDesignApertureMm(56.0, 56.0),
        ),
        StripHandlingSpec(3, True),
        ScanLayoutSpec(),
    ),
    "120-67": FormatSpec(
        "120-67",
        (
            FrameDesignApertureMm(70.0, 54.0),
            FrameDesignApertureMm(70.0, 56.0),
        ),
        StripHandlingSpec(3, True),
        ScanLayoutSpec(),
    ),
}

FORMAT_CHOICES = tuple(FORMATS)


def format_spec(format_id: str) -> FormatSpec:
    return FORMATS[format_id]
