from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive

@dataclass(frozen=True)
class FrameSizeMm:
    width_mm: float
    height_mm: float

    def __post_init__(self) -> None:
        require_positive("frame width", self.width_mm)
        require_positive("frame height", self.height_mm)

    @property
    def aspect(self) -> float:
        return float(self.width_mm) / float(self.height_mm)


@dataclass(frozen=True)
class FramePhysicalSpec:
    frame_size_mm_options: tuple[FrameSizeMm, ...]

    def __post_init__(self) -> None:
        if not self.frame_size_mm_options:
            raise ValueError("frame physical spec requires at least one size option")

    @property
    def nominal_size_mm(self) -> FrameSizeMm:
        return self.frame_size_mm_options[0]


@dataclass(frozen=True)
class StripHandlingSpec:
    default_count: int
    allowed_partial_counts: tuple[int, ...]
    complete_strip_can_be_underfilled: bool = False

    def __post_init__(self) -> None:
        require_positive("default frame count", self.default_count)
        if (
            tuple(sorted(set(self.allowed_partial_counts)))
            != self.allowed_partial_counts
            or any(count <= 0 for count in self.allowed_partial_counts)
        ):
            raise ValueError(
                "allowed partial counts must be positive, unique, and ordered"
            )
        if any(count > self.default_count for count in self.allowed_partial_counts):
            raise ValueError("partial counts cannot exceed the nominal full count")
        if (
            self.default_count in self.allowed_partial_counts
        ) != self.complete_strip_can_be_underfilled:
            raise ValueError(
                "only complete-underfilled strips may expose the nominal count "
                "in partial mode"
            )


@dataclass(frozen=True)
class ScanLayoutSpec:
    kind: str = "single_strip"
    lane_count: int = 1
    lane_format_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"single_strip", "dual_lane"}:
            raise ValueError(f"unsupported scan layout: {self.kind}")
        if self.kind == "dual_lane":
            if self.lane_count <= 1:
                raise ValueError("dual-lane layout requires multiple lanes")
            if not self.lane_format_id:
                raise ValueError("dual-lane layout requires a lane format identity")
        elif self.lane_count != 1 or self.lane_format_id is not None:
            raise ValueError("single-strip layout cannot declare lane geometry")


@dataclass(frozen=True)
class FormatSpec:
    format_id: str
    frame: FramePhysicalSpec
    strip: StripHandlingSpec
    layout: ScanLayoutSpec

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("format identity must not be empty")
        if (
            self.layout.kind == "dual_lane"
            and self.strip.default_count % self.layout.lane_count
        ):
            raise ValueError("dual-lane frame count must divide evenly across lanes")

def expected_separator_count(
    strip: StripHandlingSpec,
    layout: ScanLayoutSpec,
) -> int:
    if layout.kind == "dual_lane":
        if strip.default_count % layout.lane_count:
            raise ValueError("dual-lane frame count must divide evenly")
        lane_frame_count = int(strip.default_count) // int(layout.lane_count)
        return int(layout.lane_count) * (lane_frame_count - 1)
    return int(strip.default_count) - 1


FORMATS: dict[str, FormatSpec] = {
    "135": FormatSpec(
        format_id="135",
        frame=FramePhysicalSpec((FrameSizeMm(36.0, 24.0),)),
        strip=StripHandlingSpec(6, tuple(range(1, 6))),
        layout=ScanLayoutSpec(),
    ),
    "135-dual": FormatSpec(
        format_id="135-dual",
        frame=FramePhysicalSpec((FrameSizeMm(36.0, 24.0),)),
        strip=StripHandlingSpec(12, ()),
        layout=ScanLayoutSpec("dual_lane", 2, "135"),
    ),
    "half": FormatSpec(
        format_id="half",
        frame=FramePhysicalSpec((FrameSizeMm(18.0, 24.0),)),
        strip=StripHandlingSpec(12, tuple(range(1, 12))),
        layout=ScanLayoutSpec(),
    ),
    "xpan": FormatSpec(
        format_id="xpan",
        frame=FramePhysicalSpec((FrameSizeMm(65.0, 24.0),)),
        strip=StripHandlingSpec(3, (1, 2, 3), True),
        layout=ScanLayoutSpec(),
    ),
    "120-645": FormatSpec(
        format_id="120-645",
        frame=FramePhysicalSpec((FrameSizeMm(42.0, 56.0),)),
        strip=StripHandlingSpec(4, (1, 2, 3)),
        layout=ScanLayoutSpec(),
    ),
    "120-66": FormatSpec(
        format_id="120-66",
        frame=FramePhysicalSpec((
            FrameSizeMm(56.0, 56.0),
            FrameSizeMm(54.0, 54.0),
        )),
        strip=StripHandlingSpec(3, (1, 2, 3), True),
        layout=ScanLayoutSpec(),
    ),
    "120-67": FormatSpec(
        format_id="120-67",
        frame=FramePhysicalSpec((FrameSizeMm(70.0, 56.0),)),
        strip=StripHandlingSpec(3, (1, 2)),
        layout=ScanLayoutSpec(),
    ),
}

FORMAT_CHOICES = tuple(FORMATS.keys())


def format_spec(format_id: str) -> FormatSpec:
    return FORMATS[format_id]
