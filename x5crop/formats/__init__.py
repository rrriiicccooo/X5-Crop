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
class FormatPhysicalSpec:
    format_id: str
    default_count: int
    allowed_counts: tuple[int, ...]
    frame_size_mm_options: tuple[FrameSizeMm, ...]
    physical_layout: str = "single_strip"
    complete_strip_can_be_underfilled: bool = False
    lane_count: int = 1
    lane_format_id: str | None = None

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("format identity must not be empty")
        require_positive("default frame count", self.default_count)
        if (
            not self.allowed_counts
            or tuple(sorted(set(self.allowed_counts))) != self.allowed_counts
            or any(count <= 0 for count in self.allowed_counts)
        ):
            raise ValueError("allowed frame counts must be positive, unique, and ordered")
        if self.default_count not in self.allowed_counts:
            raise ValueError("default frame count must be allowed")
        if not self.frame_size_mm_options:
            raise ValueError("format requires at least one physical frame size")
        if self.physical_layout not in {"single_strip", "dual_lane"}:
            raise ValueError(f"unsupported physical layout: {self.physical_layout}")
        if self.physical_layout == "dual_lane":
            if self.lane_count <= 1 or self.default_count % self.lane_count:
                raise ValueError("dual-lane count must divide into multiple equal lanes")
            if not self.lane_format_id:
                raise ValueError("dual-lane format requires a lane format identity")
        elif self.lane_count != 1 or self.lane_format_id is not None:
            raise ValueError("single-strip format cannot declare lane geometry")

    @property
    def nominal_frame_size_mm(self) -> FrameSizeMm:
        return self.frame_size_mm_options[0]

    @property
    def horizontal_content_aspect(self) -> float:
        return self.nominal_frame_size_mm.aspect

    @property
    def expected_separator_count(self) -> int:
        return expected_separator_count(
            self.default_count,
            self.physical_layout,
            self.lane_count,
        )

def expected_separator_count(
    default_count: int,
    physical_layout: str,
    lane_count: int,
) -> int:
    if default_count <= 0:
        raise ValueError("default frame count must be positive")
    if physical_layout == "dual_lane":
        if lane_count <= 1 or default_count % lane_count:
            raise ValueError("dual-lane frame count must divide evenly")
        lane_frame_count = int(default_count) // int(lane_count)
        return int(lane_count) * (lane_frame_count - 1)
    if physical_layout != "single_strip" or lane_count != 1:
        raise ValueError("single-strip separator count requires one lane")
    return int(default_count) - 1


FORMATS: dict[str, FormatPhysicalSpec] = {
    "135": FormatPhysicalSpec(
        format_id="135",
        default_count=6,
        allowed_counts=tuple(range(1, 7)),
        frame_size_mm_options=(FrameSizeMm(36.0, 24.0),),
    ),
    "135-dual": FormatPhysicalSpec(
        format_id="135-dual",
        default_count=12,
        allowed_counts=(12,),
        frame_size_mm_options=(FrameSizeMm(36.0, 24.0),),
        physical_layout="dual_lane",
        lane_count=2,
        lane_format_id="135",
    ),
    "half": FormatPhysicalSpec(
        format_id="half",
        default_count=12,
        allowed_counts=tuple(range(1, 13)),
        frame_size_mm_options=(FrameSizeMm(18.0, 24.0),),
    ),
    "xpan": FormatPhysicalSpec(
        format_id="xpan",
        default_count=3,
        allowed_counts=(1, 2, 3),
        frame_size_mm_options=(FrameSizeMm(65.0, 24.0),),
        complete_strip_can_be_underfilled=True,
    ),
    "120-645": FormatPhysicalSpec(
        format_id="120-645",
        default_count=4,
        allowed_counts=(1, 2, 3, 4),
        frame_size_mm_options=(FrameSizeMm(42.0, 56.0),),
    ),
    "120-66": FormatPhysicalSpec(
        format_id="120-66",
        default_count=3,
        allowed_counts=(1, 2, 3),
        frame_size_mm_options=(
            FrameSizeMm(56.0, 56.0),
            FrameSizeMm(54.0, 54.0),
        ),
        complete_strip_can_be_underfilled=True,
    ),
    "120-67": FormatPhysicalSpec(
        format_id="120-67",
        default_count=3,
        allowed_counts=(1, 2, 3),
        frame_size_mm_options=(FrameSizeMm(70.0, 56.0),),
    ),
}

FORMAT_CHOICES = tuple(FORMATS.keys())


def format_spec(format_id: str) -> FormatPhysicalSpec:
    return FORMATS[format_id]
